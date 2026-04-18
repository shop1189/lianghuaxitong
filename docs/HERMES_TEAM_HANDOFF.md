# Hermes 侧配合清单（量化机 longxia_system · 与本日升级对齐）

> **用途**：量化仓库升级完成后，把本文发给 Hermes 负责人，按项确认或排期。**不改变** Hermes 业务逻辑时，多为「时间窗 + 文件 + 权限 + 互链」类事项。  
> **更新**：配合项变更时改本文件日期行，并在 `PROJECT_MEMORY.md` 提一句。

**本文档版本**：2026-04-18  

---

## 1) 技能库文件（自动「入脑」依赖）

量化机脚本：`scripts/hft_skill_auto_ingest.py`（建议 cron **每日 09:12** 或每 30 分钟，见 `PROJECT_MEMORY.md` §4）。

| 配合项 | Hermes 侧 | 验收 |
|--------|-----------|------|
| **产物路径** | 导出到 Hermes **outbox**（或你们约定的同步源路径），至少包含：<br>• `hft_strategy_skill_library.md`<br>• `hft_strategy_skill_library.meta.json`（**须含 `sha256`**，与当前 md 内容一致） | 量化机 `hermes_outbox/` 经 rsync 后两文件存在且可读 |
| **导出时间** | 建议每日 **北京时间不晚于 09:05**（须 **早于** 量化机 09:12 入脑脚本；若网络慢再提早） | 与量化团队约定固定窗口并写进双方 runbook |
| **权限** | 同步到量化机后的文件：**可读**、无 root-only 导致 ingest 失败（历史上曾出现 outbox 权限问题，已修则保持） | `python3 scripts/hft_skill_auto_ingest.py` 手动跑无 Permission denied |
| **变更频率** | meta 中 `sha256` 变化时，量化侧才会重解析（见 `utils/hft_skill_brain.py`） | 大改技能库后确认 sha 已更新 |

---

## 2) 健康检查 / 日报（事实源，不替代本仓库逻辑）

| 配合项 | 说明 |
|--------|------|
| **绿/黄契约** | 若契约依赖「同步目录里的 `PROJECT_MEMORY.md` / `daily_market_notes.md` / `trade_memory.json`」等，请与量化侧约定 **路径与时间**（常见：`/opt/hermes-sync/inbox/`）。 |
| **日更笔记** | 量化侧维护 **`docs/daily_market_notes.md`**（日期滚动）。若 Hermes 脚本检查「笔记日期为今/昨日」，请双方对齐 **以哪台机器文件为准**。 |
| **版式（可选）** | `hermes_outbox/*_health.md`：保持「结论在前」；超长明细可拆文件（**仅版式**，不改判定逻辑）。排期见 `docs/UPGRADE_PLAN.md` 阶段 B。 |

---

## 3) 文档互链（可选，强烈建议）

| 配合项 | 内容 |
|--------|------|
| **Hermes 工作区 README / onboarding** | 增加一行：**主工程入口** → 量化机上的 `longxia_system` 根目录 **`README.md`**（写清**本机绝对路径**）。 |
| **避免混淆** | Hermes 自有「升级计划」与量化侧 **`docs/UPGRADE_PLAN.md` / `docs/upgrade_framework_merged_v1.md`** 名称不同；对接时指明仓库路径。 |

---

## 4) 回执（Hermes 填完发给量化对接人）

```
【Hermes × longxia 配合回执】
- 执行人 / 日期：
- 技能库每日导出时间（北京时间）与 outbox 路径：
- meta.json 是否含 sha256 且与 md 一致：（是/否）
- 量化机 hermes_outbox 是否在 09:12 前可拿到当日文件：（是/否，同步方式：）
- 权限 / ingest 手动试跑：（通过 / 失败摘要）
- Hermes 说明是否已加主库 README 互链：（是/否，路径：）
- 未做项及原因：
```

---

## 5) 相关文件（量化仓库内）

| 文件 | 说明 |
|------|------|
| `docs/quant_hft_skill_consensus_v1.md` | 技能库「入脑」共识与边界 |
| `docs/hermes_synergy_framework.md` | Hermes 与量化协同总览 |
| `scripts/hft_skill_auto_ingest.py` | 自动入脑入口 |
| `scripts/hft_skill_ingest_status.py` | sha256 对比 / 可选 `--mark-ingested` |
