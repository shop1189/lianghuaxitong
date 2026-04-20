# 第三步：双轨最小验收（3d / 14d）— 执行记录

- **命令**：`bash scripts/smoke_dual_track_3d_14d.sh`（默认 `SOL/USDT`、1m、`legacy` + Markov off）
- **产出目录**：`outputs/baseline_smoke/`
- **执行环境**：WSL Ubuntu，项目 `.venv`

## 结果汇总（stdout / summary.json）

| 窗口 | 轨 | limit | total_trades | sum_net_profit_pct | max_drawdown_net_pct | win_rate_net_pct |
|------|-----|-------|--------------|--------------------|----------------------|------------------|
| 3d | main | 4320 | 61 | -12.11 | 12.11 | 0.0 |
| 3d | experiment | 4320 | 10 | -3.33 | 3.81 | 40.0 |
| 14d | main | 20160 | 62 | -12.93 | 12.93 | 0.0 |
| 14d | experiment | 20160 | 10 | -3.33 | 3.81 | 40.0 |

## 备注

- **主轨**：3d 与 14d 笔数、净盈亏略有差异，符合更长样本预期。
- **实验轨**：3d 与 14d 的 **total_trades 与净指标完全相同**；`summary.json` 中 `limit` 分别为 4320 / 20160，文件不同。可能原因包括：实验轨成交全部落在两窗重叠的尾部区间、或策略对更长历史段未新增入场等。**若需深究**：`diff` 两份 `*_experiment_cd3_trades.csv` 或比对 `entry_time_ms` 分布。

## 对应文件（相对仓库根）

- `outputs/baseline_smoke/baseline_3d_SOL-USDT_main_*_summary.json`
- `outputs/baseline_smoke/baseline_3d_SOL-USDT_experiment_*_summary.json`
- `outputs/baseline_smoke/baseline_14d_SOL-USDT_main_*_summary.json`
- `outputs/baseline_smoke/baseline_14d_SOL-USDT_experiment_*_summary.json`
