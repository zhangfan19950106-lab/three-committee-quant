#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小米集团(01810.HK) 三风控R1辩论 — 基于已有分析结果

问题：要不要买入小米？
"""
import json, os, sys, urllib.request, re, subprocess
from datetime import datetime

STOCK = "小米"
CODE = "01810.HK"
TODAY = datetime.now().strftime("%Y%m%d")
COST = 33.70
POSITION = 0
FEE_PER_TRADE = 120

DATA_BASE = rf"C:\Users\zhang\Desktop\TradingAgent报告存放\{STOCK}_{TODAY}"
AGENT_DIR = os.path.join(DATA_BASE, "9agent分析")
DEBATE_DIR = os.path.join(DATA_BASE, "辩论")
API_KEY = "sk-39f7fc15acbb42c78082beacdb4338c1"
API_URL = "https://api.deepseek.com/v1/chat/completions"

os.makedirs(DEBATE_DIR, exist_ok=True)

def call_r1(prompt, label="R1"):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-reasoner", "messages": [{"role": "user", "content": prompt}],
               "max_tokens": 4096}
    req = urllib.request.Request(API_URL, json.dumps(payload).encode(), headers, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    return r["choices"][0]["message"]["content"]

def call_model(prompt, temp=0.3):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}],
               "temperature": temp, "max_tokens": 4096}
    req = urllib.request.Request(API_URL, json.dumps(payload).encode(), headers, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=180).read())
    return r["choices"][0]["message"]["content"]

# ====== 读原有9Agent输出 ======
agent_results = {}
agent_names = ["技术分析师","基本面分析师","情绪分析师","新闻分析师","多头","空头","激进风控","保守风控","中性风控","组合经理"]
for name in agent_names:
    fp = os.path.join(AGENT_DIR, f"agent_{name}.md")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            agent_results[name] = f.read()
    else:
        agent_results[name] = ""

# 提取现价（从行情.txt读取，不依赖组合经理的入场价格字段）
current_price = "?"
quote_fp = os.path.join(DATA_BASE, "data", "行情.txt")
if os.path.exists(quote_fp):
    with open(quote_fp, "r", encoding="utf-8") as f:
        qtxt = f.read()
    m = re.search(r'最新(?:价格|价|收盘价|收盘)[：:\s]*([\d.]+)', qtxt)
    if not m:
        m = re.search(r'price[":}]*[：:\s]*([\d.]+)', qtxt, re.I)
    if not m:
        m = re.search(r'[最新价last][：:\s]*([\d.]+)', qtxt)
    if m:
        current_price = m.group(1)
if current_price == "?":
    current_price = "0"

try:
    profit_pct = f"{(float(current_price)/COST - 1)*100:.1f}" if COST > 0 else "N/A"
except:
    profit_pct = "N/A"
print(f"现价: {current_price}, 成本: {COST}, 浮盈: {profit_pct}%")

# ====== 构建context ======
# 从data目录读
DATA_DIR = os.path.join(DATA_BASE, "data")
ctx_parts = []
for fn in ["行情.txt","资金流向.txt","技术指标.txt","利润表.txt","资产负债表.txt","现金流量表.txt","新闻.txt","研报.txt"]:
    fp = os.path.join(DATA_DIR, fn)
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            txt = f.read()[:2000]
        if len(txt) > 50:
            ctx_parts.append(f"【{fn}】\n{txt}")

full_agent_text = ""
for name in ["技术分析师","基本面分析师","情绪分析师","新闻分析师","多头","空头","激进风控","保守风控","中性风控"]:
    txt = agent_results.get(name, "")[:2000]
    if txt: full_agent_text += f"\n【{name}】\n{txt}\n"

risk_text = full_agent_text[:10000]  # 全部给风控看
data_ctx = "\n\n".join(ctx_parts[:3])

debate_ctx = f"""{STOCK}({CODE}) 辩论上下文 {TODAY}
──────────────────────
用户成本: {COST} HKD
现价: {current_price} HKD
浮盈: {profit_pct}%
问题: 现在要不要买入？

核心数据：
{data_ctx[:2000]}

各分析师意见：
{full_agent_text[:8000]}
"""

# ====== Round 1: 三风控初评 ======
print("=== Round 1: 三风控初评 ===")

aggressive_prompt = f"""你是{STOCK}({CODE})的**激进风控官**（看多持有立场）。

你的立场：**应该买入，机会大于风险**。

{debate_ctx}

输出格式：
**综合评分（越高越应买入）**: X/10
**立场**: 买入/观望/不买
**核心论据**: (4-5条)
1. ...
2. ...
**仓位建议**: X%"""

conservative_prompt = f"""你是{STOCK}({CODE})的**保守风控官**（看空卖出立场）。

你的立场：**不应该买入，风险大于机会**。

{debate_ctx}

输出格式：
**综合评分（越高越应买入）**: X/10
**立场**: 买入/观望/不买
**核心论据**: (4-5条)
1. ...
2. ...
**仓位建议**: X%"""

neutral_prompt = f"""你是{STOCK}({CODE})的**中性风控官**（平衡立场）。

给出折中方案。

{debate_ctx}

