#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/longxia_system"
LOG="$ROOT/logs/critical_guard_cron_install.log"
mkdir -p "$ROOT/logs"

BEGIN="# LONGXIA_critical_guard_BEGIN"
END="# LONGXIA_critical_guard_END"
JOB1="*/5 * * * * /root/longxia_system/scripts/run_critical_files_guard.sh"
JOB2="@reboot /root/longxia_system/scripts/run_critical_files_guard.sh"

TMP="$(mktemp)"
crontab -l 2>/dev/null > "$TMP" || true

awk -v b="$BEGIN" -v e="$END" '
  $0==b {skip=1; next}
  $0==e {skip=0; next}
  !skip {print}
' "$TMP" > "${TMP}.clean"

{
  cat "${TMP}.clean"
  echo "$BEGIN"
  echo "$JOB1"
  echo "$JOB2"
  echo "$END"
} | crontab -

rm -f "$TMP" "${TMP}.clean"
echo "$(date -Is) installed critical guard cron" >> "$LOG"
echo "installed"
