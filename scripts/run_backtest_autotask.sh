#!/usr/bin/env bash
# 自动回测矩阵（防重入）：超短线节奏用 lite，正式基线用 full。
#   lite — 约 15 分钟级 cron：少参数、较短 K 线，供前端「近实时」趋势
#   full — 每日一次：全参数 + 更长 K 线，作调参/版本对比基线
# 用法：run_backtest_autotask.sh [lite|full]
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
PROFILE="${1:-lite}"
LOCK="$REPO/logs/backtest_autotask.lock"
mkdir -p "$REPO/logs"

exec 200>"$LOCK"
if ! flock -n 200; then
  echo "$(date -Is) skip: another autotask is running (flock)"
  exit 0
fi

if [[ -x "$REPO/venv/bin/python3" ]]; then
  PY="$REPO/venv/bin/python3"
elif [[ -x "$REPO/.venv/bin/python3" ]]; then
  PY="$REPO/.venv/bin/python3"
else
  PY="python3"
fi

SYMS="SOL/USDT,BTC/USDT,ETH/USDT,DOGE/USDT,XRP/USDT,BNB/USDT"

case "$PROFILE" in
  lite)
    "$PY" "$REPO/scripts/backtest_matrix.py" \
      --symbols "$SYMS" \
      --timeframes 1m \
      --limit 1200 \
      --level-modes experiment,main \
      --entry-cooldowns 3,6 \
      --max-hold-bars 120 \
      --out-dir outputs/backtest_matrix_lite_auto
    ;;
  full)
    "$PY" "$REPO/scripts/backtest_matrix.py" \
      --symbols "$SYMS" \
      --timeframes 1m \
      --limit 4000 \
      --level-modes experiment,main \
      --entry-cooldowns 3,5,8 \
      --max-hold-bars 120 \
      --out-dir outputs/backtest_matrix_full_auto
    ;;
  *)
    echo "用法: $0 [lite|full]" >&2
    exit 1
    ;;
esac
