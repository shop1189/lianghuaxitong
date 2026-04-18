#!/usr/bin/env bash
# 一键打包「代码之外」的关键运行数据，便于下载到本机或上传云盘。
# 产出：backups/longxia_data_时间戳.tar.gz（目录 backups/ 在 .gitignore 中，不会进 Git）

set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$REPO/backups"
OUT="$REPO/backups/longxia_data_${STAMP}.tar.gz"

mapfile -t FILES < <(
  for f in \
    trade_memory.json \
    live_trading_state.json \
    bayes_beta_state.json \
    memos_v316_hook.json \
    trading_theory_library.json \
    entry_history.json \
    last_entry.json \
    preferences.json \
    meta.json \
    litellm_config.yaml \
    .env .env.prod .env.dev .env.test
  do
    [[ -f "$f" ]] && echo "$f"
  done
)

if ((${#FILES[@]} == 0)); then
  echo "未找到可打包的数据文件。"
  exit 1
fi

tar czf "$OUT" "${FILES[@]}"
echo "已生成: $OUT"
ls -lh "$OUT"
