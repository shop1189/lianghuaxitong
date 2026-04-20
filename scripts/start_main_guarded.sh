#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/longxia_system"
PY="$ROOT/venv/bin/python"
LOG="$ROOT/logs/start_main_guarded.log"
mkdir -p "$ROOT/logs"
cd "$ROOT"

echo "$(date -Is) [guarded-start] preflight check begin" | tee -a "$LOG"
if ! /usr/bin/python3 "$ROOT/scripts/critical_files_guard.py" --check --strict >> "$LOG" 2>&1; then
  echo "$(date -Is) [guarded-start] abort: critical files check failed" | tee -a "$LOG"
  exit 2
fi

echo "$(date -Is) [guarded-start] starting main.py" | tee -a "$LOG"
nohup "$PY" "$ROOT/main.py" >> "$ROOT/server.log" 2>&1 &
echo $! > "$ROOT/server.pid"
echo "$(date -Is) [guarded-start] pid=$(cat "$ROOT/server.pid")" | tee -a "$LOG"
