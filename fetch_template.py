#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小米集团(01810.HK) 10Agent分析 + 监工审计

V5标准架构（三会制）：
【研究委员会】技术/基本面/情绪/新闻 — 只给事实分析，不表态买入/卖出
【风险委员会】激进风控/保守风控/中性风控 — 评估风险，不直接建议买卖
【投决会】多头/空头/仲裁员 — 辩论并终裁

流程：数据采集 → 研究委员会 → 风险委员会 → 投决会辩论+仲裁
"""
import json, os, sys, urllib.request, re, time, subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
def safe_doc_recall2(resp):
    """Safely get docRecall from neo_doc response"""
    if not resp or not isinstance(resp, dict):
        return []
    data = resp.get("data", {})
    if not isinstance(data, dict):
        return []
    doc_data = data.get("docData", {})
    if not isinstance(doc_data, dict):
        return []
    return doc_data.get("docRecall", []) or []



STOCK = "小米"
CODE = "01810.HK"
TODAY = datetime.now().strftime("%Y%m%d")
COST = 33.70   # 用户持仓成本
POSITION = 0   # 当前无持仓（买前分析）
FEE_PER_TRADE = 120

DATA_BASE = rf"C:\Users\zhang\Desktop\TradingAgent报告存放\{STOCK}_{TODAY}"
DATA_DIR = os.path.join(DATA_BASE, "data")
AGENT_DIR = os.path.join(DATA_BASE, "9agent分析")
DEBATE_DIR = os.path.join(DATA_BASE, "辩论")
API_KEY = "sk-39f7fc15acbb42c78082beacdb4338c1"
API_URL = "https://api.deepseek.com/v1/chat/completions"
PYTHON = r'C:\Users\zhang\AppData\Local\Python\bin\python.exe'
NEO_SCRIPT = r'C:\Program Files\QClaw\resources\openclaw\config\skills\neodata-financial-search\scripts\query.py'

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(AGENT_DIR, exist_ok=True)
os.makedirs(DEBATE_DIR, exist_ok=True)

def neo(q):
    cmd = [PYTHON, '-u', NEO_SCRIPT, '--query', q, '--data-type', 'api']
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=90)
        raw = (r.stdout + r.stderr).decode('utf-8', errors='replace')
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception as e:
        print(f"  Neo ERR: {e}"); return {}

def neo_doc(q):
    cmd = [PYTHON, '-u', NEO_SCRIPT, '--query', q, '--data-type', 'doc']
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=90)
        raw = (r.stdout + r.stderr).decode('utf-8', errors='replace')
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception as e:
        print(f"  Doc ERR: {e}"); return {}

def call_model(prompt, temp=0.7):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}],
               "temperature": temp, "max_tokens": 4096}
    req = urllib.request.Request(API_URL, json.dumps(payload).encode(), headers, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=180).read())
    return r["choices"][0]["message"]["content"]

def call_r1(prompt):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-reasoner", "messages": [{"role": "user", "content": prompt}],
               "max_tokens": 4096}
    req = urllib.request.Request(API_URL, json.dumps(payload).encode(), headers, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    return r["choices"][0]["message"]["content"]

# ================== 数据采集 ==================
print(f"=== {STOCK}({CODE}) 数据采集 ===")

# 1) NeoData主查询
d = neo(f"{STOCK} {CODE} 今日行情 技术指标 资金流向 日线数据 {TODAY}")
items = d.get("data",{}).get("apiData",{}).get("apiRecall",[])
with open(os.path.join(DATA_DIR, "neodata.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(d, ensure_ascii=False, indent=2))
print(f"  主查询: {len(items)}条, neodata.json saved")

# 2) 日线
dl = neo(f"{STOCK} {CODE} 日线行情 历史数据 2026")
items_dl = dl.get("data",{}).get("apiData",{}).get("apiRecall",[])
daily_lines = []
for it in items_dl:
    c = it.get("content","")
    if len(c) > 200 and ("日期" in c or "收盘" in c or "ma" in c.lower()):
        daily_lines.append(c)
if not daily_lines:
    daily_lines.append("（NeoData无独立日线返回）")
daily_txt = "\n\n=====\n\n".join(daily_lines[:3])
with open(os.path.join(DATA_DIR, "daily_lines.txt"), "w", encoding="utf-8") as f:
    f.write(daily_txt)
print(f"  日线: {len(daily_txt)}B")

# 3) 三张报表
for fname, qstr in [("利润表", f"{STOCK} {CODE} 利润表 净利润 营收 2025 2026"),
                     ("资产负债表", f"{STOCK} {CODE} 资产负债表 资产 负债 权益 2025 2026"),
                     ("现金流量表", f"{STOCK} {CODE} 现金流量表 经营现金流 2025 2026")]:
    dd = neo(qstr)
    conts = [it.get("content","")[:3000] for it in dd.get("data",{}).get("apiData",{}).get("apiRecall",[])]
    txt = "\n\n=====\n\n".join(conts)
    with open(os.path.join(DATA_DIR, f"{fname}.txt"), "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"  {fname}: {len(txt)}B")

# 4) 技术指标
tech_lines = [it.get("content","") for it in items if "技术" in it.get("type","")]
with open(os.path.join(DATA_DIR, "技术指标.txt"), "w", encoding="utf-8") as f:
    f.write("\n\n".join(tech_lines[:3]))
print(f"  技术指标: {sum(len(l) for l in tech_lines[:3])}B")

# 5) 行情
quote_lines = [it.get("content","") for it in items if "basic" in it.get("type","") or "行情" in it.get("type","")]
with open(os.path.join(DATA_DIR, "行情.txt"), "w", encoding="utf-8") as f:
    f.write("\n\n".join(quote_lines[:3]))
print(f"  行情: {sum(len(l) for l in quote_lines[:3])}B")

# 6) 资金流向
fund_lines = [it.get("content","") for it in items if "资金" in it.get("type","")]
with open(os.path.join(DATA_DIR, "资金流向.txt"), "w", encoding="utf-8") as f:
    f.write("\n\n".join(fund_lines[:3]))
print(f"  资金流向: {sum(len(l) for l in fund_lines[:3])}B")

# 7) 新闻
nd = neo_doc(f"{STOCK} {CODE} 新闻 公告 {TODAY} today")
docs_raw = safe_doc_recall2(nd)
all_news = []
for dl in docs_raw:
    for d2 in dl.get("docList",[]):
        all_news.append(f"【{d2.get('title','')}】\n{d2.get('content','')[:600]}")
news_text = "\n\n".join(all_news[:8])
with open(os.path.join(DATA_DIR, "新闻.txt"), "w", encoding="utf-8") as f:
    f.write(news_text)
print(f"  新闻: {len(news_text)}B, {len(all_news)}条")

# 8) 研报
yr = neo_doc(f"{STOCK} {CODE} 研报 评级 目标价 2026")
yr_items = []
for dl in safe_doc_recall2(yr):
    for d2 in dl.get("docList",[]):
        yr_items.append(f"【{d2.get('title','')}】\n{d2.get('content','')[:500]}")
yr_txt = "\n\n".join(yr_items[:5])
with open(os.path.join(DATA_DIR, "研报.txt"), "w", encoding="utf-8") as f:
    f.write(yr_txt)
print(f"  研报: {len(yr_txt)}B, {len(yr_items)}条")

# 跳过元宝搜索（NeoData新闻已够）
yb_text = ""
if len(news_text) < 500:
    # NeoData新闻不足，用元宝搜索补
    prosearch = r'C:\Program Files\QClaw\resources\openclaw\config\skills\online-search\scripts\prosearch.cjs'
    node_exe = r'C:\Program Files\nodejs\node.exe'
    import textwrap
    
    queries = [
        f'{STOCK} {CODE} 最新消息 2026',
        f'{STOCK} {CODE} 业绩 财报',
        f'{STOCK} {CODE} 新闻',
    ]
    all_raw = []
    for kw in queries:
        try:
            r = subprocess.run([node_exe, prosearch, '--keyword', kw, '--freshness', '30d', '--industry', 'news'],
                               capture_output=True, timeout=30, text=True, errors='replace')
            raw = r.stdout + r.stderr
            all_raw.append(raw[:3000])
            print(f'.', end='', flush=True)
        except Exception as e:
            print(f'x', end='', flush=True)
    print()
    combined = '\n\n---\n\n'.join(all_raw)
    yb_fp = os.path.join(DATA_DIR, "新闻_元宝搜索.txt")
    with open(yb_fp, "w", encoding="utf-8") as f:
        f.write(combined[:8000])
    yb_text = combined[:4000]
    print(f'  元宝补充: {len(combined)}c')

# ================== NeoData并行查询 ==================
def fetch_neodata_parallel():
    """并行执行多个NeoData查询"""
    queries = {
        "行情": f"{STOCK} {CODE} 今日行情 技术指标 资金流向 日线数据 {TODAY}",
        "日线": f"{STOCK} {CODE} 日线行情 历史数据 2026",
        "利润表": f"{STOCK} {CODE} 利润表 净利润 营收 2025 2026",
        "资产负债表": f"{STOCK} {CODE} 资产负债表 资产 负债 权益 2025 2026",
        "现金流量表": f"{STOCK} {CODE} 现金流量表 经营现金流 2025 2026",
        "研报": f"{STOCK} {CODE} 研报 评级 目标价 2026",
    }
    results = {}
    total = len(queries)
    print(f"  并行执行{total}个NeoData查询...")
    with ThreadPoolExecutor(max_workers=total) as ex:
        futures = {ex.submit(neo, q): k for k, q in queries.items()}
        for f in as_completed(futures):
            k = futures[f]
            try:
                results[k] = f.result()
                items = results[k].get("data",{}).get("apiData",{}).get("apiRecall",[])
                print(f"  [{k}]: {len(items)}条")
            except Exception as e:
                print(f"  [{k}]: ERROR {e}")
                results[k] = {}
                
    # 主查询是行情（含技术+资金+部分日线）
    main_query = results.get("行情", {})
    items = main_query.get("data",{}).get("apiData",{}).get("apiRecall",[])
    with open(os.path.join(DATA_DIR, "neodata.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(main_query, ensure_ascii=False, indent=2))
    
    # 处理各查询结果到文件
    # 日线
    dl = results.get("日线", {})
    items_dl = dl.get("data",{}).get("apiData",{}).get("apiRecall",[])
    daily_lines = [it.get("content","") for it in items_dl if len(it.get("content","")) > 200]
    if not daily_lines:
        daily_lines.append("（NeoData无独立日线返回）")
    daily_txt = "\n\n=====\n\n".join(daily_lines[:3])
    with open(os.path.join(DATA_DIR, "daily_lines.txt"), "w", encoding="utf-8") as f:
        f.write(daily_txt)
    
    # 三张报表
    for name in ["利润表", "资产负债表", "现金流量表"]:
        dd = results.get(name, {})
        conts = [it.get("content","")[:3000] for it in dd.get("data",{}).get("apiData",{}).get("apiRecall",[])]
        txt = "\n\n=====\n\n".join(conts)
        with open(os.path.join(DATA_DIR, f"{name}.txt"), "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"  {name}: {len(txt)}B")
    
    # 研报
    yr = results.get("研報", results.get("研报", {}))
    yr_items = []
    for dl2 in safe_doc_recall2(yr):
        for d2 in dl2.get("docList",[]):
            yr_items.append(f"【{d2.get('title','')}】\n{d2.get('content','')[:500]}")
    yr_txt = "\n\n".join(yr_items[:5])
    with open(os.path.join(DATA_DIR, "研报.txt"), "w", encoding="utf-8") as f:
        f.write(yr_txt)
    print(f"  研报: {len(yr_txt)}B")
    
    return items, daily_txt, yr_txt

# 替换原来的串行数据采集
print(f"=== {STOCK}({CODE}) 数据采集（并行） ===")
items, daily_txt, yr_txt = fetch_neodata_parallel()

# 技术指标（从主查询结果提取）
tech_lines = [it.get("content","") for it in items if "技术" in it.get("type","")]
with open(os.path.join(DATA_DIR, "技术指标.txt"), "w", encoding="utf-8") as f:
    f.write("\n\n".join(tech_lines[:3]))
print(f"  技术指标: {sum(len(l) for l in tech_lines[:3])}B")

# 行情
quote_lines = [it.get("content","") for it in items if "basic" in it.get("type","") or "行情" in it.get("type","")]
with open(os.path.join(DATA_DIR, "行情.txt"), "w", encoding="utf-8") as f:
    f.write("\n\n".join(quote_lines[:3]))
print(f"  行情: {sum(len(l) for l in quote_lines[:3])}B")

# 资金流向
fund_lines = [it.get("content","") for it in items if "资金" in it.get("type","")]
with open(os.path.join(DATA_DIR, "资金流向.txt"), "w", encoding="utf-8") as f:
    f.write("\n\n".join(fund_lines[:3]))
print(f"  资金流向: {sum(len(l) for l in fund_lines[:3])}B")

# 新闻（从NeoData doc查询）
nd = neo_doc(f"{STOCK} {CODE} 新闻 公告 {TODAY} today")
docs_raw = safe_doc_recall2(nd)
all_news = []
for dl in docs_raw:
    for d2 in dl.get("docList",[]):
        all_news.append(f"【{d2.get('title','')}】\n{d2.get('content','')[:600]}")
news_text = "\n\n".join(all_news[:8])
with open(os.path.join(DATA_DIR, "新闻.txt"), "w", encoding="utf-8") as f:
    f.write(news_text)
print(f"  新闻: {len(news_text)}B, {len(all_news)}条")

# ================== Context构建 ==================
data_in_memory = {}
for it in items:
    t = it.get("type","")
    c = it.get("content","")
    if "basic" in t or "行情" in t: data_in_memory["行情"] = c[:2000]
    elif "技术" in t: data_in_memory["技术面"] = c[:2000]
    elif "资金" in t: data_in_memory["资金流向"] = c[:1000]
    elif "财务" in t or "profit" in t.lower(): data_in_memory["财务数据"] = c[:3000]
data_in_memory["日线"] = daily_txt[:2000]
for k in ["利润表","资产负债表","现金流量表"]:
    fp = os.path.join(DATA_DIR, f"{k}.txt")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            data_in_memory[k] = f.read()[:2000]
if news_text: data_in_memory["新闻"] = news_text[:4000]
if yr_txt: data_in_memory["研报"] = yr_txt[:2000]

if news_text: data_in_memory["新闻"] = news_text[:4000]
if yr_txt: data_in_memory["研报"] = yr_txt[:2000]
if yb_text: data_in_memory["元宝搜索"] = yb_text

print(f"\n数据源检查:")
for k in ["行情","技术面","资金流向","日线","利润表","资产负债表","现金流量表","新闻","研报"]:
    v = data_in_memory.get(k,"")
    print(f"  [{'YES' if len(v)>50 else 'NO'}] {k}: {len(v)} chars")

local_files = sorted([(fn, os.path.getsize(os.path.join(DATA_DIR, fn)))
    for fn in os.listdir(DATA_DIR) if os.path.isfile(os.path.join(DATA_DIR, fn))])
data_audit_txt = "\n".join([
    f"data文件夹: {DATA_DIR}",
    f"文件数: {len(local_files)}",
    *[f"  {fn} ({sz} bytes)" for fn, sz in local_files]
])

ctx_parts = [f"## 本地数据审计\n{data_audit_txt}"]
for k in ["行情","资金流向","技术面","日线","利润表","资产负债表","现金流量表","新闻","研报"]:
    if k in data_in_memory and len(data_in_memory[k]) > 50:
        ctx_parts.append(f"### {k}\n{data_in_memory[k]}")
ctx_str = "\n\n".join(ctx_parts)
print(f"\nContext: {len(ctx_str)} chars")

# ================== 9Agent ==================
print("\n=== 9Agent 并行分析 ===")

agents_prompts = {
    "技术分析师": f"""你是{STOCK}({CODE})**研究委员会**的技术分析师。

