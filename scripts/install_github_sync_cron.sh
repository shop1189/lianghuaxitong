#!/usr/bin/env bash
# 安装：定时与 GitHub 双向同步（每 6 小时；带自动提交备份未忽略文件）
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
chmod +x "$REPO/scripts/github_bidirectional_sync.sh"
mkdir -p "$REPO/logs"

MARK_B="# LONGXIA_github_sync_BEGIN"
MARK_E="# LONGXIA_github_sync_END"
# 每 6 小时整点；自动提交 + 拉取 + 推送（.gitignore 外机密仍不会提交）
CRON_LINE="0 */6 * * * cd $REPO && LONGXIA_GIT_BACKUP_COMMIT=1 GIT_SYNC_AUTO_STASH=0 /bin/bash $REPO/scripts/github_bidirectional_sync.sh >> $REPO/logs/github_sync.log 2>&1"

TMP="$(mktemp)"
{
  crontab -l 2>/dev/null | awk -v b="$MARK_B" -v e="$MARK_E" '
    $0==b {skip=1; next}
    $0==e {skip=0; next}
    !skip {print}
  ' || true
  echo "$MARK_B"
  echo "$CRON_LINE"
  echo "$MARK_E"
} >"$TMP"
crontab "$TMP"
rm -f "$TMP"

echo "已安装 GitHub 双向同步：每 6 小时一次，LONGXIA_GIT_BACKUP_COMMIT=1"
echo "日志：$REPO/logs/github_sync.log"
echo ""
crontab -l
