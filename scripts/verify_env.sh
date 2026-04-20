#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR=${1:-$HOME/projects/longxia_system}
cd "$PROJECT_DIR"

echo "[1/6] project dir"
pwd

echo "[2/6] python/pip"
source .venv/bin/activate
python --version
pip --version

echo "[3/6] dependency health"
python -m pip check

echo "[4/6] key packages"
python -m pip show ccxt pandas numpy numba aiohttp requests >/dev/null
echo "IMPORT_OK"

echo "[5/6] syntax check (safe)"
python -m py_compile main.py backtest.py live_trading.py

echo "[6/6] ssh check"
ssh -o BatchMode=yes ftcloud "echo SSH_OK && hostname"

echo "verify_env.sh completed."