**职责**：只做事实分析，不表态买入/卖出。给出技术面的客观数据。

数据：{ctx_str[:4000]}

输出格式（只输出事实，不带买入/卖出建议）：
**技术面评分**: X/10（越高=技术形态越好）
**关键均线位置**: 
**MACD状态**: 
**KDJ/量能超买超卖**: 
**支撑位/阻力位**: 
**技术要点**: (5条)""",

    "基本面分析师": f"""你是{STOCK}({CODE})**研究委员会**的基本面分析师。

**职责**：只做事实分析，不表态买入/卖出。给出基本面的客观数据。

数据：{ctx_str[:4000]}

输出格式（只输出事实，不带买入/卖出建议）：
**基本面评分**: X/10（越高=基本面越扎实）
**盈利能力**: 
**资产负债状况**: 
**现金流**: 
**增长趋势**: 
**基本面要点**: (5条)""",

    "情绪分析师": f"""你是{STOCK}({CODE})**研究委员会**的资金情绪分析师。

**职责**：只做事实分析，不表态买入/卖出。给出资金面、情绪面的客观数据。

数据：{ctx_str[:4000]}

输出格式（只输出事实，不带买入/卖出建议）：
**情绪面评分**: X/10（越高=情绪越积极）
**资金流向**: 
**主力/散户博弈**: 
**量能分析**: 
**情绪要点**: (4条)""",

    "新闻分析师": f"""你是{STOCK}({CODE})**研究委员会**的新闻分析师。

