# 龙侠量化 · 合并升级框架（v1 · 本地与服务器对齐稿）

> **用途**：把「产品阶段表（阶段0～4）」与仓库内 **`docs/UPGRADE_PLAN.md`**、**`docs/upgrade_roadmap_v1.md`**（若存在）合成一份可执行、可留档的总表。  
> **更新规则**：范围或优先级变更时改本文件并补日期行；重大决策同步 **`PROJECT_MEMORY.md`**。

---

## 1) 当前基线（已确认）

- **数据层 / 对外版本**：**V3.18.0**（`GET /api/version`、决策页「数据层」、`data_fetcher` 启动行）。  
- **备份标签（可回滚）**：`restore-pre-v317-patch-2026-04-18`、`restore-pre-phase-b-2026-04-18`；离线包见 `PROJECT_MEMORY.md`。  
- **Hermes**：`hermes_outbox/` 技能库；`scripts/hft_skill_auto_ingest.py` 自动入脑（cron 可选）。  
- **主观察池 / 实验轨**：开仓筛选与档位宽度以 `live_trading` / 环境变量为准；**不**在本文件逐条复述。

---

## 2) 你的阶段框架（原意保留）

| 阶段 | 目标（摘要） | 与仓库文档关系 |
|------|----------------|----------------|
| **0 观察期** | 热修复稳定、样本与仪表盘对齐 | 接近 `upgrade_roadmap_v1` 样本期；细节以当时提交为准 |
| **1** | Gate 指标 + 电子书体系 + SL/TP 体验 | 与路线图「阶段 A」工程对齐时可合并立项 |
| **2** | 行情记忆 + 回测 / Freqtrade 等 | 路线图阶段 B/C；**不**强制一次接齐 |
| **3** | 进化、持仓管理、LLM/FinRL 等 | `UPGRADE_PLAN` 阶段 C～E、工具分级 |
| **4（可选）** | 补全书库等 | 文档/实验扩展，与主干闸门分离 |

---

## 3) 与 `UPGRADE_PLAN.md` / `upgrade_roadmap_v1.md` 的映射

| 仓库文档 | 内容 |
|----------|------|
| **`docs/UPGRADE_PLAN.md`** | 阶段 A～E：入口、Agent 文档、Kronos、动态仓位等 **工程分期** |
| **`docs/upgrade_roadmap_v1.md`** | 样本期→工程对齐→回测记忆→自动化→体验扩展（**已落盘短表**） |

---

## 4) 下一轮主线（三选一，定一条再拆任务）

| 选项 | 含义 | 典型产出 |
|------|------|----------|
| **A（工程）** | 路线图 **阶段 A**：信号/平仓/虚拟逻辑 **同源** + 最小回测入口 | 共用模块、对齐样本回归 |
| **B（体验）** | 你的 **阶段1** 一包：指标展示 + 书库扩展 + SL/TP 文案/体验 | 少量文件、可对照页面 |
| **C（合并）** | A 与 B 合成一个里程碑 | 范围冻结后写清验收 |

**当前默认（工程切片已起步）**：优先 **A** 中与「平仓判定同源」相关项（见 §7）。**书面冻结**：默认主线记为 **A**，若改 **B/C** 须在 `PROJECT_MEMORY.md` 更新一行并改 §5 勾选。

---

## 5) 启动前简表（组织条件）

- [x] 主线选项 **A / B / C**：**默认 A（工程）** 已写入 `PROJECT_MEMORY.md` §3.3（可改为 B/C 并同步本文）  
- [x] 日更笔记：`docs/daily_market_notes.md` 已建立并滚动日期（Hermes 契约若启用请保持）  
- [x] 依赖：`pandas-ta` 已在 venv 安装；快速检查见 **`scripts/phase1_health_check.py`**

---

## 6) 相关文件索引

| 文件 | 说明 |
|------|------|
| `utils/trade_exit_rules.py` | 平仓档位与盈亏 %（tick） |
| `evolution_core.py` | `check_close_trade` 调用同源规则 |
| `live_trading.py` | 虚拟单 `_virtual_hit_and_close` 调用同源规则 |
| `docs/UPGRADE_PLAN.md` | 工程分期 |
| `docs/daily_market_notes.md` | 日更笔记（Hermes/健康契约辅助） |
| `scripts/phase1_health_check.py` | 交易记忆 / state / pandas_ta 快速检查 |

---

## 7) 已执行切片（工程主线起步）

| 日期 | 项 | 说明 |
|------|-----|------|
| **2026-04-18** | **同源平仓判定** | 抽出 `utils/trade_exit_rules.py`；`evolution_core.check_close_trade` 与 `live_trading._virtual_hit_and_close` 统一为 `first_exit_tick`；**做空虚拟盈亏口径**与原先 `live_trading` 手写式对齐为 **evolution_core 公式**（属同源修正，非改策略意图）。 |
| **2026-04-18** | **合并稿落盘** | 本文 + `docs/daily_market_notes.md` 更新；`README` / `PROJECT_MEMORY` 互链。 |
| **2026-04-18** | **升级 v1 收口** | `upgrade_roadmap_v1` 短表定稿；`phase1_health_check.py`；主线默认 **A** 写入 `PROJECT_MEMORY`；备份标签 `restore-pre-upgrade-wrapup-2026-04-18`。 |

---

*文档版本：merged_v1 · 与仓库同步迭代*
