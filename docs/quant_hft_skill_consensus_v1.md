# 量化侧 · HFT 技能库与自动「入脑」共识（v1）

## 1. 定位

- Hermes 导出的 `hermes_outbox/hft_strategy_skill_library.md` + `meta.json` 是 **参考情报**，不是交易真源。
- **不**替代 `hermes_data_health` 绿/黄判定，**不**自动写入 `trade_memory`，**不**直接下单。

## 2. 自动同步 vs 自动 ingest

- **文件同步**：量化机常用 rsync 将 `hermes_outbox/` 拉到本仓库路径（由运维配置）。
- **入脑（节选）**：`scripts/hft_skill_auto_ingest.py` 在 `meta.sha256` 变化时解析 md，写入 **`data/hft_skill_brain_digest.json`**（已 `.gitignore`），供 `live_trading` 合并进书本提示与决策页展示。

## 3.1 自动「入脑」（仅书本节选）

- 定时建议：每日北京时间 **09:12** 或每 30 分钟（须晚于 Hermes 侧导出、且本机已拉到最新 outbox）。
- 详见 `PROJECT_MEMORY.md` 与 `scripts/hft_skill_auto_ingest.py`。
- 运维对照 sha256：`scripts/hft_skill_ingest_status.py`（可选 `--mark-ingested`）。

## 4. 后续（另一条升级线）

向量库 / RAG / LLM 长上下文接入：**不在** v1 范围；若要做，在 `docs/UPGRADE_PLAN.md` 中单独立项评估。
