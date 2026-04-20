#!/usr/bin/env bash
# 第三步：双轨最小验收（非大网格）
# 主轨 + 实验轨各跑 3d / 14d 窗口（1m K 线根数 = 天 * 1440）
# 用法：在项目根执行  bash scripts/smoke_dual_track_3d_14d.sh [SYMBOL]
# 依赖：source .venv 后已安装 pandas-ta 等主环境；实验轨与线上对齐见下方 export。
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source .venv/bin/activate

SYMBOL="${1:-SOL/USDT}"
OUT="${BASELINE_OUT_DIR:-outputs/baseline_smoke}"
mkdir -p "$OUT"

# 与线上实验轨对齐（云端 .env legacy + Markov 默认 off）
export LONGXIA_EXPERIMENT_MODE="${LONGXIA_EXPERIMENT_MODE:-legacy}"
export LONGXIA_MARKOV_TEMPLATE="${LONGXIA_MARKOV_TEMPLATE:-off}"
export LONGXIA_USE_MARKOV_THRESHOLD_TEMPLATE="${LONGXIA_USE_MARKOV_THRESHOLD_TEMPLATE:-0}"

# 1m：每自然日约 1440 根
bars_for_days() {
  local d="$1"
  echo $((d * 1440))
}

run_pair() {
  local days="$1"
  local limit
  limit="$(bars_for_days "$days")"
  local pfx="baseline_${days}d_$(echo "$SYMBOL" | tr / -)"

  echo "=== ${days}d limit=${limit} main ==="
  python backtest.py --symbol "$SYMBOL" --timeframe 1m --limit "$limit" \
    --level-mode main --entry-cooldown 2 --max-hold-bars 40 \
    --out-dir "$OUT" --out-prefix "${pfx}_main"

  echo "=== ${days}d limit=${limit} experiment legacy ==="
  python backtest.py --symbol "$SYMBOL" --timeframe 1m --limit "$limit" \
    --level-mode experiment --entry-cooldown 3 --max-hold-bars 120 \
    --out-dir "$OUT" --out-prefix "${pfx}_experiment"
}

run_pair 3
run_pair 14

echo "Done. Summaries under $OUT (grep total_trades in *_summary.json)."
