#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三委员会 — 投决会辩论
Round 1: 多头 vs 空头 对攻
Round 2: 仲裁员（独立第三方）终裁（读取已有的风险委员会结果）

风险委员会结论来自 fetch_template.py 第二阶段输出，不再重复调用。
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

# ====== 读9Agent输出 ======
agent_results = {}
agent_names = ["技术分析师","基本面分析师","情绪分析师","新闻分析师","多头","空头","激进风控","保守风控","中性风控","仲裁员"]
for name in agent_names:
    fp = os.path.join(AGENT_DIR, f"agent_{name}.md")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            agent_results[name] = f.read()
    else:
        agent_results[name] = ""

# 从9Agent分析目录读取已有的风险委员会结果
risk_committee_text = ""
risk_comm_ff = os.path.join(AGENT_DIR, "风险委员会汇总.md")
if os.path.exists(risk_comm_ff):
    with open(risk_comm_ff, "r", encoding="utf-8") as f:
        risk_committee_text = f.read()
    print(f"  已读取风险委员会汇总: {len(risk_committee_text)} chars")
else:
    # 降级：逐个读独立Agent文件
    risk_parts = []
    for rn in ["激进风控","保守风控","中性风控"]:
        rfp = os.path.join(AGENT_DIR, f"agent_{rn}.md")
        if os.path.exists(rfp):
            with open(rfp, "r", encoding="utf-8") as f:
                risk_parts.append(f"## {rn}\n{f.read()[:2000]}")
    risk_committee_text = "\n\n".join(risk_parts)
    print(f"  降级读取个人风险文件: {len(risk_committee_text)} chars")

# 现价
current_price = "?"
quote_fp = os.path.join(DATA_BASE, "data", "行情.txt")
if os.path.exists(quote_fp):
    with open(quote_fp, "r", encoding="utf-8") as f:
        qtxt = f.read()
    m = re.search(r'最新(?:价格|价|收盘价|收盘)[：:\s]*([\d.]+)', qtxt)
    if m: current_price = m.group(1)
if current_price == "?": current_price = "0"

try:
    profit_pct = f"{(float(current_price)/COST - 1)*100:.1f}" if float(COST) > 0 else "N/A"
except: profit_pct = "N/A"

print(f"现价: {current_price}, 成本: {COST}, 浮盈: {profit_pct}%")

# ====== Context ======
DATA_DIR = os.path.join(DATA_BASE, "data")
ctx_parts = []
for fn in ["行情.txt","资金流向.txt","技术指标.txt","利润表.txt","资产负债表.txt","现金流量表.txt","新闻.txt","研报.txt"]:
    fp = os.path.join(DATA_DIR, fn)
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            txt = f.read()[:2000]
        if len(txt) > 50: ctx_parts.append(f"【{fn}】\n{txt}")
data_ctx = "\n\n".join(ctx_parts[:3])

full_agent_text = ""
for name in ["技术分析师","基本面分析师","情绪分析师","新闻分析师","多头","空头","激进风控","保守风控","中性风控"]:
    txt = agent_results.get(name, "")[:2000]
    if txt: full_agent_text += f"\n【{name}】\n{txt}\n"

debate_ctx = f"""{STOCK}({CODE}) 辩论上下文 {TODAY}
──────────────────────
用户成本: {COST} HKD
现价: {current_price} HKD
浮盈: {profit_pct}%

核心数据：
{data_ctx[:2000]}

各分析师意见：
{full_agent_text[:8000]}
"""

# ====== Round 1: 多头 vs 空头 对攻 ======
print("\n=== Round 1: 多头 vs 空头 对攻 ===")

bull_prompt = f"""你是{STOCK}({CODE})的**多头辩手**。

你正在和空头辩手辩论「要不要买入{STOCK}」。你的职责是竭尽全力证明"应该买入"。

{debate_ctx}

**规则**：
1. 你的评分必须 ≥ 7/10（否则你就不配叫多头）
2. 给出4-5条有力的看多逻辑
3. 要足够激进——保守派觉得太夸张，说明你在认真工作

输出格式：
**综合评分（越高越应买入）**: X/10
**核心看多逻辑**: (4-5条)
1. ...
2. ...
**仓位建议**: X%
**一句话说服对手**:"""

bear_prompt = f"""你是{STOCK}({CODE})的**空头辩手**。

你正在和多头辩手辩论「要不要买入{STOCK}」。你的职责是竭尽全力证明"不应该买入"。

{debate_ctx}

**规则**：
1. 你的评分必须 ≤ 3/10（否则你就不配叫空头）
2. 给出4-5条尖锐的看空逻辑
3. 要足够悲观——多头觉得你在散布恐慌，说明你在认真工作

输出格式：
**综合评分（越高越应买入）**: X/10
**核心看空逻辑**: (4-5条)
1. ...
2. ...
**仓位建议**: X%
**一句话警告投资者**:"""

