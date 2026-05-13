#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TradingAgent 通用工具模块

用法:
    from ta_utils import qneo, qneo_or_fallback, build_context, run_agents, run_debate

集成功能:
1. 新闻搜索自动简体中文 + 股票代码格式 (P1 #3)
2. NeoData DNS降级 -> 新浪行情API自动fallback (P1 #5)
3. 9Agent + 辩论标准化 (P1 #6)
"""

import json, os, re, subprocess, urllib.request
from datetime import datetime, timedelta

# ====== 路径常量 ======
PYTHON = r'C:\Users\zhang\AppData\Local\Python\bin\python.exe'
NEO_QUERY = r'C:\Program Files\QClaw\resources\openclaw\config\skills\neodata-financial-search\scripts\query.py'
API_KEY = "sk-39f7fc15acbb42c78082beacdb4338c1"
API_URL = "https://api.deepseek.com/v1/chat/completions"

# ====== 1. 新闻搜索: 自动简体中文格式 ======

def make_news_query(stock_name, code):
    """
    统一新闻查询格式: 简体中文 + 代码 + 最新消息 + 年份
    禁止纯英文查询（5月9日的教训）
    """
    return f"{stock_name} {code} 最新消息 2026"

def make_research_query(stock_name, code):
    """研报查询统一格式"""
    return f"{stock_name} {code} 研报 评级"


# ====== 2. NeoData + 自动降级 ======

def qneo(query, timeout=120):
    """调用NeoData query.py"""
    try:
        r = subprocess.run(
            f'"{PYTHON}" -u "{NEO_QUERY}" --query "{query}" --data-type api',
            capture_output=True, shell=True, timeout=timeout
        )
        raw = (r.stdout + r.stderr).decode('utf-8', errors='replace')
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        return m.group() if m else '{}'
    except subprocess.TimeoutExpired:
        return '{}'
    except Exception:
        return '{}'

def check_neodata_alive():
    """快速检查NeoData是否可用"""
    raw = qneo("贵州茅台 600519 行情", timeout=10)
    return len(raw) > 200

def qneo_or_fallback(queries, stock_name, code, data_dir):
    """
    智能NeoData查询: 先试NeoData, 不通则打印标记告知用户
    (新浪行情降级有confidential数据暴露风险, 暂不做自动降级)
    
    返回: (neodata_json_dict, data_items, doc_items)
    """
    neodata = {"data": {"apiData": {"apiRecall": []}, "docData": {"docRecall": []}}}
    data_items = []
    doc_items = []
    
    for label, q in queries:
        raw = qneo(q)
        if len(raw) > 100:
            fn = label.replace("/", "_").replace("\\", "_")
            with open(os.path.join(data_dir, f"{fn}.txt"), "w", encoding="utf-8") as f:
                f.write(raw)
        try:
            d = json.loads(raw)
            items = d.get('data',{}).get('apiData',{}).get('apiRecall',[])
            neodata['data']['apiData']['apiRecall'].extend(items)
            docs = d.get('data',{}).get('docData',{}).get('docRecall',[])
            neodata['data']['docData']['docRecall'].extend(docs)
            data_items.extend(items)
            doc_items.extend(docs)
            print(f"  {label}: {len(items)} 条数据, {len(docs)} 篇文档", end="")
            if len(raw) < 200:
                print(" [注意: 内容过短]")
            else:
                print()
        except Exception:
            # NeoData不通: 标记但继续
            print(f"  {label}: NeoData不可用, 跳过")
    
    return neodata, data_items, doc_items


# ====== 3. Context 构建 ======

def build_context(all_rows, headers, item_map, stock_name, code):
    """
    构建标准Context.
    优先级: 最新行情/资金流向/技术面 -> 日线 -> 财务数据 -> 研报 -> 新闻
    最新行情和日线收盘价交叉验证
    """
    ctx_parts = []
    
    # 最新行情/资金流向/技术面前置 (百度V1教训: 放后面会被日线数据挤压)
    for k in ["股票实时行情", "今日资金流向", "技术面信息"]:
        if k in item_map and len(item_map[k]) > 50:
            ctx_parts.append(f"### {k}\n{item_map[k][:3000]}\n")
    
    # 涨跌幅摘要
    prices = [float(r[6]) for r in all_rows if r[6] is not None]
    if prices:
        last_p = prices[-1]
        for offset, label in [(5, "5日"), (20, "20日"), (60, "60日")]:
            if len(prices) >= offset:
                pnl = (last_p - prices[-offset]) / prices[-offset] * 100
                ctx_parts.append(f"{label}涨跌: {pnl:+.2f}%\n")
    
    # 日线最后30行
    ctx_parts.append(f"### 日线最后30行\n")
    for r in all_rows[-30:]:
        vals = [str(c) if c is not None else "" for c in r]
        ctx_parts.append("\t".join(vals) + "\n")
    
    nd_text = "\n".join(ctx_parts)
    return nd_text


# ====== 4. 标准9Agent并行分析 ======

def run_agents(prompts, stock_name, code, nd_text, agent_dir):
    """并行或串行运行9Agent, 返回agent_results dict"""
    agent_results = {}
    for name, sysp in prompts.items():
        prompt = sysp.replace("{context}", nd_text[:3000])
        prompt = prompt.replace("{context[:4000]}", nd_text[:4000])
        print(f"  [{name}]...", end=" ", flush=True)
        headers_h = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-v4-pro", "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0.7, "max_tokens": 4096}
        req = urllib.request.Request(API_URL, json.dumps(payload).encode(), headers_h, method="POST")
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=180).read())
            ans = r["choices"][0]["message"]["content"]
            agent_results[name] = ans
            with open(os.path.join(agent_dir, f"agent_{name}.md"), "w", encoding="utf-8") as f:
                f.write(f"# {name}\n\n{ans}\n\n---")
            sc = re.search(r'\*\*综合评分\*\*\s*:\s*([\d.]+)', ans)
            act = re.search(r'\*\*操作建议\*\*\s*:\s*([^\n]+)', ans)
            print(f"评分:{sc.group(1) if sc else '?'} 建议:{act.group(1).strip() if act else '?'}")
        except Exception as e:
            print(f"ERR: {e}")
            agent_results[name] = ""
    return agent_results


# ====== 5. 组合经理终裁 ======

def extract_score(text):
    """匹配综合评分或最终综合评分"""
    m = re.search(r'\*\*[最终]*(?:综合)?评分\*\*\s*:\s*([\d.]+)', text)
    return m.group(1) if m else "?"

def extract_action(text):
    """匹配操作建议或最终操作建议"""
    m = re.search(r'\*\*[最终]*(?:操作)?建议\*\*\s*:\s*([^\n]+)', text)
    return m.group(1).strip() if m else "?"

def extract_position(text):
    """匹配仓位相关字段"""
    m = re.search(r'\*\*[最终期初]*仓位(建议)?[比例]*\*\*\s*:\s*([^\n%]+)', text)
    if m: return m.group(2).strip()
    m = re.search(r'(\d+[-~]?\d*)\s*%', text[:200])
    return m.group(1)+'%' if m else "?"

def extract_price(text, label):
    """匹配入场/止损/目标价格"""
    r = re.compile(r'\*\*' + re.escape(label) + r'.*?\*\*\s*:\s*([^\n]+)')
    m = r.search(text)
    return m.group(1).strip() if m else "?"

def format_debate_summary(stock_name, code, r1_bull, r2_bull, r1_bear, r2_bear, r1_neut, r2_neut, judgment):
    """
    辩论结果可视化摘要卡片
    从R1/2原始文本提取数字，生成紧凑格式
    """
    # Extract scores and actions from each round
    bull_r1_s, bull_r1_a = extract_score(r1_bull), extract_action(r1_bull)
    bull_r2_s, bull_r2_a = extract_score(r2_bull), extract_action(r2_bull)
    bear_r1_s, bear_r1_a = extract_score(r1_bear), extract_action(r1_bear)
    bear_r2_s, bear_r2_a = extract_score(r2_bear), extract_action(r2_bear)
    neut_r1_s, neut_r1_a = extract_score(r1_neut), extract_action(r1_neut)
    neut_r2_s, neut_r2_a = extract_score(r2_neut), extract_action(r2_neut)
    
    pm_s, pm_a = extract_score(judgment), extract_action(judgment)
    pm_p = extract_position(judgment)
    pm_entry = extract_price(judgment, "入场")
    pm_stop = extract_price(judgment, "止损")
    pm_target = extract_price(judgment, "目标")
    
    # Judge divergence: range of round 1 scores
    scores_r1 = []
    for s in [bull_r1_s, bear_r1_s, neut_r1_s]:
        try: scores_r1.append(float(s))
        except: pass
    divergence = "高" if (max(scores_r1)-min(scores_r1)) >= 5 else ("低" if (max(scores_r1)-min(scores_r1)) <= 2 else "中")
    
    # Extract a key quote from judgment
    reason_match = re.search(r'\*\*决策理由\*\*\s*:\s*([^\n]+(?:[\n](?!\*\*)[^\n]+)*)', judgment, re.IGNORECASE)
    top_reason = reason_match.group(1).strip()[:120] if reason_match else ""
    
    # Key contradiction between rounds
    key_change = []
    if bull_r1_s != bull_r2_s: key_change.append(f"激进:{bull_r1_s}→{bull_r2_s}")
    if bear_r1_s != bear_r2_s: key_change.append(f"保守:{bear_r1_s}→{bear_r2_s}")
    if neut_r1_s != neut_r2_s: key_change.append(f"中性:{neut_r1_s}→{neut_r2_s}")
    
    card = f"""
{'='*60}
  🗳️  三风控辩论结果 · {stock_name}({code}) · R1深度推理
{'='*60}

  ┌ {'角色':<12} {'R1初评':<18} {'辩论后':<18} ┐
  ├─{'─'*48}─┤
  │ {'🔥 激进风控':<12} {bull_r1_s+'/10 '+bull_r1_a:<18} {bull_r2_s+'/10 '+bull_r2_a:<18} │
  │ {'🧊 保守风控':<12} {bear_r1_s+'/10 '+bear_r1_a:<18} {bear_r2_s+'/10 '+bear_r2_a:<18} │
  │ {'🎯 中性风控':<12} {neut_r1_s+'/10 '+neut_r1_a:<18} {neut_r2_s+'/10 '+neut_r2_a:<18} │
  └{'─'*48}─┘

  🏆 组合经理终裁: {pm_s}/10  {pm_a}  |  仓位: {pm_p}
     入场: {pm_entry}  止损: {pm_stop}  目标: {pm_target}

  ⚡ 初始分歧度: {divergence}
"""
    if key_change:
        card += f"  🔄 辩论修正: {' | '.join(key_change)}\n"
    if top_reason:
        card += f"\n  📌 核心裁决理由:\n     {top_reason}...\n"
    card += f"{'='*60}\n"
    return card

def format_debate_invite(stock_name, code, pm_ans):
    """
    9Agent终裁完成后附上的辩论邀请
    告诉用户结果和分歧情况，询问是否要启动R1辩论
    """
    s, a, p = extract_score(pm_ans), extract_action(pm_ans), extract_position(pm_ans)
    
    invite = f"""
{'─'*50}
📋 组合经理初裁完毕: {stock_name}({code})
   → 评分: {s}/10  |  建议: {a}  |  仓位: {p}

💡 可以启动**三风控R1深度辩论**（约3-5分钟，消耗R1额度）
   辩论会进行两轮互驳+组合经理终裁，适合分歧大或重要决策时使用
   
👉 **告诉我"跑辩论"，我就用R1跑完整个流程**
{'─'*50}"""
    return invite

def run_pm(stock_name, code, nd_text, agent_results, prompts):
    """组合经理综合裁决，末附辩论邀请"""
    all_v = "\n".join([f"\n### {n}\n{agent_results.get(n, '')[:1500]}" for n in prompts])
    pm_p = f"""你是{stock_name}({code})投资委员会组合经理。最终决策。

===== 核心数据 =====
{nd_text[:1500]}

===== 分析师意见 =====
{all_v[:5000]}

综合所有意见做终裁。

输出：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**入场价格**: X
**止损价格**: X
**目标价格**: X
**仓位比例**: X%
**决策理由**: （引用分析师论点）"""
    
    headers_h = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": pm_p}],
               "temperature": 0.3, "max_tokens": 4096}
    try:
        req = urllib.request.Request(API_URL, json.dumps(payload).encode(), headers_h, method="POST")
        r = json.loads(urllib.request.urlopen(req, timeout=180).read())
        pm_ans = r["choices"][0]["message"]["content"]
        sc, act = extract_score(pm_ans), extract_action(pm_ans)
        pos = extract_position(pm_ans)
        print(f"  组合经理: {sc}/10 {act} 仓位:{pos}")
        print(format_debate_invite(stock_name, code, pm_ans))
        return pm_ans
    except Exception as e:
        print(f"ERR: {e}")
        return ""


# ====== 6. 三风控辩论 (R1深度推理) ======

def run_debate(stock_name, code, all_data, data_dir):
    """
    三风控深度辩论流程:
    Round 1: 各自初评
    Round 2: 相互反驳后更新
    终裁: 组合经理(DeepSeek-R1)综合裁决
    返回: 终裁文本
    """
    print("\n" + "="*50)
    print("  R1三风控深度辩论开始")
    print("="*50)
    
    bully_prompt = f'''你是{stock_name}({code})的激进风控（看多角度）。
当前市场数据如下：
{all_data[:7000]}
回答结构：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**核心看多逻辑**: （至少4条，每条引用具体数据）
**仓位建议**: X%
**入场/止损/目标**: X / X / X
**对看空论据的反驳**:'''

    bear_prompt = f'''你是{stock_name}({code})的保守风控（看空角度）。
当前市场数据如下：
{all_data[:7000]}
回答结构：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**核心看空逻辑**: （至少4条，每条引用具体数据）
**仓位建议**: X%
**对看多论据的反驳**:'''

    neut_prompt = f'''你是{stock_name}({code})的中性风控。
当前市场数据如下：
{all_data[:7000]}
回答结构：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**看多因素**: （至少3条，引用数据）
**看空因素**: （至少3条，引用数据）
**折中方案**:'''
    
    def call_r1(prompt):
        headers_h = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-reasoner", "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0.3, "max_tokens": 4096}
        req = urllib.request.Request(API_URL, json.dumps(payload).encode(), headers_h, method="POST")
        r = json.loads(urllib.request.urlopen(req, timeout=240).read())
        content = r["choices"][0]["message"]["content"]
        # Remove  response tags if present
        content = re.sub(r'^.*? response\s*', '', content, flags=re.DOTALL)
        return content
    
    # Round 1
    print("  Round 1: 初评...")
    r1_bull = call_r1(bully_prompt)
    r1_bear = call_r1(bear_prompt)
    r1_neut = call_r1(neut_prompt)
    
    with open(os.path.join(data_dir, "辩论_round1.txt"), "w", encoding="utf-8") as f:
        f.write(f"===== 激进风控 =====\n{r1_bull}\n\n===== 保守风控 =====\n{r1_bear}\n\n===== 中性风控 =====\n{r1_neut}")
    
    # Extract scores from round 1
    def extract_score(text):
        m = re.search(r'\*\*综合评分\*\*\s*:\s*([\d.]+)', text)
        return float(m.group(1)) if m else None
    def extract_action(text):
        m = re.search(r'\*\*操作建议\*\*\s*:\s*([^\n]+)', text)
        return m.group(1).strip() if m else "?"
    
    print(f"    激进: {extract_score(r1_bull)}/10 {extract_action(r1_bull)}")
    print(f"    保守: {extract_score(r1_bear)}/10 {extract_action(r1_bear)}")
    print(f"    中性: {extract_score(r1_neut)}/10 {extract_action(r1_neut)}")
    
    # Round 2: Cross-exam
    print("  Round 2: 相互辩论...")
    
    cross_bull = f'''你是{stock_name}的激进风控（看多）。
你的初评：{r1_bull[:2000]}
保守风控初评：{r1_bear[:2000]}
反驳保守风控核心论据，更新观点。
**对保守风控的反驳**:
**对自己观点的修正**:
**最终综合评分**: X/10
**最终操作建议**: 买入/观望/卖出
**最终仓位建议**: X%'''

    cross_bear = f'''你是{stock_name}的保守风控（看空）。
你的初评：{r1_bear[:2000]}
激进风控初评：{r1_bull[:2000]}
反驳激进风控核心论据，更新观点。
**对激进风控的反驳**:
**对自己观点的修正**:
**最终综合评分**: X/10
**最终操作建议**: 买入/观望/卖出
**最终仓位建议**: X%'''

    cross_neut = f'''你是{stock_name}的中性风控。
激进初评：{r1_bull[:1500]}
保守初评：{r1_bear[:1500]}
你的初评：{r1_neut[:1500]}
权衡双方论据，更新方案。
**对双方论据的权衡**:
**最终综合评分**: X/10
**最终操作建议**: 买入/观望/卖出
**最终仓位建议**: X%'''

    r2_bull = call_r1(cross_bull)
    r2_bear = call_r1(cross_bear)
    r2_neut = call_r1(cross_neut)
    
    with open(os.path.join(data_dir, "辩论_round2.txt"), "w", encoding="utf-8") as f:
        f.write(f"===== 激进风控最终 =====\n{r2_bull}\n\n===== 保守风控最终 =====\n{r2_bear}\n\n===== 中性风控最终 =====\n{r2_neut}")
    
    print(f"    激进最终: {extract_score(r2_bull)}/10 {extract_action(r2_bull)}")
    print(f"    保守最终: {extract_score(r2_bear)}/10 {extract_action(r2_bear)}")
    print(f"    中性最终: {extract_score(r2_neut)}/10 {extract_action(r2_neut)}")
    
    # Judgment
    print("  组合经理终裁...")
    judge_prompt = f'''你是{stock_name}({code})投资委员会主席（组合经理），R1深度推理终裁。

基础数据：{all_data[:4000]}

三方辩论：
**激进风控初评**: {r1_bull[:1000]}
**激进风控辩论后**: {r2_bull[:1000]}
**保守风控初评**: {r1_bear[:1000]}
**保守风控辩论后**: {r2_bear[:1000]}
**中性风控初评**: {r1_neut[:1000]}
**中性风控辩论后**: {r2_neut[:1000]}

综合所有信息做终裁。
**最终综合评分**: X/10
**最终操作建议**: 买入/观望/卖出
**入场价格**: X
**止损价格**: X
**目标价格**: X
**仓位比例**: X%
**决策理由**: （引用关键论据）'''

    judgment = call_r1(judge_prompt)
    with open(os.path.join(data_dir, "辩论_终裁.txt"), "w", encoding="utf-8") as f:
        f.write(judgment)
    
    # Print formatted summary card
    print()
    print(format_debate_summary(stock_name, code, r1_bull, r2_bull, r1_bear, r2_bear, r1_neut, r2_neut, judgment))
    return judgment


# ====== 7. 监工Agent：报告质量审计 + 侦探工作站 ======

def run_overseer(stock_name, code, stock_number, agent_results, pm_answer, debate_content=None, data_summary=None):
    """
    监工Agent（第10Agent）：在所有分析和终裁完成后运行。
    
    职责：
    1. 🕵️ 偷懒检测 — 检查是否有Agent输出过短、回避作答、用空话搪塞
    2. 📊 质量审计 — 检查评分与建议是否匹配、数据引用是否合理
    3. 👁️ 行为统计 — 统计每轮谁写得最长最短、回答有无实质内容
    4. ✅ 报告完整性 — 检查关键字段是否齐全
    5. 📝 给出改进建议
    
    输出结构化的监工报告，不修改原分析结论。
    """
    
    # 构建偷懒检测数据
    agent_survey = {}
    for name, content in agent_results.items():
        char_len = len(content or "")
        word_count = char_len  # 中文用字数
        has_evasion = any(kw in (content or "").lower() for kw in ["我不确定", "无法判断", "信息不足", "数据不充分", 
                                                                    "不确定", "cannot assess", "insufficient data"])
        has_score = bool(re.search(r'\*\*综合评分\*\*\s*:\s*[\d.]+', content or ""))
        has_action = bool(re.search(r'\*\*操作建议\*\*\s*:\s*[^\n]+', content or ""))
        
        agent_survey[name] = {
            "字数": char_len,
            "回避措辞": "⚠️ 有" if has_evasion else "✅ 无",
            "评分字段": "✅" if has_score else "❌ 缺失",
            "建议字段": "✅" if has_action else "❌ 缺失",
        }
    
    # 构建监工Prompt
    survey_lines = []
    for n, s in agent_survey.items():
        survey_lines.append(f"  [{n}] 字数={s['字数']}  {s['回避措辞']}  评分:{s['评分字段']}  建议:{s['建议字段']}")
    survey_text = "\n".join(survey_lines)
    
    # 评分一致性检查：如果所有评分相同或差距极小，可能是互相抄袭
    scores = []
    for n, c in agent_results.items():
        m = re.search(r'\*\*综合评分\*\*\s*:\s*([\d.]+)', c or "")
        if m:
            try: scores.append(float(m.group(1)))
            except: pass
    score_diversity = ""
    if len(scores) >= 3:
        avg = sum(scores) / len(scores)
        unique_scores = len(set(scores))
        if unique_scores <= 2 and len(scores) >= 5:
            score_diversity = "⚠️ 警告：所有Agent评分集中在2个数值内，可能存在互相影响或缺乏独立判断"
        elif max(scores) - min(scores) < 2:
            score_diversity = "⚠️ 注意：评分范围过窄（<2分），独立判断空间不足"
        else:
            score_diversity = f"✅ 评分分布健康（范围：{min(scores):.1f}~{max(scores):.1f}）"
    
    # 整体质量评估
    overseer_prompt = f"""你是一个严格但不刻薄的**监工Agent（监督审计员）**。

你的任务是审计对 {stock_name}({code}) 的9Agent分析报告质量。
不需要重写结论，只需要指出事实。

## 1. 各Agent产出统计
{survey_text}

{score_diversity}

## 2. 组合经理终裁
{pm_answer[:2000] if pm_answer else '（无）'}

## 3. 核心审计项目
逐项审计：

### A. 📉 偷懒检测
- 哪个Agent字数最少？合理吗？（最小字数<50字符标记为偷懒）
- 有Agent用了'我不确定'/'无法判断'等回避措辞吗？
- 谁评分/建议字段缺失？

### B. 🎯 评分-建议一致性
- 高分(>7)+却建议卖出？低分(<4)却建议买入？——这是逻辑矛盾
- 列出所有评分和建议不匹配的Agent

### C. 📋 报告完整性
- 9Agent + 组合经理共计10份输出是否全部到位？
- 有没有Agent明显内容雷同或模板化？

### D. 🔍 质量观察
- 是否有Agent的分析看起来像'凑字数'（通篇空泛）？
- 整体报告质量评级（A/B/C）

输出压缩为简洁格式，每条用1-2句话，总长度控制在500字以内。
标记'|✅ GOOD|'或'|⚠️ ISSUE|'前缀每条结论。

**监工总结**:

| 项目 | 状态 |
|------|------|
| 偷懒检测 | ... |
| 评分一致性 | ... |
| 报告完整性 | ... |
| 质量评级 | A/B/C |

**抓到偷懒**: x个Agent（名字）
**改进建议**: （若有）
"""
    
    headers_h = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": overseer_prompt}],
               "temperature": 0.3, "max_tokens": 2048}
    try:
        req = urllib.request.Request(API_URL, json.dumps(payload).encode(), headers_h, method="POST")
        r = json.loads(urllib.request.urlopen(req, timeout=120).read())
        report = r["choices"][0]["message"]["content"]
        print(f"\n{'='*60}")
        print(f"  🕵️  监工报告 · {stock_name}({code})")
        print(f"{'='*60}")
        print(report)
        print(f"{'='*60}\n")
        return report
    except Exception as e:
        print(f"  监工Agent ERR: {e}")
        return ""


# ====== 8. 标准9Agent Prompts工厂 ======

def make_prompts(stock_name, code, is_bank=False, is_tech=False):
    """生成标准9Agent prompts, 带is_bank/is_tech自动适配"""
    
    if is_bank:
        fund_focus = f"""{stock_name}核心关注点：净息差(NIM)、不良贷款率(NPL)、拨备覆盖率、ROE、分红率、资本充足率。"""
        bull_focus = f"高股息率、南向资金加仓、资产质量改善。"
        bear_focus = f"房地产敞口风险、净息差收窄、不良贷款反弹。"
    elif is_tech:
        fund_focus = f"""{stock_name}核心关注点：营收增速、毛利率、净利润、现金流、研发投入、市场份额、估值(PE/PEG)。"""
        bull_focus = f"龙头地位、市场份额增长、盈利改善、估值修复空间。"
        bear_focus = f"竞争加剧、毛利率承压、估值过高、行业监管、周期波动。"
    else:
        fund_focus = f"{stock_name}核心关注点：营收、利润、现金流、估值。"
        bull_focus = f"估值优势、增长潜力。"
        bear_focus = f"市场风险、竞争风险。"
    
    return {
        "数据监督源": f"""你是{stock_name}({code})的数据监督源。
数据：{{{{context[:4000]}}}}
检查项：日线行数/日期范围/最新价、行情价vs日线收盘交叉验证、资金流向、技术指标、财务数据、新闻覆盖度、Context总字符数
输出：
**数据质量评级**: A/B/C
**检查结果**: 每项逐一列出
**交叉验证**: 差异%
**数据可用性结论**:""",

        "技术分析师": f"""你是{stock_name}({code})的技术分析师。
数据：{{context}}
输出：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**技术要点**: （至少5条）""",

        "基本面分析师": f"""你是{stock_name}({code})的基本面分析师。
{fund_focus}
数据：{{context}}
输出：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**基本面要点**: （至少5条）""",

        "情绪分析师": f"""你是{stock_name}({code})的资金情绪分析师。
数据：{{context}}
输出：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**情绪要点**: （至少4条）""",

        "新闻分析师": f"""你是{stock_name}({code})的新闻分析师。
数据：{{context}}
输出：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**新闻要点**: （至少4条）""",

        "宏观策略师": f"""你是{stock_name}({code})的宏观策略师。
参考研报观点。数据：{{context}}
输出：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**宏观要点**: （至少4条）""",

        "激进风控": f"""你是{stock_name}({code})的激进风控（看多角度）。
{bull_focus}
数据：{{context}}
输出：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**核心看多逻辑**: （至少4条）
**仓位建议**: X%
**入场/止损/目标**: X / X / X""",

        "保守风控": f"""你是{stock_name}({code})的保守风控。
{bear_focus}
数据：{{context}}
输出：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**核心风险**: （至少4条）
**仓位建议**: X%""",

        "中性风控": f"""你是{stock_name}({code})的中性风控。
数据：{{context}}
输出：
**综合评分**: X/10
**操作建议**: 买入/观望/卖出
**看多因素**: （至少3条）
**看空因素**: （至少3条）
**折中方案**:""",
    }
