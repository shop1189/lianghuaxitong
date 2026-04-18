#!/usr/bin/env bash
# 安装：每小时第 20 分跑一次每日复盘（可重复执行，会替换本脚本写入的旧片段）
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
chmod +x "$REPO/scripts/run_daily_review.sh"
mkdir -p "$REPO/logs"

MARK_B="# LONGXIA_daily_review_cron_BEGIN"
MARK_E="# LONGXIA_daily_review_cron_END"

TMP="$(mktemp)"
{
  crontab -l 2>/dev/null | awk -v b="$MARK_B" -v e="$MARK_E" '
    $0==b {skip=1; next}
    $0==e {skip=0; next}
    skip {next}
    /run_daily_review\.sh/ {next}
    {print}
  ' || true
  echo "$MARK_B"
  echo "20 * * * * /bin/bash $REPO/scripts/run_daily_review.sh >> $REPO/logs/daily_strategy_review.log 2>&1"
  echo "$MARK_E"
} >"$TMP"
crontab "$TMP"
rm -f "$TMP"

echo "已安装：每小时 :20 执行 daily_strategy_review（服务器本地时间）。"
echo "日志：$REPO/logs/daily_strategy_review.log"
echo ""
echo "当前 crontab："
crontab -l
