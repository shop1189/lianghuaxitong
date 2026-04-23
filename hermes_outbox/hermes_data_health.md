# Hermes 数据健康检查（数据健康优先）

**生成时间（UTC）**: 2026-04-23T15:50:01Z

## 可用性结论

**暂不可用**

## 下一步（1 条）

更新 daily_market_notes.md（含当日/昨日日期或刷新文件）并同步到 Hermes inbox。

---

## 检查明细

### 1) trade_memory.json

- 可解析: **是** 
- 记录数: **1057**
- 最近一条时间: **2026-04-12**

### 2) backtest_result.csv

- 可解析: **是** 
- 表头: `['timestamp_utc', 'symbol', 'timeframe', 'bars', 'win_rate_pct', 'profit_factor', 'max_drawdown_pct', 'annual_return_pct', 'monthly_return_ann12_pct', 'monthly_return_compound_pct', 'sharpe_ratio', 'trades_count', 'avg_trades_per_day', 'commission_rate', 'kelly_size_cap', 'strategy_label', 'signal_cooldown_bars', 'weak_vol_exit_count', 'weak_vol_exits_note', 'edge_filter_full_sample_pct', 'edge_filter_path_pct', 'edge_filter_path_hits', 'edge_filter_path_checks', 'best_gene_name', 'best_gene_score', 'win_rate', 'max_drawdown', 'sharpe', 'trade_count']`
- 必需列（或同义）覆盖: win_rate / max_drawdown / sharpe / trade_count → **{'win_rate': True, 'max_drawdown': True, 'sharpe': True, 'trade_count': True}**
- 四列齐全: **是**

### 3) PROJECT_MEMORY.md

- 存在: **是**
- 最后修改: **2026-04-22T12:15:35**

### 4) daily_market_notes.md

- 存在: **是**
- 正文解析日期: **2026-04-21**
- 采用日期（正文或文件修改日）: **2026-04-22**
- 是否为今天或昨天: **否**

### 5) meta.json（批次元数据，与量化侧对齐）

- 状态: **ok**  
- schema_version: **1.0**
- generated_at_utc: **2026-04-16T04:10:01Z**
- data_range: **{'start_utc': '2026-04-11T00:00:00Z', 'end_utc': '2026-04-16T04:05:26Z'}**

### 6) 整体状态

- **状态**: **YELLOW**
- **原因**: 市场笔记日期非今/昨日（以正文日期或文件修改日为准）

---

*本报告仅描述数据可用性，不包含交易建议或策略推荐。*
