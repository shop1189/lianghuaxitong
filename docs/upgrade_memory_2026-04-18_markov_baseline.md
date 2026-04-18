# Longxia Markov 基线 · 记忆备份（扫描核实版）

> 生成说明：按当前仓库 `/root/longxia_system` 扫描结果整理；**未在代码中出现的项已标注「未实现」**，避免与对话稿混淆。你可整份复制到本地存档。

---

## 1. 今日升级摘要（可读版）

### 已落地（代码可核对）

- **Markov 状态模块**（`utils/market_regime_state.py`）：维护 chop/mid/trend 转移与下一步经验概率；实盘写 `logs/market_regime_state.json`，回测用 `RegimeMarkovTracker` 内存累计不写盘。
- **实验轨与模板名**：环境变量 `LONGXIA_MARKOV_TEMPLATE`（`off` | `strict_chop` | `balanced`，默认 `off`）。`strict_chop` / `balanced` 时由 `apply_markov_template_to_thresholds` 在**下一状态概率**基础上微调 `need_edge` / `score_floor`（与「按状态名写死 prob/consistency 三张表」不是同一套实现）。
- **决策快照**（`live_trading.get_v313_decision_snapshot` → `experiment_km_for_bar`）：写入 `markov_regime_state`、`markov_regime_line`、`markov_next_prob`、`markov_template` 等。
- **决策页**（`main.py` `/decision`）：已增加 **「行情状态（Markov）」** 一行，绑定 `markov_regime_line`。**未实现**单独一行「当前策略模板：XX（Markov）」若依赖 `experiment_markov_template_line` 等字段（见下表）。
- **回测**（`backtest.py`）：`--markov-template` 与实验轨 + kronos_light 筛选；`summary.json` 含 `markov_template`（experiment）或 `n/a`（main）；指标当前为 **毛口径** `win_rate_pct`、`sum_profit_pct` 等，**无** `win_rate_net_pct` / `sharpe_net` / `max_drawdown_net_pct`。
- **矩阵**（`scripts/backtest_matrix.py`）：`--markov-templates` 对 experiment 展开；`template_summary`；各表含 Markov 模板列；`LEVEL_MODES` / `MARKOV_TEMPLATES` 可由 `run_backtest_autotask.sh` 环境变量覆盖。
- **Git 基线**：远程曾推送标签 `backup/2026-04-18-markov-matrix-baseline`（用于 `git checkout` 复原该时点代码树）。

### 未实现 / 与对话稿不一致（勿当作已上线）

- 代码中**无** `USE_MARKOV_THRESHOLD_TEMPLATE` 常量、**无** `LONGXIA_USE_MARKOV_THRESHOLD_TEMPLATE`、**无** `get_threshold_template(current_state)` 返回「prob_diff / consistency / max_frequency」三档固定表。
- 快照中**无** `experiment_markov_template_enabled`、`experiment_markov_template_config`、`experiment_markov_template_line` 等字段名（若需展示「当前策略模板」行，须后续增量开发）。
- 矩阵报告**无** `markov_optimized`、`markov_optimized_compare_text`、自动「新旧规则对比总结」段落；**无**净胜率/回撤/Sharpe 与毛指标并列的矩阵列（除非后续在 `backtest.py` 先统一收益序列再算）。

### 后续升级计划（周期与条件建议）

| 阶段 | 周期建议 | 进入条件 |
|------|----------|----------|
| 观察 | 1～3 天 | 矩阵与决策页 Markov 行稳定产出；无异常报错 |
| 小范围验证 | 1～2 周 | 同品种、同参数下对比 `LONGXIA_MARKOV_TEMPLATE=off` 与 `strict_chop/balanced` 的实验轨行为差异可解释 |
| 若要上「状态映射策略表 + 开关」 | 按需排期 | 先定稿字段与执行层（频率节流在 `live_trading` 而非纯 state 模块），再改 `live_trading` + 快照 + 回测口径 |
| 若要矩阵「新旧规则 + 净指标」 | 按需排期 | 先在 `backtest.py` 产出净值序列与手续费口径，再算回撤/Sharpe，最后矩阵汇总 |

**默认立场**：在未补齐净口径与执行层频率逻辑前，**保持 `LONGXIA_MARKOV_TEMPLATE` 默认 off 或仅做观察**，与路线图一致、少动无关路径。

---

## 2. 参数与字段对照（技术版）

| 名称 | 位置（文件/模块） | 默认值 | 作用 | 是否影响旧逻辑 |
|------|-------------------|--------|------|----------------|
| `LONGXIA_MARKOV_TEMPLATE` | `live_trading.py` 文档串 / `experiment_km_for_bar` | `off` | 实验轨筛选使用的模板名：`off` 不调 `apply_markov_template_to_thresholds`；`strict_chop`/`balanced` 则按下一状态概率微调门槛 | **仅实验轨**；`off` 时与未接 Markov 模板时一致 |
| `apply_markov_template_to_thresholds` | `utils/market_regime_state.py` | — | 输入 `next_prob` + 模板名，输出调整后的 `need_edge`、`score_floor` | 仅在被 `LONGXIA_MARKOV_TEMPLATE` 非 off 且走 kronos_light 分支时生效 |
| `markov_template` | 快照 `experiment_km_for_bar` 返回 | `off` 或环境覆盖 | 记录当前选用的模板名 | 否（off 时） |
| `markov_regime_state` | 快照 | 结构体 | 当前/转移/步数等（无 `line` 键的副本） | 否 |
| `markov_regime_line` | 快照 + `main.py` 决策表 | 文本 | 展示用一行文案 | 否 |
| `markov_next_prob` | 快照 | `{chop,mid,trend}` | 下一状态经验概率 | 否 |
| `USE_MARKOV_THRESHOLD_TEMPLATE` | **未实现** | — | 对话稿中的全局开关 | — |
| `LONGXIA_USE_MARKOV_THRESHOLD_TEMPLATE` | **未实现** | — | 对话稿中的环境开关 | — |
| `experiment_markov_template` / `_enabled` / `_config` / `_line` | **未实现** | — | 对话稿中的调试字段 | — |
| `markov_template` | `backtest.py` → `summary.json` | experiment：`off`/`strict_chop`/`balanced`；main：`n/a` | 区分矩阵单次 run 的模板维度 | 否 |
| `win_rate_pct` / `sum_profit_pct` | `backtest.py` → `summary.json` | 数值 | 当前回测汇总（毛口径） | 否 |
| `win_rate_gross_pct` / `win_rate_net_pct` / `avg_net_profit_pct` / `sum_net_profit_pct` / `max_drawdown_net_pct` / `sharpe_net` | **未实现**（当前 `backtest.py` 无） | — | 对话稿中的净口径与质量指标 | — |
| `markov_optimized` | **未实现** | — | 对话稿中矩阵标记列 | — |
| `markov_optimized_compare_text` | **未实现** | — | 对话稿中自动对比文案 | — |
| `template_summary` | `scripts/backtest_matrix.py` → `matrix_report.json` | 按实验轨行聚合 | 各 `markov_template` 下平均单量/胜率/合计盈亏 | 否 |
| `markov_templates` / `LEVEL_MODES` | `scripts/run_backtest_autotask.sh` | profile 内 `:="${...:=...}"` | 覆盖矩阵维度而不改脚本 | 否 |

---

## 3. 启用模板前检查清单 + 一句话结论

### 检查清单（建议在把 `LONGXIA_MARKOV_TEMPLATE` 设为非 `off` 并重启前逐项勾选）

- [ ] 最近 **1～3 天** 决策页 **「行情状态（Markov）」** 有正常文案，非空或异常报错。
- [ ] `logs/market_regime_state.json`（若使用实盘累计）体积与写入频率可接受，无权限或磁盘问题。
- [ ] 实验轨样本量（笔数/天数）是否足以讨论「收紧/放宽」——避免极低样本下过度解读。
- [ ] **毛**胜率与合计盈亏%与 **off** 对比，波动是否在可解释范围内（当前矩阵**无**自动净口径/Sharpe 对比，需人工或后续开发）。
- [ ] 主观察池与实验轨若同时观察，**方向是否同向改善**（至少不互相矛盾到无法归因）。
- [ ] 是否出现 **单量骤降**（模板收紧导致）——业务上是否可接受。
- [ ] 高波动行情下是否 **误触发** 增多（人工翻决策页与虚拟/实验记录）。
- [ ] **回撤**是否在个人/团队容忍度内（当前回测 summary **未**内置 max_drawdown_net，需后续或外部工具）。
- [ ] **回滚方案明确**：将 `LONGXIA_MARKOV_TEMPLATE` 设回 **`off`** 或清空该环境变量并重启进程。
- [ ] Git 上是否存在可回退标签/commit（例如 `backup/2026-04-18-markov-matrix-baseline`），以便代码级复原。
- [ ] 与 `docs/upgrade_roadmap_v1.md` 路线不冲突：属增量试验，不替换主链路默认行为。

### 一句话结论

**建议现阶段仍以「默认 off + 观察矩阵与 Markov 行」为主，待净口径与（若需要的）状态映射策略表落地后再灰度开启非 `off` 模板；默认立场：谨慎，先观察再放量。**

---

*文档结束 · 可与本地笔记双向备份*
