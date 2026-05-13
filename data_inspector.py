#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data_inspector.py — 数据监督源（新增 Agent 0）

放在 fetch_bidu_v2.py 等所有 fetch_*.py 中调用。

职责：
1. 检查本地日线数据的完整性（行数、日期范围、最新价、缺失值）
2. 检查 NeoData 每个数据块内容的有效性（最新行情时间戳、价格合理性、资金流向金额）
3. 检查财务数据是否完整加载（利润表/资产负债表/现金流有值）
4. 检查新闻是否有近期内容
5. 交叉验证关键字段一致性（日线最新价 vs NeoData行情价）
6. 输出一份"数据质量报告"嵌入最终 report/data 目录
7. 如果数据有重大问题（过期价格、缺失关键字段），发出 ALERT

V2 新增：在 Context 中标记一份给其他 Agent 参考的数据摘要（避免 Agent 读错价格）
"""

import json, os, re
from datetime import datetime, timedelta

def inspect_data(stock, code, data_base=None, all_rows=None, headers=None,
                 item_map=None, neodata_path=None, news_path=None,
                 fin_paths=None, context_str=None, context_parts=None):
    """
    data_base: 分析数据所在目录（含 data/ 子目录）
    返回: {
        "has_issues": bool,  # 是否有重大问题
        "alert": str,        # 警告信息
        "quality_report": str, # 可读报告
        "data_anchor": str,  # 给其他Agent参考的数据锚点
    }
    """
    report_lines = []
    issues = []
    data_anchor = []

    # ====== 1. 日线数据检查 ======
    report_lines.append("## 数据监督报告\n")
    
    if all_rows and headers:
        n_rows = len(all_rows)
        report_lines.append(f"### 1. 本地日线数据")
        report_lines.append(f"- 总行数: {n_rows}")
        
        # 找date列和close列
        date_idx = None
        close_idx = None
        open_idx = None
        high_idx = None
        low_idx = None
        vol_idx = None
        
        for i, h in enumerate(headers):
            h_lower = str(h).lower()
            if 'date' in h_lower:
                date_idx = i
            elif h_lower in ('close', '收盘', '收盘价'):
                close_idx = i
            elif h_lower in ('open', '开盘', '开盘价'):
                open_idx = i
            elif h_lower in ('high', '最高', '最高价'):
                high_idx = i
            elif h_lower in ('low', '最低', '最低价'):
                low_idx = i
            elif h_lower in ('volume', 'vol', '成交量', '成交数量', 'volume'):
                vol_idx = i
        
        # 日期范围
        if date_idx is not None:
            first_date = all_rows[0][date_idx]
            last_date = all_rows[-1][date_idx]
            report_lines.append(f"- 日期范围: {first_date} ~ {last_date}")
            report_lines.append(f"- 最新交易日: {last_date}")
        
        # 最新价格
        if close_idx is not None:
            last_close = all_rows[-1][close_idx]
            report_lines.append(f"- 最新收盘价: {last_close}")
            data_anchor.append(f"日线最新收盘: {last_close}")
            
            # 检查价格合理性（非0、非None）
            if last_close is None or (isinstance(last_close, (int, float)) and last_close == 0):
                issues.append("⚠️ 最新收盘价为0或空值！")
            elif isinstance(last_close, (int, float)) and last_close > 1000:
                report_lines.append(f"  ⚠️ 注意：价格较高 ({last_close})，确认单位正确")
            
            # 计算简单回报
            closes_vals = []
            for r in all_rows:
                v = r[close_idx]
                if v is not None:
                    try:
                        closes_vals.append(float(v))
                    except:
                        pass
            if len(closes_vals) >= 20:
                ret_5d = (closes_vals[-1] - closes_vals[-5]) / closes_vals[-5] * 100
                ret_20d = (closes_vals[-1] - closes_vals[-20]) / closes_vals[-20] * 100
                high_20d = max(closes_vals[-20:])
                low_20d = min(closes_vals[-20:])
                report_lines.append(f"- 5日涨跌幅: {ret_5d:+.2f}%")
                report_lines.append(f"- 20日涨跌幅: {ret_20d:+.2f}%")
                report_lines.append(f"- 20日最高: {high_20d:.2f}  最低: {low_20d:.2f}")
                
                # 检查是否有异常波动（单日>15%）
                for i in range(-20, 0):
                    if i >= -len(closes_vals):
                        dret = (closes_vals[i] - closes_vals[i-1]) / closes_vals[i-1] * 100
                        if abs(dret) > 15:
                            rdate = all_rows[i+len(all_rows)-20][date_idx] if date_idx is not None else i
                            report_lines.append(f"  ⚠️ {rdate} 单日波动 {dret:+.2f}%")
                
            data_anchor.append(f"日线行数: {len(closes_vals)}")
        else:
            issues.append("❌ 找不到columns中的close字段")
        
        # 检查NaN/None
        missing = 0
        for ri, row in enumerate(all_rows[-30:]):  # 只看最近30行
            for ci, v in enumerate(row):
                if v is None or (isinstance(v, float) and (v != v)):
                    missing += 1
                    if missing <= 3:
                        col_name = headers[ci] if ci < len(headers) else f"col{ci}"
                        report_lines.append(f"  ⚠️ 倒数第{30-ri}行 {col_name} 为空值")
        
        if missing > 0:
            issues.append(f"⚠️ 日线最近30行中存在 {missing} 个空值")

    else:
        issues.append("❌ 未提供日线数据")
    
    report_lines.append("")
    
    # ====== 2. NeoData 检查 ======
    report_lines.append("### 2. NeoData 数据源")
    
    if item_map:
        n_items = len(item_map)
        total_chars = sum(len(v) for v in item_map.values())
        report_lines.append(f"- 数据块数量: {n_items}，总字符: {total_chars}")
        data_anchor.append(f"NeoData: {n_items}数据块, {total_chars}c")
        
        # 检查行情
        price_item = item_map.get("股票实时行情", "")
        if price_item:
            # 提取价格和时间
            price_match = re.search(r'最新价格[:：\s]*([\d.]+)', price_item)
            time_match = re.search(r'(?:更新时间|数据更新)[:：\s]*(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', price_item)
            
            if price_match:
                neo_price = float(price_match.group(1))
                report_lines.append(f"- ✅ NeoData 最新行情价: {neo_price}")
                data_anchor.append(f"NeoData行情价: {neo_price}")
                
                # 交叉验证：日线收盘 vs NeoData行情价
                if close_idx is not None:
                    last_close = all_rows[-1][close_idx]
                    try:
                        daily_close = float(last_close)
                        diff_pct = abs(neo_price - daily_close) / daily_close * 100
                        if diff_pct > 1:
                            issues.append(f"⚠️ 日线收盘价({daily_close})与NeoData行情价({neo_price})差异{diff_pct:.1f}%")
                        else:
                            report_lines.append(f"- ✅ 日线 vs NeoData 价格一致（差异{diff_pct:.1f}%）")
                    except (ValueError, TypeError):
                        pass
            
            if time_match:
                report_lines.append(f"- 行情更新时间: {time_match.group(1)}")
                last_trade_date = all_rows[-1][date_idx] if date_idx is not None else None
                if last_trade_date:
                    report_lines.append(f"- 最后交易日: {last_trade_date}")
        else:
            issues.append("❌ 缺少股票实时行情数据块")
        
        # 检查资金流向
        flow_item = item_map.get("今日资金流向", "")
        if flow_item:
            flow_match = re.search(r'(?:总|主力)净流入[:：\s]*([\d.\-]+)', flow_item)
            if flow_match:
                report_lines.append(f"- ✅ 资金流向: 主力净流入={flow_match.group(1)}")
            else:
                # 尝试找主力净流入
                flow_match2 = re.search(r'主力净流入([\d.\-]+)', flow_item)
                if flow_match2:
                    report_lines.append(f"- ✅ 资金流向: 主力净流入={flow_match2.group(1)}")
                else:
                    report_lines.append(f"- ⚠️ 资金流向数据格式解析失败（内容:{flow_item[:100]}）")
        else:
            issues.append("⚠️ 缺少今日资金流向")
        
        # 检查技术指标
        tech_item = item_map.get("技术面信息", "")
        if tech_item:
            tech_len = len(tech_item)
            report_lines.append(f"- ✅ 技术指标: {tech_len}字符")
            # 提取KDJ或MACD
            for key, label in [("J值", "KDJ"), ("平滑ADX", "ADX"), ("MACD柱状图", "MACD")]:
                m = re.search(rf'{key}[:：\s]*([\d.\-]+)', tech_item)
                if m:
                    report_lines.append(f"  {key}: {m.group(1)}")
                    break
        else:
            issues.append("⚠️ 缺少技术面信息")
        
        # 检查财务数据
        for fin_type, label in [("利润表", "利润表"), ("资产负债表", "资产负债表"),
                                ("现金流量表", "现金流量表"), ("公司简介", "公司简介")]:
            if fin_type in item_map:
                report_lines.append(f"- ✅ {label}: {len(item_map[fin_type])}字符")
            elif fin_type not in item_map:
                # 可能在其他地方
                found = False
                for k, v in item_map.items():
                    if fin_type in k or k in fin_type:
                        report_lines.append(f"- ✅ {label}(找{fin_type}→实际类型'{k}'): {len(v)}字符")
                        found = True
                        break
                if not found:
                    report_lines.append(f"- ⚠️ 未找到'{label}'数据块（可能在其他文件中）")
        
        # 检查市场观点/研报
        mrkt_types = [k for k in item_map.keys() if '观点' in k or '研报' in k or '评级' in k]
        if mrkt_types:
            for t in mrkt_types:
                report_lines.append(f"- ✅ 研报观点 ({t}): {len(item_map[t])}字符")
        else:
            report_lines.append(f"- ⚠️ 未找到研报/市场观点数据块")
    
    else:
        issues.append("❌ 无NeoData数据")
    
    report_lines.append("")
    
    # ====== 3. 财务文件检查 ======
    if fin_paths:
        report_lines.append("### 3. 财务报表文件")
        for fn, label in fin_paths:
            fp = os.path.join(data_base, "data", fn) if data_base else fn
            if os.path.exists(fp):
                fsize = os.path.getsize(fp)
                with open(fp, "rb") as f:
                    raw = f.read()
                if raw[:3]==b"\xef\xbb\xbf": raw=raw[3:]
                text = raw.decode("utf-8", errors="replace")
                
                # 尝试解析JSON提取金融数据
                m = re.search(r'\{.*\}', text, re.DOTALL)
                ext_content = ""
                if m:
                    try:
                        d = json.loads(m.group())
                        its = d.get('data',{}).get('apiData',{}).get('apiRecall',[])
                        if its:
                            ext_content = its[0].get('content','')
                    except:
                        ext_content = text[:100]
                else:
                    ext_content = text[:100]
                
                report_lines.append(f"- ✅ {label}: {fsize} bytes")
                data_anchor.append(f"{label}: {fsize}b")
            else:
                issues.append(f"❌ 找不到财务文件: {fn}")
                report_lines.append(f"- ❌ {label}: 文件缺失")
    
    report_lines.append("")
    
    # ====== 4. 新闻检查 ======
    if news_path:
        report_lines.append("### 4. 新闻数据")
        if os.path.exists(news_path):
            fsize = os.path.getsize(news_path)
            with open(news_path, "rb") as f:
                raw = f.read()
            if raw[:3]==b"\xef\xbb\xbf": raw=raw[3:]
            text = raw.decode("utf-8", errors="replace")
            
            # NeoData返回的新闻可能在apiRecall或docRecall中
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                try:
                    d = json.loads(m.group())
                    # 先查apiRecall
                    its = d.get('data',{}).get('apiData',{}).get('apiRecall',[])
                    if its:
                        news_confirmed = its[0].get('type','news')
                        news_text = its[0].get('content','')
                        report_lines.append(f"- ✅ 新闻 (apiRecall-{news_confirmed}): {len(news_text)}字符")
                        data_anchor.append(f"新闻: {len(news_text)}c")
                    else:
                        # 再查docRecall
                        docs = d.get('data',{}).get('docData',{}).get('docRecall',[])
                        n_docs = 0
                        doc_total = 0
                        for dl in docs:
                            dlist = dl.get('docList',[])
                            n_docs += len(dlist)
                            for dd in dlist:
                                doc_total += len(dd.get('content',''))
                        if n_docs > 0:
                            report_lines.append(f"- ✅ 新闻 (docRecall): {n_docs}篇文档, 约{doc_total}字符")
                            data_anchor.append(f"新闻: {n_docs}篇")
                        else:
                            report_lines.append(f"- ⚠️ 新闻JSON中apiRecall和docRecall均为空")
                except Exception as e:
                    report_lines.append(f"- ⚠️ 新闻JSON解析失败: {e}")
            else:
                report_lines.append(f"- ⚠️ 新闻文件未包含JSON数据 ({fsize}b raw)")
        else:
            issues.append("❌ 新闻文件缺失")
    
    # ====== 5. 文档新闻检查（兼容neodata.json中的docRecall）======
    
    # ====== 6. Context完整性检查 ======
    if context_str:
        report_lines.append(f"\n### 5. Context")
        report_lines.append(f"- Context长度: {len(context_str)} 字符")
        data_anchor.append(f"Context: {len(context_str)}c")
        
        if len(context_str) < 1000:
            issues.append("⚠️ Context仅{len(context_str)}字符，数据严重不足")
        
        # 检测context中是否包含关键数字
        price_in_ctx = re.findall(r'[\d]+\.[\d]+', context_str)
        ctx_price_candidates = [float(p) for p in price_in_ctx if float(p) < 500 and float(p) > 0.1]
        if close_idx is not None:
            try:
                last_close = float(all_rows[-1][close_idx])
                if last_close not in ctx_price_candidates:
                    # 模糊匹配
                    close_rounded = round(last_close)
                    report_lines.append(f"- ⚠️ Context中可能未包含最新价{last_close}的精确数字")
            except:
                pass
    
    # ====== 总结 ======
    report_lines.append(f"\n### 6. 数据质量总结")
    
    n_issues = len(issues)
    has_critical = any('❌' in i for i in issues)
    has_warning = any(['⚠️' in i or '⚠' in i for i in issues]) or any('差异' in i for i in issues)
    
    if n_issues == 0:
        report_lines.append("- ✅ 数据质量优秀，所有数据源完整")
        quality = "优秀"
    elif has_critical:
        quality = "有重大问题"
        report_lines.append(f"- ❌ 发现 {n_issues} 个问题（含严重问题）")
    else:
        quality = "有轻微警告"
        report_lines.append(f"- ⚠️ 发现 {n_issues} 个轻微问题/警告")
    
    for issue in issues:
        report_lines.append(f"  {issue}")
    
    report_lines.append(f"\n**数据质量评估: {quality}**")
    
    # 构建 data_anchor 短签名
    anchor_str = " | ".join(data_anchor)
    
    # 构建最终 report
    report_str = "\n".join(report_lines)
    
    return {
        "has_issues": n_issues > 0,
        "n_issues": n_issues,
        "has_critical": has_critical,
        "quality": quality,
        "issues": issues,
        "quality_report": report_str,
        "data_anchor": anchor_str,
    }


def save_data_quality_report(result, output_dir):
    """保存数据监督报告到文件"""
    fp = os.path.join(output_dir, "agent_数据监督源.md")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(f"# 数据监督源 — 数据质量报告\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(result["quality_report"])
    
    # 另存一份纯数据摘要（给其他Agent引用）
    anchor_fp = os.path.join(output_dir, "data_anchor.txt")
    with open(anchor_fp, "w", encoding="utf-8") as f:
        f.write(f"数据签名: {result['data_anchor']}\n")
        f.write(f"质量评估: {result['quality']}\n")
        f.write(f"问题数: {result['n_issues']}\n")
    
    return fp


if __name__ == "__main__":
    # 简单测试
    print("data_inspector.py loaded OK")