**职责**：只做事实分析，不表态买入/卖出。给出新闻面、事件驱动的客观数据。

数据：{ctx_str[:5000]}

输出格式（只输出事实，不带买入/卖出建议）：
**新闻面评分**: X/10（越高=新闻面越正面）
**核心事件**: 
**新闻要点**: (4条)""",

    "激进风控": f"""你是{STOCK}({CODE})**风险委员会**的激进风控官。

**职责**：风险委员会的一员。评估「如果买入，风险是否可控」。给出客观的风险评估，不直接建议买卖。

**评分规则：评分越高=机会越大/风险越低**

数据：{ctx_str[:4000]}

输出格式：
**风险评估评分**: X/10（越高=风险越小）
**机会评估**: (3-4条)
**可控风险**: (2-3条)
**不可控风险**: (2-3条)
**最大可接受仓位**: X%
**建议入场区间**:
**止损参考**:""",

    "保守风控": f"""你是{STOCK}({CODE})**风险委员会**的保守风控官。

**职责**：风险委员会的一员。评估「如果买入，最坏情况有多糟」。给出客观的最坏场景评估，不直接建议买卖。

**评分规则：评分越高=最坏场景越可接受**

数据：{ctx_str[:4000]}

输出格式：
**风险评估评分**: X/10（越高=最坏场景越能接受）
**极坏场景**: 
**不确定性评估**: 
**不可接受的损失**: 
**安全边界**:
**最大可接受仓位**: X%""",

    "中性风控": f"""你是{STOCK}({CODE})**风险委员会**的中性风控官（协调人）。

