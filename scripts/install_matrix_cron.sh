#!/usr/bin/env bash
# 一键安装：双层频率（可重复执行，会先替换本脚本写入的旧片段）
#   lite：每 15 分钟 — 轻量快照
#   full：每日 00:35 — 全量基线
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
chmod +x "$REPO/scripts/run_backtest_autotask.sh" "$REPO/scripts/run_backtest_matrix_cron.sh"
mkdir -p "$REPO/logs"

LEGACY_B="# LONGXIA_backtest_matrix_cron_BEGIN"
LEGACY_E="# LONGXIA_backtest_matrix_cron_END"
MARK_B="# LONGXIA_matrix_schedule_BEGIN"
MARK_E="# LONGXIA_matrix_schedule_END"

TMP="$(mktemp)"
{
  crontab -l 2>/dev/null | awk -v lb="$LEGACY_B" -v le="$LEGACY_E" -v b="$MARK_B" -v e="$MARK_E" '
    $0==lb || $0==b {skip=1; next}
    $0==le || $0==e {skip=0; next}
    skip {next}
    /run_backtest_autotask\.sh/ {next}
    {print}
  ' || true
  echo "$MARK_B"
  echo "*/15 * * * * /bin/bash $REPO/scripts/run_backtest_autotask.sh lite >> $REPO/logs/backtest_matrix_lite.log 2>&1"
  echo "35 0 * * * /bin/bash $REPO/scripts/run_backtest_autotask.sh full >> $REPO/logs/backtest_matrix_full.log 2>&1"
  echo "$MARK_E"
} >"$TMP"
crontab "$TMP"
rm -f "$TMP"

echo "已安装：每 15 分钟 lite + 每日 00:35 full（服务器本地时间）。"
echo "日志：$REPO/logs/backtest_matrix_lite.log 与 $REPO/logs/backtest_matrix_full.log"
echo ""
echo "当前 crontab："
crontab -l
