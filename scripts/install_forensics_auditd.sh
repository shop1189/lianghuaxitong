#!/usr/bin/env bash
set -euo pipefail

# 安装并启用 Linux 审计：用于“谁在何时改/删了关键文件”的追责
RULE_FILE="/etc/audit/rules.d/longxia-critical.rules"

if ! command -v auditctl >/dev/null 2>&1; then
  apt-get update
  apt-get install -y auditd audispd-plugins
fi

cat > "$RULE_FILE" <<'EOF'
-w /root/longxia_system/main.py -p wa -k longxia_critical
-w /root/longxia_system/live_trading.py -p wa -k longxia_critical
-w /root/longxia_system/data_fetcher.py -p wa -k longxia_critical
-w /root/longxia_system/evolution_core.py -p wa -k longxia_critical
-w /root/longxia_system/scripts/run_backtest_autotask.sh -p wa -k longxia_critical
-w /root/longxia_system/scripts/run_daily_review.sh -p wa -k longxia_critical
-w /root/longxia_system/scripts/github_bidirectional_sync.sh -p wa -k longxia_critical
EOF

augenrules --load
systemctl enable --now auditd
echo "auditd_installed_and_rules_loaded"
echo "query_cmd: ausearch -k longxia_critical -i | tail -n 200"
