<<<<<<< HEAD
Featuring:
Supervisor Agent for quality control
AI Investment Committee for institutional-grade decisions
=======
# 三委员会量化 — 港股多Agent分析系统

多Agent协作式港股量化分析系统，采用**三委员会架构**替代传统单一大模型评估。

## 架构

```
研究委员会（4人并行）→ 风险委员会（3人并行）→ 投决会（3人并行）
                        ↓
                  多头 vs 空头 辩论 → 仲裁员终裁
```

### 第一阶段：研究委员会
- **技术分析师** — 均线/MACD/KDJ/支撑阻力
- **基本面分析师** — 利润/资产负债/现金流
- **情绪分析师** — 资金流向/市场情绪
- **新闻分析师** — 新闻/研报/事件

> 只给事实分析，不表态买卖方向。

### 第二阶段：风险委员会
- **激进风控** — 风险可控性评估
- **保守风控** — 最坏场景评估
- **中性风控** — 平衡评估（委员会主席）

> 只评估风险，不直接建议仓位。

### 第三阶段：投决会
- **多头辩手** — 论证买入理由
- **空头辩手** — 论证卖出/观望理由
- **仲裁员** — 基于以上所有信息给出终裁

## 使用方法

```bash
# 快速分析一只股票
python run_analysis.py --stock 小米 --code 01810.HK --cost 33.70 --position 0

# 交互模式
python run_analysis.py
```

## 数据源

- **NeoData API** — 行情/技术指标/资金流向/三张报表/新闻/研报
- **新浪财经** — 港股日线数据降级
- **元宝搜索** — 联网新闻补充

## 模型

- **deepseek-chat** — 各Agent分析（并行调用）
- **deepseek-reasoner** — 多头vs空头辩论 + 仲裁员终裁

## 输出

```
C:\Users\zhang\Desktop\TradingAgent报告存放\{股票}_{日期}\
├── 9agent分析/          # 三委员会各Agent独立文件
│   ├── 研究委员会汇总.md
│   ├── 风险委员会汇总.md
│   ├── agent_技术分析师.md
│   └── ...
├── 辩论/
│   ├── 辩论_round1_多头.md
│   ├── 辩论_round1_空头.md
│   └── 辩论_终裁.md
└── data/                # 原始数据
    ├── 行情.txt
    ├── 技术指标.txt
    └── ...
```

## 关键文件

| 文件 | 说明 |
|:---|:---|
| `run_analysis.py` | 总指挥调度入口 |
| `fetch_template.py` | 三委员会核心逻辑 + 数据采集 |
| `run_xiaomi_debate.py` | 投决会辩论（多头vs空头→仲裁员） |
| `ta_utils.py` | 工具函数库 |
| `data_inspector.py` | 数据监督Agent |

## 系统红线（L0）

1. 新闻搜索统一简体中文+股票代码格式
2. 所有分析前检查三源数据真实性
3. 辩论使用 `deepseek-reasoner`（R1），日常用 `deepseek-chat`
4. 监工Agent审查—打回循环，`MAX_RETRIES=2`
>>>>>>> 614a2a7 (feat: 三委员会量化系统 V5)
