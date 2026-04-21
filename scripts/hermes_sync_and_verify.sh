#!/usr/bin/env bash
set -euo pipefail

# 云端量化 → Hermes inbox 一键同步 + 强校验
# 默认同步：
# - docs/daily_market_notes.md      -> daily_market_notes.md
# - trade_memory.json               -> trade_memory.json
# - backtest_result.csv             -> backtest_result.csv
# - PROJECT_MEMORY.md               -> PROJECT_MEMORY.md
# 并重建 meta.json（含 schema_version/data_range/artifacts）

ROOT="/root/longxia_system"
DEST_USER="${HERMES_DEST_USER:-admin}"
DEST_HOST="${HERMES_DEST_HOST:-47.237.166.188}"
DEST_PORT="${HERMES_DEST_PORT:-22}"
DEST_DIR="${HERMES_DEST_DIR:-/opt/hermes-sync/inbox}"
SSH_KEY="${HERMES_SSH_KEY:-/root/.ssh/hermes_sync}"

STAMP="$(date +%Y%m%d_%H%M%S)"
STAGE="${HERMES_STAGE_DIR:-/tmp/hermes_inbox_stage_${STAMP}}"
PROOF_DIR="${HERMES_PROOF_DIR:-$ROOT/logs/hermes_sync_proofs}"
PROOF_FILE="$PROOF_DIR/proof_${STAMP}.log"

mkdir -p "$STAGE" "$PROOF_DIR"

copy_inputs() {
  cp -f "$ROOT/docs/daily_market_notes.md" "$STAGE/daily_market_notes.md"
  cp -f "$ROOT/trade_memory.json" "$STAGE/trade_memory.json"
  cp -f "$ROOT/backtest_result.csv" "$STAGE/backtest_result.csv"
  cp -f "$ROOT/PROJECT_MEMORY.md" "$STAGE/PROJECT_MEMORY.md"
}

build_meta() {
  STAGE_DIR="$STAGE" python3 - <<'PY'
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

stage = Path(os.environ["STAGE_DIR"])
files = [
    "daily_market_notes.md",
    "trade_memory.json",
    "backtest_result.csv",
    "PROJECT_MEMORY.md",
]
artifacts = []
oldest = None
latest = None
for name in files:
    p = stage / name
    st = p.stat()
    mt = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    oldest = mt if oldest is None or mt < oldest else oldest
    latest = mt if latest is None or mt > latest else latest
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    artifacts.append(
        {
            "path": name,
            "bytes": st.st_size,
            "mtime_utc": mt.isoformat().replace("+00:00", "Z"),
            "sha256_prefix": h.hexdigest()[:12],
        }
    )

meta = {
    "schema_version": "1.0",
    "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "data_range": {
        "start_utc": oldest.isoformat().replace("+00:00", "Z") if oldest else None,
        "end_utc": latest.isoformat().replace("+00:00", "Z") if latest else None,
    },
    "artifacts": artifacts,
    "changelog_one_liner": "refresh inbox freshness and schema-valid meta for Hermes health check",
}
(stage / "meta.json").write_text(
    json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("meta_generated")
PY
}

sync_remote() {
  rsync -azv --chmod=D755,F644 \
    -e "ssh -i $SSH_KEY -p $DEST_PORT" \
    "$STAGE/" "${DEST_USER}@${DEST_HOST}:${DEST_DIR}/"
}

remote_verify_block() {
  ssh -i "$SSH_KEY" -p "$DEST_PORT" "${DEST_USER}@${DEST_HOST}" \
    "hostname; stat -c '%y %s %n' ${DEST_DIR}/meta.json ${DEST_DIR}/daily_market_notes.md; head -n 5 ${DEST_DIR}/daily_market_notes.md"
  sha256sum "$STAGE/meta.json" "$STAGE/daily_market_notes.md"
  ssh -i "$SSH_KEY" -p "$DEST_PORT" "${DEST_USER}@${DEST_HOST}" \
    "sha256sum ${DEST_DIR}/meta.json ${DEST_DIR}/daily_market_notes.md"
  ssh -i "$SSH_KEY" -p "$DEST_PORT" "${DEST_USER}@${DEST_HOST}" \
    "python3 - <<'PY'
import json
p='${DEST_DIR}/meta.json'
d=json.load(open(p))
print('schema_version=',repr(d.get('schema_version')))
print('generated_at_utc=',d.get('generated_at_utc'))
print('data_range.end_utc=',d.get('data_range',{}).get('end_utc'))
PY"
}

{
  echo "[start_utc] $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[start_local] $(date +%Y-%m-%dT%H:%M:%S%z)"
  echo "[stage_dir] $STAGE"
  echo "[dest] ${DEST_USER}@${DEST_HOST}:${DEST_DIR} (port=$DEST_PORT)"
  copy_inputs
  build_meta
  echo "[sync] rsync begin"
  sync_remote
  echo "rsync_exit=0"
  echo "[verify] remote checks begin"
  remote_verify_block
  echo "[done_utc] $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} | tee "$PROOF_FILE"

echo "proof_file=$PROOF_FILE"
