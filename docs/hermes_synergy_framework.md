# Hermes 与量化系统：能力边界与协同（落地对照）

> 本文档与 `hermes_outbox/` 下快照一致，便于新人与复盘；**Bot-A / Bot-B 可执行脚本与 compose 在 Hermes 主机（如 `/opt/hermes-stack`），不在本仓库。**

## 1. 架构角色（已落地侧）

| 组件 | 作用 |
|------|------|
| **Bot-A（hermes）** | 量化日报「确定性出口」：`hermes_daily_telegram_digest.py`（在 Hermes 侧）与 `hermes_data_health.json` 对齐，避免 LLM 编造品种/净值。 |
| **Bot-B（hermes-chat）** | 日常：读同步目录、联网检索、解释；遇「生成日报」引导至 Bot-A。 |
| **`/opt/hermes-sync`** | 量化 → Hermes 的**事实边界**：inbox 数据、outbox 健康与报告、meta 批次信息。 |
| **LLM（硅基 + Qwen 等）** | 推理、摘要、对照文档、解释黄/绿原因；**不替代**回测与实盘系统。 |

## 2. 本仓库内可验收产物（对照路径）

| 类型 | 位置 |
|------|------|
| 数据健康快照 | `hermes_outbox/hermes_data_health.json`、`.md`（`overall_status`、`status_reasons`、`checks`） |
| 模型/对话健康 | `hermes_outbox/hermes_model_health.json` |
| 日报与数据来源说明 | `hermes_outbox/hermes_daily_report.json`、`.md`（指向 `/opt/hermes-sync/inbox/` 下 `trade_memory`、`backtest_result`、`PROJECT_MEMORY`、`daily_market_notes`） |
| 技能包 meta / 正文 | `hermes_outbox/hft_strategy_skill_library.meta.json`、`hft_strategy_skill_library.md` |
| ingest 状态 | `config/hermes_skill_ingest_state.json`、`data/hft_skill_brain_digest.json` |

## 3. 强项 / 弱项（心里有数）

**强项**：统一事实入口（同一套同步文件）；可验收的绿灯/黄灯（health、meta）；人机分流（日报 vs 泛对话）；架构可扩展。

**弱项**：LLM 仍可能幻觉——关键事实靠 **脚本 + 健康 JSON + 规则**；联网 ≠ 交易真相；工具与双容器增加运维负担（密钥、白名单、compose）。

## 4. 与量化侧搭配（数据流）

```
量化机生成/导出 → rsync（+ meta）→ /opt/hermes-sync/inbox
                              → 健康脚本 → outbox
Bot-A：digest 读 JSON + trade + meta → 固定格式日报
Bot-B：同路径 read_file + 联网 → 解释、对比、风险提示（标注「参考」）
```

**分工**：量化侧写 meta、保证数据质量与节奏；Hermes 侧读 `hermes_data_health.json`，**不篡改事实**；闲聊中的市场观点**不**写入 `PROJECT_MEMORY` 当事实，除非量化确认。

**搭配得好**：改 schema 时同步更新 meta / 健康脚本字段约定。

## 5. 演进阶段（运维节奏，非本仓库强制开关）

| 阶段 | 重心 |
|------|------|
| **A：稳（0–4 周）** | 监控：日报是否空、health 是否常黄、rsync/cron 是否跳过；维护短文档「inbox 文件说明 + 绿条件」；密钥与 `.env` 权限。 |
| **B：准（1–3 月）** | 健康维度少量增加、可验证；Bot-B 提示词固定「读文件先报路径」「联网带来源与时间」；可选黄灯摘要告警。 |
| **C：省（2–6 月）** | 常问「黄了怎么办」映射到 `status_reasons` + 量化 checklist；MEMORY 只记偏好不记行情判断；可选只读摘要类定时任务且与量化 cron 错峰。 |
| **D：强（长期）** | 策略/数据/meta schema 版本同构升级；实验闭环进 outbox，Hermes 读懂结构、对齐文档，**默认不**自动调参下单。 |

## 6. 三句话原则

1. 量化产出「可验证事实」；Hermes 产出「可读、可对齐、不越权」的辅助层。  
2. 每加一层自动化，先加一层验收（健康、meta、日志）。  
3. 变强 = 契约更稳 + 复盘更快 + 误会更少，而不是模型更大。

## 7. 示意图（一记）

```
        ┌─────────────────────────────────────────┐
        │ 量化：信号 · 回测 · 实盘 · 风控（唯一权威） │
        └──────────────────┬──────────────────────┘
                           │ 文件 + meta + 健康
                           ▼
        ┌─────────────────────────────────────────┐
        │ /opt/hermes-sync（事实 + 批次 + 健康快照）   │
        └──────────┬──────────────────┬───────────────┘
                   │                │
           Bot-A：可验收日报        Bot-B：解释·检索·对照
                   │                │
                   └────────┬───────┘
                            ▼
                   人：决策 · 实验 · 复盘
```

---

*若仅「确认架构与仓库产物一致」，无需改首页或业务代码；后续有新约定再增量修改本文或 `hermes_outbox` 生成逻辑。*
