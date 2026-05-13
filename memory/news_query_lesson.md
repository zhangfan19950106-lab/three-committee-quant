# 2026-05-09：新闻查询词教训 — 简体中文+代码 > 纯英文

**问题**：NeoData docRecall 的搜索引擎对纯英文查询词效果极差。
- 搜 `09868.HK news 2026 May` → 返回香港财政预算案等无关内容
- 搜 `Xpeng 09868.HK latest news May 2026` → 返回微软Build 2026开发者大会
- 搜 `小鹏汽车 09868 最新消息 2026` → 正确命中4月交付数据

**结论**：所有 fetch 脚本的新闻查询词必须使用 **简体中文 + 港股代码** 的格式，禁止纯英文。

**已更新文件（6个）**：
- fetch_template.py — 模板默认词
- step1_fetch.py — 通用step1
- step1_fetch_xpeng_data.py — 小鹏专用
- fetch_dyg.py — 东阳光
- fetch_ks.py — 快手
- fetch_sjg.py — 数据港
- fetch_bidu.py — 百度v1
- fetch_xiaopeng.py — 小鹏

**新标准格式**：`f"{股票简称} {代码} 最新消息 2026"`（如 `小鹏汽车 09868.HK 最新消息 2026`）
