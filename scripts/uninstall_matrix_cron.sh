#!/usr/bin/env bash
# 移除 install_matrix_cron.sh 写入的 crontab 片段（含新旧标记）
set -euo pipefail
LEGACY_B="# LONGXIA_backtest_matrix_cron_BEGIN"
LEGACY_E="# LONGXIA_backtest_matrix_cron_END"
MARK_B="# LONGXIA_matrix_schedule_BEGIN"
MARK_E="# LONGXIA_matrix_schedule_END"
MARK_OLD_B="# LONGXIA_backtest_autotask_BEGIN"
MARK_OLD_E="# LONGXIA_backtest_autotask_END"

TMP="$(mktemp)"
crontab -l 2>/dev/null | awk -v lb="$LEGACY_B" -v le="$LEGACY_E" -v b="$MARK_B" -v e="$MARK_E" -v ob="$MARK_OLD_B" -v oe="$MARK_OLD_E" '
  $0==lb || $0==b || $0==ob {skip=1; next}
  $0==le || $0==e || $0==oe {skip=0; next}
  !skip {print}
' >"$TMP" || true
crontab "$TMP"
rm -f "$TMP"
echo "已移除 LONGXIA 矩阵定时任务（含 legacy / schedule）。"
crontab -l 2>/dev/null || echo "（crontab 已空）"
