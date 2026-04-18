#!/usr/bin/env bash
# 一键「复原点」：数据快照 + 代码树归档 + git bundle（venv 不打包，复原后需 pip install -r）
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
DEST="${LONGXIA_BACKUP_ROOT:-/root/longxia_backups}"
mkdir -p "$DEST" "$REPO/backups"

HEAD="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo 'no-git')"
BRANCH="$(git -C "$REPO" branch --show-current 2>/dev/null || echo 'no-git')"
NOTE="$DEST/RESTORE_${STAMP}.txt"

{
  echo "longxia_system 复原点  $STAMP"
  echo "生成主机: $(hostname)"
  echo "Git HEAD: $HEAD"
  echo "分支: $BRANCH"
  echo ""
  echo "包含文件："
  echo "  1) longxia_data_${STAMP}.tar.gz — 关键 JSON/配置（在 repo/backups/）"
  echo "  2) longxia_tree_${STAMP}.tar.gz — 项目目录（已排除 venv）"
  echo "  3) longxia_git_${STAMP}.bundle — git 全分支 bundle（需已安装 git）"
  echo ""
  echo "复原步骤（示例）："
  echo "  cd /root"
  echo "  mv longxia_system longxia_system.bak.\$STAMP   # 可选"
  echo "  tar -xzf $DEST/longxia_tree_${STAMP}.tar.gz"
  echo "  cd longxia_system && python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt  # 若有"
  echo "  tar -xzf $REPO/backups/longxia_data_${STAMP}.tar.gz -C longxia_system   # 在解压后的目录内执行时路径需对应"
  echo "  或：先解压 longxia_data_*.tar.gz 内单文件到项目根覆盖"
  echo "  git clone longxia_git_${STAMP}.bundle longxia_from_bundle   # 可选：仅从 bundle 恢复仓库"
  echo ""
} >"$NOTE"

# 1) 数据（沿用现有脚本；若无任何数据文件则该脚本会报错，不阻断整包）
bash "$REPO/scripts/backup_full_snapshot.sh" 2>&1 | tee -a "$NOTE" || true
DATA_TAR=""
shopt -s nullglob
for f in "$REPO"/backups/longxia_data_*.tar.gz; do
  [[ "$f" -nt "${DATA_TAR:-/dev/null}" ]] && DATA_TAR="$f"
done

TREE_OUT="$DEST/longxia_tree_${STAMP}.tar.gz"
tar --exclude='longxia_system/venv' \
  --exclude='longxia_system/.venv' \
  --exclude='longxia_system/**/__pycache__' \
  --exclude='longxia_system/**/.pytest_cache' \
  -czf "$TREE_OUT" -C "$(dirname "$REPO")" "$(basename "$REPO")"

BUNDLE_OUT="$DEST/longxia_git_${STAMP}.bundle"
if git -C "$REPO" rev-parse HEAD &>/dev/null; then
  git -C "$REPO" bundle create "$BUNDLE_OUT" --all
else
  BUNDLE_OUT="(跳过：非 git 仓库)"
fi

{
  echo ""
  echo "----"
  echo "tree: $TREE_OUT ($(du -h "$TREE_OUT" | cut -f1))"
  echo "data: ${DATA_TAR:-未生成}"
  echo "bundle: $BUNDLE_OUT"
  echo "说明: $NOTE"
} | tee -a "$NOTE"

ls -lh "$TREE_OUT" "$NOTE" 2>/dev/null
[[ -f "$DEST/longxia_git_${STAMP}.bundle" ]] && ls -lh "$DEST/longxia_git_${STAMP}.bundle"
[[ -n "$DATA_TAR" ]] && ls -lh "$DATA_TAR"

echo "OK: $NOTE"