输出格式：
**综合评分（越高越应买入）**: X/10
**立场**: 买入/观望/不买
**看多理由**: (2-3条)
**看空理由**: (2-3条)
**折中方案**:"""

results_r1 = {}
for role, prompt in [("激进风控", aggressive_prompt), ("保守风控", conservative_prompt), ("中性风控", neutral_prompt)]:
    print(f"  {role} 思考中...", end=" ", flush=True)
    ans = call_r1(prompt)
    results_r1[role] = ans
    with open(os.path.join(DEBATE_DIR, f"辩论_round1_{role}.md"), "w", encoding="utf-8") as f:
        f.write(f"# {role} 初评\n\n{ans}")
    print(f" {len(ans)} chars")

# ====== Round 2: 互驳 ======
print("\n=== Round 2: 互驳辩论 ===")

rebut_aggro = call_r1(f"""你是{STOCK}的激进风控（买入立场）。保守风控说不能买，请你驳斥。

保守风控论点：
{results_r1['保守风控'][:2500]}

你之前的论点：
{results_r1['激进风控'][:2000]}

输出：直接逐条驳斥对方，不要重述自己观点。""",
label="激进反驳")

rebut_conserva = call_r1(f"""你是{STOCK}的保守风控（不买立场）。激进风控说应该买，请你驳斥。

激进风控论点：
{results_r1['激进风控'][:2500]}

你之前的论点：
{results_r1['保守风控'][:2000]}

输出：直接逐条驳斥对方，不要重述自己观点。""",
label="保守反驳")

rebut_neutral = call_r1(f"""你是{STOCK}的中性风控官。听完辩论后给最终折中方案。

激进（买入）：
{results_r1['激进风控'][:2000]}

保守（不买）：
{results_r1['保守风控'][:2000]}

激进反驳：
{rebut_aggro[:2000]}

保守反驳：
{rebut_conserva[:2000]}

输出：最终评分+折中方案""",
label="中性和解")

results_r2 = {"激进风控_反驳": rebut_aggro, "保守风控_反驳": rebut_conserva, "中性风控_终裁": rebut_neutral}
for name, txt in results_r2.items():
    with open(os.path.join(DEBATE_DIR, f"辩论_round2_{name}.md"), "w", encoding="utf-8") as f:
        f.write(f"# {name}\n\n{txt}")

# ====== 终裁 ======
print("\n=== 组合经理R1终裁 ===")

# 提取9Agent评分用于终裁
scores_summary = ""
for name in agent_names:
    txt = agent_results.get(name,"")
    m = re.search(r'\*\*综合评分\*\*\s*:\s*([\d.]+)', txt)
    m2 = re.search(r'\*\*操作建议\*\*\s*:\s*([^\n]+)', txt)
    sc = m.group(1) if m else "?"
    act = m2.group(1).strip()[:10] if m2 else "?"
    scores_summary += f"\n{name}: {sc}/10 → {act}"

pm_debate_prompt = f"""你是{STOCK}({CODE})投资委员会**组合经理**。你拥有最终决策权。

**决策问题：要不要买入？**

用户当前无仓位，成本参考{COST} HKD。
现价约{current_price} HKD。

**9Agent评分汇总（高分=倾向买入）：**
{scores_summary}

**辩论交锋：**
激进（买入）：
{results_r1['激进风控'][:2000]}

保守（不买）：
{results_r1['保守风控'][:2000]}

中性（折中）：
{rebut_neutral[:2000]}

激进驳保守：
{rebut_aggro[:2000]}

保守驳激进：
{rebut_conserva[:2000]}

现在，请做出最终决策。注意是「要不要买入」的问题。

输出格式：
**综合评分（越高越应买入）**: X/10
**最终操作**: 买入/观望/不买
**仓位比例（如买入）**: X%
**入场价格**: 
**止损价格**: 
**目标价格**: 
**理由综述**: (400-600字)
**后续操作提示**:"""

pm_final = call_r1(pm_debate_prompt)
with open(os.path.join(DEBATE_DIR, "辩论_终裁.md"), "w", encoding="utf-8") as f:
    f.write(f"# {STOCK}三风控R1辩论 — 组合经理终裁\n\n{pm_final}")
print(f" {len(pm_final)} chars")

# ====== 输出 ======
print(f"\n{'='*60}")
print(f"   {STOCK}({CODE}) 三风控R1辩论结果")
print(f"{'='*60}")
for role in ["激进风控","保守风控","中性风控"]:
    txt = results_r1.get(role,"")
    m = re.search(r'综合评分[：:\s]*([\d.]+)', txt)
    act = re.search(r'立场[：:\s]*([^\n]+)', txt)
    print(f"   {role:10s} | 评分: {(m.group(1) if m else '?'):4s} | 立场: {(act.group(1).strip()[:8] if act else '?')}")

m_f = re.search(r'综合评分[：:\s]*([\d.]+)', pm_final)
act_f = re.search(r'最终操作[：:\s]*([^\n]+)', pm_final)
pos_f = re.search(r'仓位比例[：:\s]*([^\n,%]+)', pm_final)
ep_f = re.search(r'入场价格[：:\s]*([^\n,，]+)', pm_final)
sl_f = re.search(r'止损价格[：:\s]*([^\n,，]+)', pm_final)
tp_f = re.search(r'目标价格[：:\s]*([^\n,，]+)', pm_final)
print(f"\n🏆 组合经理R1终裁:")
print(f"   评分: {m_f.group(1) if m_f else '?'} | 操作: {act_f.group(1).strip()[:10] if act_f else '?'}")
print(f"   仓位: {pos_f.group(1).strip()[:15] if pos_f else '?'}")
print(f"   入场: {ep_f.group(1).strip()[:20] if ep_f else '?'} | 止损: {sl_f.group(1).strip()[:20] if sl_f else '?'} | 目标: {tp_f.group(1).strip()[:20] if tp_f else '?'}")

print(f"\n✅ 辩论完成！")
print(f"  辩论目录: {DEBATE_DIR}")
