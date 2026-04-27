# 回测端协作：净收益优先

## 目标
在“手续费+滑点+资金费率”口径下优化净收益，而不是只追求胜率。

## 必做项
- 使用 `config/backtest_netfirst_grid.env` 做网格回测。
- 输出每组参数的：
  - `gross_win_rate`
  - `net_win_rate`
  - `net_pnl_pct`
  - `expectancy_net`
  - `max_drawdown`
  - `trades_count`
- 过滤条件：`trades_count >= 80`。
- 最终按 `net_pnl_pct` 降序，并附前 10 组。

## 回执模板
- commit_hash:
- 回测区间:
- 样本币种:
- 成本口径（费率/滑点/资金费率）:
- 最优参数组:
- gross_win_rate:
- net_win_rate:
- net_pnl_pct:
- expectancy_net:
- max_drawdown:
- trades_count:
- 与当前线上参数对比结论（3条以内）:
