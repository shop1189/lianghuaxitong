# PROJECT_MEMORY（本仓库）

## 1) 这份文件的用途

记录与人协作时的**长期约定**与备忘；**一层入口**请先读仓库根目录 **[README.md](README.md)**（渐进式披露：短索引 → 再点链）。

**本地与服务器合并升级框架（权威对照稿）**：[`docs/upgrade_framework_merged_v1.md`](docs/upgrade_framework_merged_v1.md)（阶段0～4 与 `UPGRADE_PLAN` / `upgrade_roadmap_v1` 映射、下一轮 A/B/C 选项）。

若你方在 Hermes 同步目录（如 `/opt/hermes-sync/inbox/`）另有同名 `PROJECT_MEMORY.md`，以**各自场景**为准：本文件服务 **longxia_system 仓库内开发**；同步目录文件服务 **日报 / 健康检查 / 跨机事实**。

## 2) 相关链接

- **合并升级框架（v1）**：`docs/upgrade_framework_merged_v1.md`
- 升级与排期：`docs/UPGRADE_PLAN.md`
- 长路线图占位：`docs/upgrade_roadmap_v1.md`
- 日更笔记（可选契约）：`docs/daily_market_notes.md`
- 实验轨环境变量速查：`live_trading.py` 顶部注释
- HFT 技能库共识（v1）：`docs/quant_hft_skill_consensus_v1.md`
- **Hermes 配合清单（转对方执行）**：`docs/HERMES_TEAM_HANDOFF.md`
- 对外引擎版本（监控）：`GET /api/version` → `{"engine":"V3.17.0",...}`

## 3) 发布割接留档（V3.17.0 · 2026-04-18）

- **性质**：版本号与对外文案统一（数据层 **V3.17.0**）、`data_fetcher` 启动日志、`GET /api/version`；**未**改动主观察池虚拟单、实验轨开平仓规则内核。
- **100% 复原（打补丁前一刻）**：Git 标签 **`restore-pre-v317-patch-2026-04-18`**（提交 `a033433` 及父链）；可选离线包：`/root/longxia_backups/longxia_system-restore-pre-v317-2026-04-18.tar.gz`（`git archive`）。
- **回滚命令**：`git reset --hard restore-pre-v317-patch-2026-04-18`（需在同一仓库内且已 fetch 标签）。

## 3.1) 阶段 B 前备份与文档落地（2026-04-18）

- **备份标签**：`restore-pre-phase-b-2026-04-18` → 提交 **`0dfb385`**（进入阶段 B 文档前的快照）  
- **离线包**：`/root/longxia_backups/longxia_system-restore-pre-phase-b-2026-04-18.tar.gz`  
- **阶段 B 文档增量**：**`ff616e3`**～**`b849a3b`**（`docs/agent/`、`AGENTS.md`、README 互链与留档；Hermes 健康报告版式仍待真人团队）

## 3.2) 工程切片（2026-04-18 · 路线图阶段 A 起步）

- **同源平仓判定**：`utils/trade_exit_rules.py`（`first_exit_tick`）；`evolution_core.TradeMemory.check_close_trade` 与 `live_trading._virtual_hit_and_close` 统一调用。虚拟单 **做空** 盈亏 % 与原先手写分支若不一致，以 **evolution_core 公式** 为准（属同源对齐）。详见 **`docs/upgrade_framework_merged_v1.md` §7**。

## 3.3) 合并升级 v1 收口（2026-04-18）

- **主线默认**：**A（工程向）**——与「同源平仓 + 后续回测入口」一致；若改为体验向 **B** 或合并 **C**，请改本行并同步 **`docs/upgrade_framework_merged_v1.md` §5**。  
- **长路线图**：`docs/upgrade_roadmap_v1.md`（短表已定稿，非占位一句）。  
- **健康快检**：`scripts/phase1_health_check.py`（`trade_memory` / `live_trading_state` / `pandas_ta`）。  
- **备份（收口前一刻）**：标签 **`restore-pre-upgrade-wrapup-2026-04-18`**；离线包 `/root/longxia_backups/longxia_system-restore-pre-upgrade-wrapup-2026-04-18.tar.gz`。  
- **修补**：文档约定中的「后续小改、Hermes 版式、策略向 B」等，**不**与本节同一批次强绑；按 `UPGRADE_PLAN` 阶段 B～D 另排期。

## 4) Hermes 技能包 · 自动入脑（可选 cron）

| 目的 | 路径 |
|------|------|
| 对比 sha256 是否要重新处理 | `scripts/hft_skill_ingest_status.py`（可选 `--mark-ingested`） |
| **自动入脑**（解析 md → `data/hft_skill_brain_digest.json`） | `scripts/hft_skill_auto_ingest.py` |

在量化机 `crontab` 中可增加（**路径按本机修改**；须晚于 Hermes 侧导出与本机 rsync）：

```cron
12 9 * * * /usr/bin/python3 /root/longxia_system/scripts/hft_skill_auto_ingest.py >> /root/longxia_system/logs/hft_skill_auto_ingest.log 2>&1
```

亦可改为 `*/30 * * * *` 每 30 分钟。首次可手动：`python3 scripts/hft_skill_auto_ingest.py`。
