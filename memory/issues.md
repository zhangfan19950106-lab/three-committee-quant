# 已知问题与约束

_修复Bug或写新脚本时加载。_

## 不可修复

- **PowerShell GBK编码** — Unicode/emoji不可打印，通过 PYTHONIOENCODING=utf-8 处理
- **Docker不可用** — UAC权限错误4294967291，RAGflow 未安装

## 待解决

- **qneo() shell=True 转义Bug** — 未在 ta_utils.py 根因修复，新脚本通过 subprocess list 参数绕过
- **R1终裁超时** — 35K+ prompt + 300秒可能不够 → 考虑切换到 deepseek-chat 做终裁
- **NeoData DNS 间歇性故障** — api.9shuju.com 解析失败时降级处理
