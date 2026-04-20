#!/usr/bin/env bash
set -euo pipefail
ROOT="/root/longxia_system"
PY="/usr/bin/python3"
mkdir -p "$ROOT/logs"
cd "$ROOT"
"$PY" "$ROOT/scripts/critical_files_guard.py" --check --strict >> "$ROOT/logs/critical_files_guard.log" 2>&1
