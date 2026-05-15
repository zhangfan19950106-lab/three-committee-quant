#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三委员会量化 — 多Agent三维协作分析系统

架构：
  研究委员会（4人并行）→ 风险委员会（3人并行）→ 投决会（3人并行）

规则体系：
1. [权限] 总指挥唯一调度入口，执行Agent只干活不辩解，监工只读不修改不指挥
2. [流程] 总指挥派任务→执行产出→监工审核→总指挥裁决
3. [重试] 上限2次，超限标记异常
4. [输出] 统一标签：【接收】【完成】【驳回】【通过】【异常】

使用方法：
  run_analysis.py --stock 美团 --code 03690.HK --cost 82.0 --position 0
  或
  run_analysis.py  # 交互式输入
"""

import os, sys, subprocess, json, re, textwrap, argparse
from datetime import datetime

# ===== 路径常量 =====
PYTHON = r"C:\Users\zhang\AppData\Local\Python\bin\python.exe"
BASE_DIR = r"C:\Users\zhang\.qclaw\workspace"
OUT_DIR = r"C:\Users\zhang\Desktop\TradingAgent报告存放"
FETCH_SCRIPT = os.path.join(BASE_DIR, "fetch_template.py")
DEBATE_SCRIPT = os.path.join(BASE_DIR, "run_xiaomi_debate.py")

# ===== 默认值（交互模式可改）=====
DEFAULT_STOCK = "美团"
DEFAULT_CODE = "03690.HK"
DEFAULT_COST = 82.0
DEFAULT_POSITION = 0
DEFAULT_FEE = 120
MAX_RETRY = 2

TAG_RECV = "【接收】"
TAG_DONE = "【完成】"
TAG_REJECT = "【驳回】"
TAG_PASS = "【通过】"
TAG_ERROR = "【异常】"
TAG_DISPATCH = "【派遣】"


def eprint(msg):
    print(f"[龙虾 @ {datetime.now().strftime('%H:%M:%S')}] {msg}")


def generate_and_write_script(src_file: str, out_file: str, replacements: dict):
    """生成替换变量后的脚本并写入"""
    content = open(src_file, encoding="utf-8").read()
    for key, val in replacements.items():
        if isinstance(val, str):
            content = content.replace(key, val)
        elif isinstance(val, (int, float)):
            content = content.replace(key, str(val))
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(content)
    return len(content)


def run_script(script_path: str, timeout: int = 300, label: str = "") -> dict:
    """执行脚本，返回结构化输出"""
    short = os.path.basename(script_path)
    eprint(f"{TAG_DISPATCH} {label or short}  (timeout={timeout}s)")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        r = subprocess.run([PYTHON, "-u", script_path], capture_output=True, text=True, timeout=timeout, env=env)
        return {
            "ok": r.returncode == 0,
            "code": r.returncode,
            "stdout": r.stdout,
            "stderr": r.stderr[-1000:],
            "script": short,
        }
    except subprocess.TimeoutExpired:
        eprint(f"{TAG_ERROR} {short} 超时({timeout}s)")
        return {"ok": False, "code": -1, "stdout": "", "stderr": f"Timeout ({timeout}s)", "script": short}
    except Exception as e:
        eprint(f"{TAG_ERROR} {short} 异常: {e}")
        return {"ok": False, "code": -2, "stdout": "", "stderr": str(e), "script": short}


def extract_key_lines(output: str):
    """从Agent输出中抽取关键行"""
    lines = []
    for line in output.split("\n"):
        if any(kw in line for kw in ["评分", "建议", "终裁", "报告目录", "监工", "评级", "审计", "通过", "驳回", "OK!"]):
            lines.append(line.strip())
    return lines


def check_supervisor(run_output: str) -> dict:
    """
    监工审核：从执行输出中提取监工结论，而不是独立运行一个审核脚本
    （当前fetch_template已内嵌监工，未来可拆为独立supervisor.py）
    """
    # 提取监工评级
    rating = "?"
    m = re.search(r"监工评级:\s*(\S+)", run_output)
    if m:
        rating = m.group(1)

    # 提取打回记录
    rejects = run_output.count("打回")
    
    # 提取回避措辞（仅限严重回避—无评分/无建议，忽略模糊措辞如「不确定」）
    evasions = []
    for m in re.finditer(r"回避措辞[「「\"]*([^」\"\n]+)", run_output):
        evasion_word = m.group(1)
        # 模糊/不确定类措辞降低为警告，不导致打回
        if evasion_word not in ("不确定", "不明确", "不好说", "说不准"):
            evasions.append(evasion_word)
    
    # 检查缺失字段（更严格的拒绝条件）
    missing_fields = []
    for m in re.finditer(r"缺少[「「\"]*([^」\"\n]+)", run_output):
        missing_fields.append(m.group(1))
    
    has_critical_missing = len(missing_fields) >= 2  # 2个以上字段缺失才打回
    has_evasions = len(evasions) >= 2  # 2个以上严重回避才打回
    
    # 评级判定：C级或以下直接打回
    grade_pass = rating in ("A", "A+", "B+", "B", "S")
    is_pass = grade_pass and (not has_critical_missing) and (not has_evasions)
    
    return {
        "rating": rating,
        "rejects": rejects,
        "evasions": evasions,
        "missing_fields": missing_fields,
        "pass": is_pass,
    }


def extract_verdict(debate_output: str) -> dict:
    """从辩论输出提取终裁结论"""
    v = {"score": "?", "action": "?", "position": "?", "entry": "?", "stop": "?", "target": "?", "reason": ""}
    m = re.search(r"综合评分[^0-9]*([\d.]+)/?\s*10", debate_output)
    if m:
        v["score"] = m.group(1)
    
    m = re.search(r"(?:最终操作|最终建议)[：:\s]*([^\n.。]+)", debate_output)
    if m:
        act = m.group(1).strip()
        # 去掉可能的markdown标记
        act = re.sub(r'^\*{1,2}\s*', '', act)
        v["action"] = act[:20]
    
    for key, pattern in [
        ("position", r"仓位(?:比例|建议)?[^：:\n]*[：:]\s*([^\n,，%]+)"),
        ("entry", r"入场[价格价]*[^：:\n]*[：:]\s*([^\n,，]+)"),
        ("stop", r"止损[价格价]*[^：:\n]*[：:]\s*([^\n,，]+)"),
        ("target", r"目标[价格价]*[^：:\n]*[：:]\s*([^\n,，]+)"),
    ]:
        m = re.search(pattern, debate_output)
        if m:
            txt = m.group(1).strip()[:40]
            txt = re.sub(r'^\*{1,2}\s*', '', txt)
            v[key] = txt
    
    return v


def print_summary(stock, code, agent_results, verdict):
    """打印最终汇总"""
    sep = "=" * 60
    print()
    print(sep)
    print(f"  🏁 {stock}({code}) — 最终分析报告")
    print(sep)

    # Phase 1: 投票汇总
    print()
    print(f"  📊 10 Agent 投票")
    for line in agent_results:
        print(f"    {line.strip()}")
    
    # Phase 2: 仲裁员终裁
    print()
    def clean_val(key, default='?'):
        """清理markdown标记和多余括号"""
        t = verdict.get(key, default)
        t = re.sub(r'^[*:：\s]+', '', t)
        t = re.sub(r'[*]{1,2}', '', t)
        t = t.strip(' (（').strip()
        return t if t else default
    print(f"  💬 仲裁员终裁")
    print(f"    评分: {verdict.get('score','?')}/10")
    print(f"    操作: {clean_val('action')}")
    print(f"    仓位: {clean_val('position')}")
    print(f"    入场: {clean_val('entry')}")
    print(f"    止损: {clean_val('stop')}")
    print(f"    目标: {clean_val('target')}")
    print(f"    {'=' * 40}")
    print()


def main():
    parser = argparse.ArgumentParser(description="龙虾总指挥 — 多Agent分析调度")
    parser.add_argument("--stock", default=DEFAULT_STOCK)
    parser.add_argument("--code", default=DEFAULT_CODE)
    parser.add_argument("--cost", type=float, default=DEFAULT_COST)
    parser.add_argument("--position", type=int, default=DEFAULT_POSITION)
    parser.add_argument("--fee", type=float, default=DEFAULT_FEE)
    args = parser.parse_args()

    stock = args.stock
    code = args.code
    cost = args.cost
    position = args.position
    fee = args.fee
    today = datetime.now().strftime("%Y%m%d")

    print()
    eprint(f"{TAG_RECV} 任务: {stock}({code}), 成本={cost}, 持仓={position}")
    print()

    # ===== Phase 1: 执行9Agent分析 =====
    replacements = {
        'STOCK = "小米"': f'STOCK = "{stock}"',
        'CODE = "01810.HK"': f'CODE = "{code}"',
        "COST = 33.70": f"COST = {cost}",
        "POSITION = 0": f"POSITION = {position}",
        "FEE_PER_TRADE = 0": f"FEE_PER_TRADE = {fee}",
    }

    # 重试循环
    analysis_ok = False
    analysis_out = ""
    report_dir = ""
    retries = 0

    while retries <= MAX_RETRY:
        gen_script = os.path.join(BASE_DIR, f"_gen_{stock}.py")
        generate_and_write_script(FETCH_SCRIPT, gen_script, replacements)

        result = run_script(gen_script, timeout=300, label=f"9Agent分析 ({stock})")
        analysis_out = result.get("stdout", "")

        if not result.get("ok"):
            eprint(f"{TAG_ERROR} 分析进程异常(code={result.get('code')})")
            eprint(f"  stderr: {result.get('stderr','')[:500]}")
            retries += 1
            if retries <= MAX_RETRY:
                eprint(f"重试 ({retries}/{MAX_RETRY})...")
            continue

        # 监工审核（从输出提取）
        supervisor = check_supervisor(analysis_out)
        key_lines = extract_key_lines(analysis_out)
        report_dir_m = re.search(r"报告目录: (.+)", analysis_out)
        if report_dir_m:
            report_dir = report_dir_m.group(1).strip()
        eprint(f"监工评级: {supervisor['rating']}, 打回={supervisor['rejects']}次, 回避={len(supervisor['evasions'])}次")

        if supervisor["pass"]:
            analysis_ok = True
            eprint(f"{TAG_PASS} 监工审核通过")
            break
        else:
            reasons = []
            if supervisor["missing_fields"]:
                reasons.append(f"缺失字段: {', '.join(supervisor['missing_fields'])}")
            if supervisor["evasions"]:
                reasons.append(f"严重回避: {', '.join(supervisor['evasions'])}")
            if not supervisor["pass"] and supervisor["rating"] not in ("A", "A+", "B+", "B", "S"):
                reasons.append(f"评级{supervisor['rating']}")
            reason_str = "; ".join(reasons)
            eprint(f"{TAG_REJECT} 监工审核不通过 ({reason_str})")
            retries += 1
            if retries <= MAX_RETRY:
                eprint(f"第{retries}次重试 (上限{MAX_RETRY}次)...")
            else:
                eprint(f"{TAG_ERROR} 重试{MAX_RETRY}次均未通过，标记异常")
                # 但仍然产出报告
                analysis_ok = True

    if not analysis_ok:
        eprint(f"{TAG_ERROR} 分析失败，终止流程")
        return

    eprint(f"{TAG_DONE} 9Agent分析完成 → {report_dir}")

    report_dir = report_dir or os.path.join(OUT_DIR, f"{stock}_{today}")
    eprint(f"  报告路径: {report_dir}")

    # ===== Phase 2: 辩论=多头vs空头→风险委员会→仲裁员 =====
    debate_replacements = {
        'STOCK = "小米"': f'STOCK = "{stock}"',
        'CODE = "01810.HK"': f'CODE = "{code}"',
        "COST = 33.70": f"COST = {cost}",
        "POSITION = 0": f"POSITION = {position}",
    }

    debate_script = os.path.join(BASE_DIR, f"_debate_{stock}.py")
    generate_and_write_script(DEBATE_SCRIPT, debate_script, debate_replacements)

    eprint(f"{TAG_DISPATCH} 投决会辩论-多头vs空头→仲裁员 ({stock})")
    debate_result = run_script(debate_script, timeout=500, label="辩论")

    # 哪怕辩论exit code非0，尝试从文件读终裁
    debate_ok = debate_result.get("ok", False)
    if not debate_ok:
        eprint(f"{TAG_ERROR} 辩论脚本异常(exit={debate_result.get('code','?')})，尝试从文件读取终裁...")
    else:
        eprint(f"{TAG_DONE} 辩论完成")

    # 提取仲裁员终裁（无论exit code如何，只要文件在就提取）
    verdict_output = ""
    debate_dir = os.path.join(report_dir, "辩论")
    verdict_file = os.path.join(debate_dir, "辩论_终裁.md")
    if os.path.exists(verdict_file):
        verdict_output = open(verdict_file, encoding="utf-8").read()
    else:
        verdict_output = debate_result.get("stdout", "")

    verdict = extract_verdict(verdict_output)

    # 即使文件存在也兜底
    if verdict["action"] == "?" or verdict["action"] == "辩论异常":
        # 尝试从more格式提取
        for alt_fn in ["辩论_round2_中性风控_终裁.md", "辩论_终裁.md"]:
            alt_path = os.path.join(debate_dir, alt_fn)
            if os.path.exists(alt_path):
                alt_txt = open(alt_path, encoding="utf-8").read()
                alt_v = extract_verdict(alt_txt)
                if alt_v["action"] != "?":
                    verdict = alt_v
                    break

    eprint(f"{TAG_PASS} 终裁: {verdict['score']}/10 → {verdict['action']} (仓位 {verdict['position']})")

    # ===== 输出汇总 =====
    print_summary(stock, code, extract_key_lines(analysis_out), verdict)

    # 写入最终摘要
    summary_path = os.path.join(report_dir, "_final_summary.json")
    summary = {
        "stock": stock,
        "code": code,
        "cost": cost,
        "timestamp": datetime.now().isoformat(),
        "agent_rating": supervisor.get("rating", "?"),
        "verdict_score": verdict["score"],
        "verdict_action": verdict["action"],
        "verdict_position": verdict["position"],
        "report_dir": report_dir,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    eprint(f"完整报告: {report_dir}")


if __name__ == "__main__":
    main()
