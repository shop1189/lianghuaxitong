#!/usr/bin/env bash
# 将一次日课 outputs 复制到 receipts/daily/… 供提交到远端（outputs/ 仍 gitignore）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAILY_DIR_NAME="${1:?usage: package_daily_receipt.sh <backtest_daily_YYYYMMDDTHHMMSSZ_gitsha>}"
SRC="$ROOT/outputs/$DAILY_DIR_NAME"
[[ -d "$SRC" ]] || { echo "missing $SRC"; exit 1; }
SUM=$(ls "$SRC"/*matrix_summary.json | head -1)
PREFIX=$(basename "$SUM" _matrix_summary.json)
DEST="$ROOT/receipts/daily/${PREFIX}_main_B"
mkdir -p "$DEST"
cp "$SRC/${PREFIX}_matrix_summary.json" "$DEST/matrix_summary.json"
[[ -f "$SRC/${PREFIX}_matrix_report.json" ]] && cp "$SRC/${PREFIX}_matrix_report.json" "$DEST/matrix_report.json" || true
"$ROOT/.venv/bin/python" "$ROOT/scripts/print_matrix_receipt.py" \
  --out-dir "$SRC" \
  --matrix-dir-relative "outputs/$DAILY_DIR_NAME" \
  >"$DEST/receipt.txt"
echo "packaged -> $DEST"
ls -la "$DEST"
