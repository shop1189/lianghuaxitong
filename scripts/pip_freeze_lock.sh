#!/usr/bin/env bash
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source .venv/bin/activate
mkdir -p outputs/env
TS="$(date +%Y%m%d_%H%M%S)"
OUT="outputs/env/requirements_lock_${TS}.txt"
pip freeze >"$OUT"
echo "Wrote $OUT ($(wc -l <"$OUT") lines)"
