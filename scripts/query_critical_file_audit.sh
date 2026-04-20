#!/usr/bin/env bash
set -euo pipefail

# 查询关键文件审计记录（默认今天）
SINCE="${1:-today}"
echo "[query] ausearch -k longxia_critical -ts ${SINCE}"
ausearch -k longxia_critical -ts "$SINCE" -i | tail -n 400
