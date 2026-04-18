# 龙侠量化 · longxia_system

实盘与决策快照主工程（Gate.io / CCXT）。本页为**入口索引**；细节按需点开链接，避免一次读完全库。

## 打开方式

- 用 Cursor / VS Code **打开本仓库根目录**（或本目录下的 `longxia_system.code-workspace`），避免只打开上层父目录导致工作区识别不一致。
- **身份与短规则**：`.cursor/WORKSPACE_IDENTITY.txt`
- **详细 Cursor 规则**：`.cursor/rules/`（身份、交易记忆写盘约束等）
- **会话与 Hermes 恢复说明**：`.cursor/HERMES_SESSION_RESTORE.md`

## 一层索引（先短后长）

| 想了解 | 去读 |
|--------|------|
| **Cursor / Agent 短约束** | [`AGENTS.md`](AGENTS.md) → [`docs/agent/README.md`](docs/agent/README.md) |
| 整库升级路线与分阶段事项 | `docs/UPGRADE_PLAN.md` |
| 项目记忆 / 协作约定（若存在） | `PROJECT_MEMORY.md` |
| Hermes 与量化协同边界 | `docs/hermes_synergy_framework.md` |
| 决策页、虚拟单、**规则实验轨**环境变量 | `live_trading.py` 文件顶部注释 |
| Hermes HFT 技能库自动入脑（cron） | `scripts/hft_skill_auto_ingest.py`、`docs/quant_hft_skill_consensus_v1.md` |
| Web 入口 | `main.py`（`/decision` 决策看板） |
| 对外版本（监控 / curl） | `GET /api/version` → JSON `engine` = **V3.17.0** |

## 主干链路（一句话）

行情与 K 线 → `live_trading.get_v313_decision_snapshot` → 主观察池虚拟写入 + 规则实验轨（`sync_experiment_track_from_snapshot`）→ `trade_memory.json` / 页面展示。

## 可选参考（非主干）

本地若存在 **`memos_ref/`**（体积大、可能 gitignore）：仅作阅读参考，**不**与线上决策快照混为一谈；主干以本仓库 `live_trading` / `main.py` 为准。
