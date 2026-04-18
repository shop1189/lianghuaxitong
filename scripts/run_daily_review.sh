#!/usr/bin/env bash
set -euo pipefail
ROOT="/root/longxia_system"
PY="${PYTHON:-/usr/bin/python3}"
cd "$ROOT"
exec "$PY" "$ROOT/scripts/daily_strategy_review.py" "$@"
