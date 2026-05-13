# 工具配置

_执行脚本或调试时加载。_

## 路径

| 用途 | 路径 |
|:---|:----|
| Python | `C:\Users\zhang\AppData\Local\Python\bin\python.exe` |
| Node | `C:\Program Files\nodejs\node.exe` |
| ta_utils.py | `C:\Users\zhang\.qclaw\workspace\ta_utils.py` |
| fetch_template.py | `C:\Users\zhang\.qclaw\workspace\fetch_template.py` |
| 报告输出根目录 | `C:\Users\zhang\Desktop\TradingAgent报告存放\` |
| 工作区脚本 | `C:\Users\zhang\.qclaw\workspace\` |

## API

| 用途 | Key / 命令 |
|:---|:----------|
| DeepSeek | `sk-39f7fc15acbb42c78082beacdb4338c1` |
| NeoData | `<skills>/neodata-financial-search/scripts/query.py`（list参数绕过shell转义） |
| 元宝搜索 | `prosearch.cjs --keyword=关键词 --freshness=7d --industry=news` |

## 加速技巧（2026-05-13 新增）

| 修改 | 效果 |
|:----|:----|
| NeoData并行查询 | 7次API调用从~105s → ~15s |
| Agent并行运行 | 10个Agent调用从~150-300s → ~15-30s |
| 跳过元宝搜索 | 省~30s（NeoData新闻不够时才补） |
| 监工重写并行 | 重写从~30s/个 → ~15s/组 |
| **理论总节省** | **从~300-500s降到~60-90s（~5-6分钟 → ~1-1.5分钟）** |

## TradingAgent 优化记录（2026-05-13）

### 优化1: ✅ 现价读取 bug 修复
- **问题**: debate 脚本从「组合经理入场价格」字段读现价，买前分析时输出「不适用」→ 回退硬编码 31.46（小米的）
- **修复**: 改为从 `行情.txt` 读 `最新价格:` 正则匹配
- **文件**: `run_xiaomi_debate.py`

### 优化2: ✅ 新闻增强
- **问题**: NeoData 新闻经常 0 条（如华虹），元宝搜索只补1次86字符
- **修复**: 3组不同关键词（最新消息/业绩财报/新闻），累计约 3000c+
- **文件**: `fetch_template.py`

### 优化3: ✅ 一键分析脚本
- **新文件**: `quick_analyze.py` — 改3个变量（STOCK/CODE/COST）→ 自动跑完 9Agent + 辩论 + 输出
- 使用方法：修改脚本顶部 STOCK/CODE/COST，运行即可
- **依赖**: `fetch_template.py` + `run_xiaomi_debate.py`

| 技能 | 路径 |
|:---|:----|
| 元宝搜索 | `{bundled_skill_dir}\online-search\scripts\prosearch.cjs` |
| NeoData | `{bundled_skill_dir}\neodata-financial-search\scripts\query.py` |
