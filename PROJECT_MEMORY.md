# PROJECT_MEMORY（本仓库）

## 1) 这份文件的用途

记录与人协作时的**长期约定**与备忘；**一层入口**请先读仓库根目录 **[README.md](README.md)**（渐进式披露：短索引 → 再点链）。

若你方在 Hermes 同步目录（如 `/opt/hermes-sync/inbox/`）另有同名 `PROJECT_MEMORY.md`，以**各自场景**为准：本文件服务 **longxia_system 仓库内开发**；同步目录文件服务 **日报 / 健康检查 / 跨机事实**。

## 2) 相关链接

- 升级与排期：`docs/UPGRADE_PLAN.md`
- 实验轨环境变量速查：`live_trading.py` 顶部注释
- HFT 技能库共识（v1）：`docs/quant_hft_skill_consensus_v1.md`

## 12) Hermes 技能包 · 自动入脑（可选 cron）

| 目的 | 路径 |
|------|------|
| 对比 sha256 是否要重新处理 | `scripts/hft_skill_ingest_status.py`（可选 `--mark-ingested`） |
| **自动入脑**（解析 md → `data/hft_skill_brain_digest.json`） | `scripts/hft_skill_auto_ingest.py` |

在量化机 `crontab` 中可增加（**路径按本机修改**；须晚于 Hermes 侧导出与本机 rsync）：

```cron
12 9 * * * /usr/bin/python3 /root/longxia_system/scripts/hft_skill_auto_ingest.py >> /root/longxia_system/logs/hft_skill_auto_ingest.log 2>&1
```

亦可改为 `*/30 * * * *` 每 30 分钟。首次可手动：`python3 scripts/hft_skill_auto_ingest.py`。
