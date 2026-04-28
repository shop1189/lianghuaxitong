#!/usr/bin/env bash
# 专用回测机「日课·轻量矩阵」：main only，参数 B，目录 outputs/backtest_daily_<UTC>_<git_sha>/
# 用法：cron 例（北京时间 10:00 / 22:00 ≈ UTC 02:00 / 14:00，按机器时区自行调整）：
#   0 2,14 * * * /path/to/longxia_system/scripts/daily_backtest_main_B.sh >> /path/to/longxia_system/logs/daily_backtest.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOCK="$ROOT/logs/backtest_matrix_daily.lock"
mkdir -p "$ROOT/logs"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[daily_backtest_main_B] skip: another holder on $LOCK"
  exit 0
fi

export GIT_TERMINAL_PROMPT=0
# 子模块损坏时 git fetch 可能失败；日课以「跑出矩阵」为主，同步失败仅告警
if git fetch origin 2>/dev/null; then
  git checkout main 2>/dev/null || true
  git -c fetch.recurseSubmodules=false -c submodule.recurse=false pull --ff-only 2>/dev/null || true
else
  echo "[daily_backtest_main_B] warn: git fetch failed (e.g. broken submodule memos_ref); using current tree."
fi

UTC_TS="$(date -u +%Y%m%dT%H%M%SZ)"
GIT_SHA="$(git rev-parse --short HEAD)"
OUT_REL="outputs/backtest_daily_${UTC_TS}_${GIT_SHA}"
OUT="$ROOT/$OUT_REL"
mkdir -p "$OUT"

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

set -a
# shellcheck source=/dev/null
source "$ROOT/config/backtest_matrix_daily_B.env"
# 可选：费率/路径等（矩阵若不需要密钥可不加载）
if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT/.env" || true
fi
set +a

"$PY" "$ROOT/scripts/backtest_matrix.py" \
  --symbols "SOL/USDT,BTC/USDT,ETH/USDT,DOGE/USDT,XRP/USDT,BNB/USDT" \
  --timeframes "1m" \
  --limit 1200 \
  --level-modes main \
  --entry-cooldowns "3,6" \
  --max-hold-bars 120 \
  --markov-templates off \
  --out-dir "$OUT_REL"

"$PY" "$ROOT/scripts/print_matrix_receipt.py" --out-dir "$OUT" --matrix-dir-relative "$OUT_REL"
