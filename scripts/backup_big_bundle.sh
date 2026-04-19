#!/usr/bin/env bash
# 全量备份：整目录打包（含 venv、memos_ref、.git、trade_memory 等），体积约 1GB+ 属正常。
# 新建包前会删除 backups/ 下所有旧 .tar.gz，仅保留本次一份，作为「当前权威离线包」。
# 产出：backups/longxia_FULL_<时间戳>.tar.gz 与符号链接 longxia_FULL_LATEST.tar.gz
# 注意：*.tar.gz 在 .gitignore 中，不会进 Git；请自行把该文件拷网盘/U 盘。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$REPO/backups"
TMP="/tmp/longxia_full_${STAMP}_$$.tar.gz"
NAME="longxia_FULL_${STAMP}.tar.gz"
OUT="$REPO/backups/$NAME"

echo "[backup_big_bundle] 仓库: $REPO"
echo "[backup_big_bundle] 清理旧包: $REPO/backups/*.tar.gz"
shopt -s nullglob
for f in "$REPO"/backups/*.tar.gz; do
  rm -f "$f"
done

echo "[backup_big_bundle] 正在全量打包（含 venv / memos_ref / .git，排除 backups 目录本身）…"
# 排除 backups：避免把历史包打进包内，且输出文件写在 backups/
tar czf "$TMP" \
  -C "$REPO" \
  --exclude='./backups' \
  .

mv -f "$TMP" "$OUT"
ln -sfn "$NAME" "$REPO/backups/longxia_FULL_LATEST.tar.gz"

echo "[backup_big_bundle] 完成: $OUT"
ls -lh "$OUT" "$REPO/backups/longxia_FULL_LATEST.tar.gz"