results = {}
for role, prompt in [("多头", bull_prompt), ("空头", bear_prompt)]:
    print(f"  {role} 思考中...", end=" ", flush=True)
    ans = call_r1(prompt)
    results[role] = ans
    with open(os.path.join(DEBATE_DIR, f"辩论_round1_{role}.md"), "w", encoding="utf-8") as f:
        f.write(f"# {role} 初辩\n\n{ans}")
    print(f" {len(ans)} chars")

# ====== Round 2: 仲裁员终裁 ======
print("\n=== Round 2: 仲裁员终裁 ===")

# 提取9Agent评分
scores_summary = ""
for name in agent_names:
    txt = agent_results.get(name,"")
    m = re.search(r'\*\*综合评分\*\*\s*:\s*([\d.]+)', txt)
    m2 = re.search(r'\*\*操作建议\*\*\s*:\s*([^\n]+)', txt)
    sc = m.group(1) if m else "?"
    act = m2.group(1).strip()[:10] if m2 else "?"
    scores_summary += f"\n{name}: {sc}/10 → {act}"

arbiter_prompt = f"""你是{STOCK}({CODE})的**独立仲裁员**。你不在辩论中站队，你是终裁者。

你已经完整听取了以下所有声音：

**9Agent初评汇总：**
{scores_summary}

**多头辩手观点：**
{results['多头'][:2000]}

**空头辩手观点：**
{results['空头'][:2000]}

**风险委员会评审（来自三委员会分析阶段）：**
{risk_committee_text[:5000]}

用户当前成本: {COST} HKD
现价: {current_price} HKD
浮盈: {profit_pct}%

**决策问题：要不要买入{STOCK}？**

你的职责：独立做出最终裁决。参考所有意见但不受任何一方支配。

输出格式：
**综合评分（越高越应买入）**: X/10
**最终操作**: 买入/观望/不买
**仓位比例（如买入）**: X%
**入场价格**: 
**止损价格**: 
**目标价格**: 
**驳斥了谁的观点**:  (300-400字)
**理由综述**: (400-600字)
**后续操作提示**:"""

print("  仲裁员 思考中...", end=" ", flush=True)
arbiter_final = call_r1(arbiter_prompt)
results["仲裁员"] = arbiter_final
with open(os.path.join(DEBATE_DIR, "辩论_终裁.md"), "w", encoding="utf-8") as f:
    f.write(f"# {STOCK} — 仲裁员终裁\n\n{arbiter_final}")
print(f" {len(arbiter_final)} chars")

# ====== 汇总输出 ======
print(f"\n{'='*60}")
print(f"   {STOCK}({CODE}) 辩论结果")
print(f"{'='*60}")

for role in ["多头","空头"]:
    txt = results.get(role,"")
    m = re.search(r'综合评分[：:\s]*([\d.]+)', txt)
    act = re.search(r'(?:立场|操作建议|一句话[说服警告])[：:\s]*([^\n]+)', txt)
    act_t = act.group(1).strip()[:12] if act else "?"
    print(f"   {role:10s} | 评分: {(m.group(1) if m else '?'):4s} | {act_t}")

m_f = re.search(r'综合评分[：:\s]*([\d.]+)', arbiter_final)
act_f = re.search(r'最终操作[：:\s]*([^\n]+)', arbiter_final)
pos_f = re.search(r'仓位比例[：:\s]*([^\n,%]+)', arbiter_final)
ep_f = re.search(r'入场价格[：:\s]*([^\n,，]+)', arbiter_final)
sl_f = re.search(r'止损价格[：:\s]*([^\n,，]+)', arbiter_final)
tp_f = re.search(r'目标价格[：:\s]*([^\n,，]+)', arbiter_final)
print(f"\n🏆 仲裁员终裁:")
print(f"   评分: {m_f.group(1) if m_f else '?'} | 操作: {act_f.group(1).strip()[:10] if act_f else '?'}")
print(f"   仓位: {pos_f.group(1).strip()[:15] if pos_f else '?'}")
print(f"   入场: {ep_f.group(1).strip()[:20] if ep_f else '?'} | 止损: {sl_f.group(1).strip()[:20] if sl_f else '?'} | 目标: {tp_f.group(1).strip()[:20] if tp_f else '?'}")

print(f"\n✅ 辩论完成！")
print(f"  辩论目录: {DEBATE_DIR}")