**职责**：风险委员会的协调者。综合激进和保守两方观点，给出委员会的总风险评估报告。不直接建议买卖。

**评分规则：评分越高=总体风险越低**

数据：{ctx_str[:4000]}

输出格式：
**委员会风险评估评分**: X/10（越高=风险越低）
**看多风险点**: (2-3条)
**看空风险点**: (2-3条)
**委员会总评**: 
**风险等级**: 高/中/低
**折中方案**: (不涉及买卖建议，只涉及风险控制)""",

    "多头": f"""你是{STOCK}({CODE})**投决会**的多头委员（纯看多立场）。

**职责**：投决会是最终决策机构，你是其中的看多力量。你的存在价值是给出令人信服的买入逻辑。

**评分规则：评分越高=越应该买入**

数据：{ctx_str[:4000]}

输出格式：
**综合评分（越高越应买入）**: X/10
**核心看多逻辑**: (4-5条)
1. ...
2. ...
**仓位建议**: X%
**买入理由一句话**:""",

    "空头": f"""你是{STOCK}({CODE})**投决会**的空头委员（纯看空立场）。

**职责**：投决会是最终决策机构，你是其中的看空力量。你的存在价值是找到致命弱点。

**评分规则：评分越高=越应该买入（空头评分低=强烈看空）**

数据：{ctx_str[:4000]}

