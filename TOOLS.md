# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

---

## 元宝搜索（prosearch.cjs）

```bash
# 通用搜索新闻
node 'C:\Program Files\QClaw\resources\openclaw\config\skills\online-search\scripts\prosearch.cjs' \
  --keyword="简体中文 + 股票代码 + 最新消息 2026" \
  --freshness=7d \
  --industry=news
```

**关键点：**
- 查询格式必须简体中文 + 代码
- 不走web_fetch爬新闻站
- Python脚本内的subprocess.run需用list参数避免shell转义

## 直连NeoData（绕过ta_utils.qneo shell bug）

```python
PYTHON = r'C:\Users\zhang\AppData\Local\Python\bin\python.exe'
NEO_Q = r'C:\Program Files\QClaw\resources\openclaw\config\skills\neodata-financial-search\scripts\query.py'
cmd = [PYTHON, '-u', NEO_Q, '--query', query_str, '--data-type', 'api']
r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
```

## TradingAgent 执行标准流程（2026-04-30 定稿）

### 必要前置步骤

**跑任何 TradingAgent 脚本前，必须检查数据源真实性**

1. **确认三源均有内容**：查看 build_context() 输出的 `[数据源X]` 标记
   - [数据源1] 本地日线 — 必须有具体文件名和行数
   - [数据源2] 每日筛选结果 — 必须有具体行
   - [数据源3] NeoData — 必须有 `N 个数据块`
2. **检查数据新鲜度**：
   - 本地日线文件修改时间是否是今天/合理的交易日
   - NeoData 行情时间戳是否是当日
3. **检查数据合理性**：
   - 每日筛选的收盘价是否与今日价/最新收盘相差不大
   - RSI/涨跌幅等关键指标数值是否合理
4. **Context 字符数底线**：`> 1000 chars`，否则数据不全

**有疑问一律先拉新数据，不调用模型**，避免 Agent 凭训练知识编造分析。

### 模型路由

### 日常对话 / 快速分析
- `deepseek-chat`（V3）：日常对话、简单数据查询、常规分析

### 深度推理 / 辩论
- `deepseek-reasoner`（R1）：以下场景**必须**使用
  - 多Agent辩论（三风控互怼、委员会投票）
  - 组合经理综合裁决
  - 任何需要深度推理、数值验证、多轮逻辑链的场景
  - 风控意见出现分歧需要调解

### 脚本执行
- TradingAgents 脚本统一走 `deepseek-chat`（速度优先）
- 仅辩论环节改用 R1（在脚本中通过 `model = "deepseek-reasoner"` 指定）
