#!/usr/bin/env bash
# EverOS PoC 只读同步：不写交易、不启 Web；可由 cron 低频调用。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-/usr/bin/python3}"
cd "$ROOT"
exec "$PY" "$ROOT/scripts/everos_poc_memory_sync.py" "$@"