输出格式：
**综合评分（越高越应买入）**: X/10
**核心看空逻辑**: (4-5条)
1. ...
2. ...
**仓位建议**: X%
**看空理由一句话**:""",

    "仲裁员": f"""你是{STOCK}({CODE})**投决会**的仲裁员（中立主席）。

**职责**：投决会是最终决策机构，你是中立主席。研究委员会（技术/基本面/情绪/新闻）已经给出了客观的4个角度的分析，风险委员会（激进/保守/中性风控）已经做了风险评估。现在，你听完了多头和空头的对攻，需要做出独立终止——给出「买/不买」的最终建议。

**评分规则：评分越高=越应该买入**

数据：{ctx_str[:5000]}

输出格式：
**综合评分（越高越应买入）**: X/10
**操作建议**: 买入/观望/不买
**投决会决策理由**: (300-400字，需要考虑多空双方观点的优劣)
**仓位建议（如买入）**: X%
**入场/止损/目标**:""",
}

agent_results = {}

# ====== 第一阶段：研究委员会（并行4人） ======
print(f"\n=== 第一阶段：研究委员会（技术/基本面/情绪/新闻） ===")
research_names = ["技术分析师","基本面分析师","情绪分析师","新闻分析师"]
research_prompts = {n: agents_prompts[n] for n in research_names}
print(f"  并行启动{len(research_prompts)}个研究委员会Agent...")
with ThreadPoolExecutor(max_workers=len(research_prompts)) as ex:
    futures = {ex.submit(call_model, p): name for name, p in research_prompts.items()}
    for f in as_completed(futures):
        name = futures[f]
        try:
            ans = f.result()
            agent_results[name] = ans
            with open(os.path.join(AGENT_DIR, f"agent_{name}.md"), "w", encoding="utf-8") as fout:
                fout.write(f"# {name} 分析\n\n{ans}\n")
            print(f"  [{name}]: {len(ans)} chars")
        except Exception as e:
            print(f"  [{name}]: ERROR {e}")

# 整理研究委员会报告摘要
research_summaries = []
for name in research_names:
    txt = agent_results.get(name, "")
    if txt:
        research_summaries.append(f"## {name}\n{txt[:1500]}")
research_overview = "\n\n".join(research_summaries)
research_file = os.path.join(AGENT_DIR, "研究委员会汇总.md")
with open(research_file, "w", encoding="utf-8") as f:
    f.write(f"# 研究委员会汇总 — {STOCK}({CODE})\n\n{research_overview}\n")
print(f"  研究委员会报告: {len(research_overview)} chars")

# ====== 第二阶段：风险委员会（3人并行）======
print(f"\n=== 第二阶段：风险委员会 ===")
risk_names = ["激进风控","保守风控","中性风控"]
risk_prompts = {}
research_ref = f"\n\n=====\n## 研究委员会分析参考（请先阅读）\n{research_overview[:2500]}\n=====\n请先仔细阅读以上研究委员会的技术面/基本面/情绪/新闻分析，再给出你的风险委员会评估。"
for name in risk_names:
    risk_prompts[name] = agents_prompts[name] + research_ref

print(f"  并行启动{len(risk_prompts)}个风险委员会Agent...")
with ThreadPoolExecutor(max_workers=len(risk_prompts)) as ex:
    futures = {ex.submit(call_model, p): name for name, p in risk_prompts.items()}
    for f in as_completed(futures):
        name = futures[f]
        try:
            ans = f.result()
            agent_results[name] = ans
            with open(os.path.join(AGENT_DIR, f"agent_{name}.md"), "w", encoding="utf-8") as fout:
                fout.write(f"# {name} 分析\n\n{ans}\n")
            print(f"  [{name}]: {len(ans)} chars")
        except Exception as e:
            print(f"  [{name}]: ERROR {e}")

# 整理风险委员会报告摘要
risk_summaries = []
for name in risk_names:
    txt = agent_results.get(name, "")
    if txt:
        risk_summaries.append(f"## {name}\n{txt[:1500]}")
risk_overview = "\n\n".join(risk_summaries)
risk_file = os.path.join(AGENT_DIR, "风险委员会汇总.md")
with open(risk_file, "w", encoding="utf-8") as f:
    f.write(f"# 风险委员会汇总 — {STOCK}({CODE})\n\n{risk_overview}\n")
print(f"  风险委员会报告: {len(risk_overview)} chars")

# ====== 第三阶段：投决会（多头/空头/仲裁员，3人并行，读研究+风险）======
print(f"\n=== 第三阶段：投决会 ===")
vote_names = ["多头","空头","仲裁员"]
vote_prompts = {}
vote_ref = (f"\n\n=====\n## 研究委员会分析参考\n{research_overview[:2000]}\n"
            f"\n## 风险委员会分析参考\n{risk_overview[:2000]}\n"
            "=====\n请先仔细阅读以上研究委员会和风险委员会的全部分析，再给出你的投决会观点。")
for name in vote_names:
    vote_prompts[name] = agents_prompts[name] + vote_ref

print(f"  并行启动{len(vote_prompts)}个投决会Agent...")
with ThreadPoolExecutor(max_workers=len(vote_prompts)) as ex:
    futures = {ex.submit(call_model, p): name for name, p in vote_prompts.items()}
    for f in as_completed(futures):
        name = futures[f]
        try:
            ans = f.result()
            agent_results[name] = ans
            with open(os.path.join(AGENT_DIR, f"agent_{name}.md"), "w", encoding="utf-8") as fout:
                fout.write(f"# {name} 分析\n\n{ans}\n")
            print(f"  [{name}]: {len(ans)} chars")
        except Exception as e:
            print(f"  [{name}]: ERROR {e}")

# ====== 仲裁员单独保存 ======
arbitrator_text = agent_results.get("仲裁员", "")
if arbitrator_text:
    print(f"  [仲裁员]: {len(arbitrator_text)} chars")
    with open(os.path.join(AGENT_DIR, "agent_仲裁员.md"), "w", encoding="utf-8") as f:
        f.write(f"# 仲裁员终裁\n\n{arbitrator_text}\n")
else:
    print("  [仲裁员]: 缺失")

# ================== 监工 ==================
print("\n=== 监工Agent（审查-打回-再审） ===")

required_fields = {
    "技术分析师": ["技术面评分", "技术要点"],
    "基本面分析师": ["基本面评分", "基本面要点"],
    "情绪分析师": ["情绪面评分", "情绪要点"],
    "新闻分析师": ["新闻面评分", "新闻要点"],
    "多头": ["综合评分", "核心看多逻辑"],
    "空头": ["综合评分", "核心看空逻辑"],
    "激进风控": ["风险评估评分", "机会评估"],
    "保守风控": ["风险评估评分", "极坏场景"],
    "中性风控": ["委员会风险评估评分"],
    "仲裁员": ["综合评分", "投决会决策理由"],
}

def overseer_audit(agent_results):
    issues = []
    for name, fields in required_fields.items():
        text = agent_results.get(name, "")
        if not text:
            issues.append(f"[监工] {name}: 输出为空"); continue
        if len(text) < 80:
            issues.append(f"[监工] {name}: 字数仅{len(text)}，可能过于敷衍")
        for f in fields:
            # 宽松匹配：**f** 或 **f（ 都算通过
            if f"**{f}**" not in text and f"**{f}（" not in text and f"**{f}(" not in text:
                issues.append(f"[监工] {name}: 缺少「{f}」字段")
    scores = {}
    for name in list(agent_results.keys()):
        txt = agent_results.get(name,"")
        # 兼容研究委员会（技术面评分/基本面评分等）和投决会/风控（综合评分）
        m = re.search(r'\*\*(?:综合评分|技术面评分|基本面评分|情绪面评分|新闻面评分|风险评估评分|委员会风险评估评分)[^0-9]*([\d.]+)', txt)
        if m: scores[name] = float(m.group(1))
    for name, text in agent_results.items():
        # 研究委员会没有操作建议字段，跳过矛盾检测
        if name in ["技术分析师","基本面分析师","情绪分析师","新闻分析师"]:
            continue
        m_action = re.search(r'\*\*操作建议\*\*\s*:\s*([^\n]+)', text)
        if m_action and name in scores:
            act = m_action.group(1).strip(); sc = scores[name]
            for low_act in ["买入","加仓"]:
                if low_act in act and sc < 4:
                    issues.append(f"[监工] {name}: 评分{sc}却建议「{act}」，矛盾")
            for high_act in ["卖出","减仓"]:
                if high_act in act and sc > 7:
                    issues.append(f"[监工] {name}: 评分{sc}却建议「{high_act}」，矛盾")
    # 回避措辞检测也跳过研究委员会（他们不执行操作建议，说「不确定」是可以的）
    avoid = ["不确定","无法判断","不明确","可能也许"]
    for name, text in agent_results.items():
        if name in ["技术分析师","基本面分析师","情绪分析师","新闻分析师"]:
            continue  # 研究委员会只做事实分析，说「不确定」是正常的
        for w in avoid:
            if w in text: issues.append(f"[监工] {name}: 回避措辞「{w}」"); break
    return issues, scores

issues, scores = overseer_audit(agent_results)
print(f"  第一轮审查: {len(issues)}个问题")
for iss in issues: print(f"    {iss}")

MAX_RETRIES, retry_count, retry_agents = 2, 0, set()
while issues and retry_count <= MAX_RETRIES:
    agents_to_retry = set()
    for iss in issues:
        for name in list(agent_results.keys()):
            if name in iss and name not in retry_agents:
                agents_to_retry.add(name)
    if not agents_to_retry: break
    print(f"  并行重写{len(agents_to_retry)}个Agent...")
    retry_prompts = {}
    for name in agents_to_retry:
        prompt = agents_prompts.get(name, "")
        if not prompt: continue
        feedback = "\n".join([iss for iss in issues if name in iss])
        retry_prompts[name] = prompt + f"\n\n[监工退回] {feedback}\n请严格按格式重新输出。评分统一规则：高分=倾向买入，低分=倾向卖出。"
    with ThreadPoolExecutor(max_workers=len(retry_prompts)) as ex:
        futures = {ex.submit(call_model, p): name for name, p in retry_prompts.items()}
        for f in as_completed(futures):
            name = futures[f]
            try:
                new_ans = f.result()
                agent_results[name] = new_ans
                with open(os.path.join(AGENT_DIR, f"agent_{name}.md"), "w", encoding="utf-8") as fout:
                    fout.write(f"# {name} 分析（监工退回重写）\n\n{new_ans}\n")
                print(f"  [重写{name}]: {len(new_ans)} chars")
            except Exception as e:
                print(f"  [重写{name}]: ERROR {e}")
    retry_agents.update(agents_to_retry); retry_count += 1
    issues, scores = overseer_audit(agent_results)
    print(f"  第{retry_count+1}轮审查: {len(issues)}个问题")
    for iss in issues: print(f"    {iss}")

print(f"\n  监工最终: {'全部通过' if not issues else f'{len(issues)}个问题'}")
print(f"  监工评级: {'A' if not issues else 'B' if len(issues)<=2 else 'C'}")
if issues:
    for iss in issues: print(f"    {iss}")

# ====== 数据监督报告 ======
with open(os.path.join(AGENT_DIR, "数据监督报告.md"), "w", encoding="utf-8") as f:
    lines = []
    lines.append(f"# 数据监督Agent 审计报告 — {STOCK}({CODE})")
    lines.append(f"**审计时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("## 数据源完整性")
    lines.append("")
    lines.append(f"```")
    lines.append(f"data文件夹: {DATA_DIR}")
    lines.append(f"文件数: {len(local_files)}")
    for fn, sz in local_files:
        lines.append(f"  {fn} ({sz} bytes)")
    lines.append(f"```")
    lines.append("")
    lines.append("## 数据质量检查")
    lines.append("")
    lines.append("| 数据源 | 状态 | 大小 |")
    lines.append("|:------|:----:|:---:|")
    for k in ["行情","技术面","资金流向","日线","利润表","资产负债表","现金流量表","新闻","研报"]:
        v = data_in_memory.get(k,"")
        status = "OK" if len(v) > 50 else "WARN"
        lines.append(f"| {k} | {status} | {len(v)} chars |")
    lines.append("")
    lines.append(f"**Context总字符数**: {len(ctx_str)}")
    lines.append(f"**审计结论**: {'数据完整，可进行后续分析' if len(ctx_str) > 1000 else '数据不足，建议重新采集'}")
    f.write("\n".join(lines))
print(f"  数据监督报告: {len(lines)} lines")

# ====== 监工审计报告 ======
with open(os.path.join(AGENT_DIR, "监工审计报告.md"), "w", encoding="utf-8") as f:
    lines = []
    lines.append(f"# 监工Agent 审计报告 — {STOCK}({CODE})")
    lines.append(f"**审计时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**最终评级**: {'A' if not issues else 'B' if len(issues)<=2 else 'C'}")
    lines.append("")
    lines.append("## 审查结果")
    lines.append("")
    lines.append(f"**总轮次**: {retry_count + 1}")
    lines.append(f"**最终问题数**: {len(issues)}")
    lines.append("")
    if issues:
        lines.append("### 遗留问题")
        for iss in issues:
            lines.append(f"- {iss}")
    else:
        lines.append("**无遗留问题，全部通过审查。**")
    lines.append("")
    lines.append("## Agent评分一览")
    lines.append("")
    lines.append("| Agent | 评分 | 建议 |")
    lines.append("|:------|:---:|:----:|")
    for name in ["技术分析师","基本面分析师","情绪分析师","新闻分析师","多头","激进风控","空头","保守风控","中性风控","仲裁员"]:
        txt = agent_results.get(name,"")
        # 兼容：综合评分 / 技术面评分 / 基本面评分 / 情绪面评分 / 新闻面评分 / 风险评估评分 / 委员会风险评估评分
        m_sc = re.search(r'\*\*(?:综合评分|技术面评分|基本面评分|情绪面评分|新闻面评分|风险评估评分|委员会风险评估评分)[^0-9]*([\d.]+)', txt)
        m_act = re.search(r'\*\*操作建议\*\*\s*:\s*([^\n]+)', txt) if name not in ["技术分析师","基本面分析师","情绪分析师","新闻分析师","激进风控","保守风控","中性风控"] else None
        sc = m_sc.group(1) if m_sc else "?"
        act = "?"
        if m_act:
            act = m_act.group(1).strip()[:10]
        lines.append(f"| {name} | {sc}/10 | {act} |")
    lines.append("")
    lines.append("## 审计结论")
    lines.append("")
    rating_desc = {"A": "高质量分析，结论可信", "B": "存在轻微问题，需留意", "C": "质量问题较多，建议重跑"}
    lines.append(rating_desc.get('A' if not issues else 'B' if len(issues)<=2 else 'C', '需审查'))
    f.write("\n".join(lines))
print(f"  监工审计报告: {len(lines)} lines")

# ====== 结果汇总 ======
print(f"\n{'='*60}")
print(f"   {STOCK}({CODE}) 10Agent 分析结果")
print(f"{'='*60}")
for name in ["技术分析师","基本面分析师","情绪分析师","新闻分析师","多头","激进风控","空头","保守风控","中性风控"]:
    sc = agent_results.get(name,"")
    m = re.search(r'\*\*(?:综合评分|技术面评分|基本面评分|情绪面评分|新闻面评分|风险评估评分|委员会风险评估评分)[^0-9]*([\d.]+)', sc)
    act = re.search(r'\*\*操作建议\*\*\s*:\s*([^\n]+)', sc)
    sc_str = m.group(1) if m else "?"
    if name in ["技术分析师","基本面分析师","情绪分析师","新闻分析师","激进风控","保守风控","中性风控"]:
        # 研究委员会和风险委员会不输出操作建议，显示空
        act_str = "—"
    else:
        act_str = act.group(1).strip()[:12] if act else "?"
    print(f"   {name:10s} | 评分: {sc_str:4s} | 建议: {act_str}")

pm = agent_results.get("仲裁员", agent_results.get("组合经理",""))
# 仲裁员字段兼容：综合评分 / 综合评分（...）, 最终操作 / 操作建议, 仓位比例 / 仓位建议
m = re.search(r'\*\*综合评分[^0-9]*([\d.]+)', pm)
act = re.search(r'\*\*(?:最终操作|操作建议|最终建议)\*{0,2}\s*[：:]\s*([^\n.。]+)', pm)
pos = re.search(r'\*\*(?:仓位比例|仓位建议)\*{0,2}[^0-9]*[：:]\s*([^\n,，%]+)', pm)
ep = re.search(r'\*\*(?:入场价格|入场价|入场|建议入场区间)\*{0,2}[^\n]*[：:]\s*([^\n,，]+)', pm)
sl = re.search(r'\*\*(?:止损价格|止损价|止损)\*{0,2}[^\n]*[：:]\s*([^\n,，]+)', pm)
tp = re.search(r'\*\*(?:目标价格|目标价|目标)\*{0,2}[^\n]*[：:]\s*([^\n,，]+)', pm)
sc_txt = m.group(1) if m else "?"
act_txt = "?"
if act:
    a = act.group(1).strip()
    a = re.sub(r'^\*{1,2}\s*', '', a)
    act_txt = a[:10]
print(f"\n仲裁员终裁:")
print(f"   评分: {sc_txt} | 建议: {act_txt}")
print(f"   入场: {ep.group(1).strip()[:20] if ep else 'N/A'} | 止损: {sl.group(1).strip()[:20] if sl else 'N/A'} | 目标: {tp.group(1).strip()[:20] if tp else 'N/A'}")
print(f"   仓位: {pos.group(1).strip()[:20] if pos else '?'}")

# ====== 综合报告 ======
print(f"=== 生成综合报告 ===")
report = []
report.append(f"# {STOCK}({CODE}) \u2014 10Agent 综合投资报告")
report.append(f"**分析日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  **您的成本**: {COST} HKD")
report.append("")
report.append("---")
report.append("")
report.append("## 一、投票汇总")
report.append("")
for name in ["技术分析师","基本面分析师","情绪分析师","新闻分析师","多头","激进风控","空头","保守风控","中性风控"]:
    sc = agent_results.get(name,"")
    sc_text = "?"
    m_sc = re.search(r"\*\*(?:综合评分|技术面评分|基本面评分|情绪面评分|新闻面评分|风险评估评分|委员会风险评估评分)[^0-9]*([\d.]+)", sc)
    if m_sc: sc_text = m_sc.group(1)
    if name in ["技术分析师","基本面分析师","情绪分析师","新闻分析师","激进风控","保守风控","中性风控"]:
        act_text = "—"
    else:
        act = re.search(r"\*\*操作建议\*\*\s*:\s*([^\n]+)", sc)
        act_text = act.group(1).strip() if act else "?"
    report.append(f"| **{name}** | **{sc_text}/10** | **{act_text}** |")
report.append("")
report.append("### 投决会仲裁员终裁")
report.append("")
report.append(agent_results.get("仲裁员","")[:1500])
report.append("")
report.append("---")
report.append("")
report.append("## 二、各Agent详细观点")
report.append("")
for name in ["技术分析师","基本面分析师","情绪分析师","新闻分析师"]:
    txt = agent_results.get(name,"")
    if txt:
        report.append(f"### {name}")
        report.append("")
        points = re.findall(r"\d+\.\s*[^\n]+", txt)
        if points:
            for p in points: report.append(f"- {p}")
        else:
            report.append(txt[:600])
        report.append("")
report.append("---")
report.append("")
report.append("## 三、风控多空博弈")
report.append("")
for name in ["多头","激进风控","空头","保守风控","中性风控"]:
    txt = agent_results.get(name,"")
    if txt:
        label = name
        m_sc = re.search(r"\*\*综合评分\*\*\s*:\s*([^\n]+)", txt)
        if m_sc: label += f" \u2014 评分: {m_sc.group(1).strip()}"
        m_act = re.search(r"\*\*操作建议\*\*\s*:\s*([^\n]+)", txt)
        if m_act: label += f" \u2192 {m_act.group(1).strip()}"
        report.append(f"### {label}")
        report.append("")
        points = re.findall(r"\d+\.\s*[^\n]+", txt)
        if points:
            for p in points[:4]: report.append(f"- {p}")
        report.append("")

with open(os.path.join(AGENT_DIR, "综合报告.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(report))
print(f"  综合报告 saved to {DATA_BASE}")

print(f"OK! 报告目录: {DATA_BASE}")
