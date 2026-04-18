#!/usr/bin/env bash
# 兼容旧 crontab：等同于全量矩阵一次（转发到 autotask full）。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$REPO/scripts/run_backtest_autotask.sh" full
