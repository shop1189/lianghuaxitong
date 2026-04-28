# 专用回测机：日课矩阵与最短回执（与云端对接）

云端结论摘要：代码锚点 `426e8515`；**默认快轨参数采用 B 组**（`EDGE=3`、`MIN_SCORE=0.35`、`REQUIRE_STRONG=0`）；Hermes 三 sha 已对齐；`apply_coinglass_score_nudge` 若存在占位实现，后续应在仓库统一为与线上一致的单一逻辑。

## 环境提示（WSL + Cursor）

若 `git commit` / `git push` 报 `option trailer requires a value` 或莫名打开 `editor`，多半是 **PATH 里 Cursor 的 `git` 包装器** 抢在 `/usr/bin/git` 之前。解决：执行 git 时临时使用 `PATH=/usr/bin:/bin`（`daily_backtest_main_B.sh` 已在开头把系统路径前置）。

## 一、固定「日课」两条线（cron）

| 任务 | 频率 | 产出 | 说明 |
|------|------|------|------|
| 日课·轻量矩阵 | 每天 1～2 次（例：北京时间 10:00、22:00） | `outputs/backtest_daily_<UTC>_<git_sha>/` + `*_matrix_summary.json` | **仅 `main`**；6 币；`1m`；`limit=1200`；`cd3,cd6`；env 见 `config/backtest_matrix_daily_B.env` |
| 日课·快照回执 | 矩阵跑完后立即 | 终端一段固定字段正文 | 见下文「最短回执」；可复制到约定渠道，或单独分支只提交 `receipts/*.md`（勿把大体积 `outputs/*.json` 提交进 `main`） |

**单进程串行**：脚本已用 `flock` 锁 `logs/backtest_matrix_daily.lock`，避免两个 `backtest_matrix` 并发抢写。

## 二、「加重」触发（手动或每周）

- 云端合并了 `live_trading` / 回测 / Coinglass 相关逻辑 → 当天加跑全矩阵或多 `limit` 档；目录名建议仍带 **UTC 时间戳 + git sha**。
- 本地改了 `.env` 里费率/滑点 → 重跑 B 组对比前后 `sum_net_profit_pct` 与 `max_drawdown_net_pct`。

## 三、命令（仓库内真实入口）

在仓库根目录执行（路径按机器修改）：

```bash
chmod +x scripts/daily_backtest_main_B.sh   # 一次性
./scripts/daily_backtest_main_B.sh
```

等价手动命令（与脚本一致）：

```bash
cd /path/to/longxia_system
git fetch origin && git checkout main && git pull --ff-only
set -a && source config/backtest_matrix_daily_B.env && source .env 2>/dev/null || true && set +a
UTC_TS=$(date -u +%Y%m%dT%H%M%SZ)
GIT_SHA=$(git rev-parse --short HEAD)
OUT="outputs/backtest_daily_${UTC_TS}_${GIT_SHA}"
.venv/bin/python scripts/backtest_matrix.py \
  --symbols SOL/USDT,BTC/USDT,ETH/USDT,DOGE/USDT,XRP/USDT,BNB/USDT \
  --timeframes 1m --limit 1200 --level-modes main \
  --entry-cooldowns 3,6 --max-hold-bars 120 --markov-templates off \
  --out-dir "$OUT"
.venv/bin/python scripts/print_matrix_receipt.py --out-dir "$(pwd)/$OUT" --matrix-dir-relative "$OUT"
```

**跑完 3 检查**：

1. `*_matrix_summary.json` 存在，且 **main** 的 `total_trades` 合计 > 0。  
2. 回执中 `trade_weighted net_win_rate` 可读。  
3. 若关心 Coinglass 列：`coinglass_score_nudge.notes` 不应出现 **ImportError**（回执脚本会提示）。

## 四、最短回执模板（`print_matrix_receipt.py` 已按此格式打印）

```text
git_sha: ______
matrix_dir: outputs/______
level_mode: main
symbols: SOL,BTC,ETH,DOGE,XRP,BNB
cooldowns: cd3,cd6
param_profile: B (EDGE=3, MIN_SCORE=0.35, REQUIRE_STRONG=0)
sum_net_profit_pct (main cells sum): ______
trade_weighted net_win_rate: ______
max_drawdown_net_pct (worst main cell): ______
notes: ______
```

云端收到后：**登记 + 决定是否把 B 写进默认 env/文档**；无需本地反复确认。

## 与 `config/exp_fastlane_B.env` 的关系

`exp_fastlane_B.env` 当前可能仍承载 **HTTP/演示快轨** 等变量；**矩阵日课 B** 单独使用 `config/backtest_matrix_daily_B.env`，避免与线上端口/开关混在一处。云端合并参数后再考虑合并为单一配置源。
