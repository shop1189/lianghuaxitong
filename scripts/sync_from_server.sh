#!/usr/bin/env bash
set -euo pipefail

REMOTE=${1:-ftcloud}
REMOTE_DIR=${2:-/root/longxia_system/}
LOCAL_DIR=${3:-$HOME/projects/longxia_system/}

mkdir -p "$LOCAL_DIR"

echo "[1/2] sync code/config (fast, safe)"
rsync -avz --info=progress2 \
  --exclude='.git/' \
  --exclude='venv/' \
  --exclude='.venv/' \
  --exclude='*.tar.gz' \
  --exclude='*.zip' \
  --exclude='*.log' \
  --exclude='outputs/' \
  --exclude='backups/' \
  "${REMOTE}:${REMOTE_DIR}" "$LOCAL_DIR"

echo "[2/2] sync done"
echo "sync_from_server.sh completed."
