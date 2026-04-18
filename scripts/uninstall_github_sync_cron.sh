#!/usr/bin/env bash
set -euo pipefail
MARK_B="# LONGXIA_github_sync_BEGIN"
MARK_E="# LONGXIA_github_sync_END"
TMP="$(mktemp)"
crontab -l 2>/dev/null | awk -v b="$MARK_B" -v e="$MARK_E" '
  $0==b {skip=1; next}
  $0==e {skip=0; next}
  !skip {print}
' >"$TMP" || true
crontab "$TMP"
rm -f "$TMP"
echo "已移除 LONGXIA GitHub 同步定时任务。"
crontab -l 2>/dev/null || true
