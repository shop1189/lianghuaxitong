#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR=${1:-$HOME/projects/longxia_system}
PY_BIN=${PY_BIN:-python3}

echo "[1/5] install base packages"
sudo apt-get update
sudo apt-get install -y git rsync openssh-client python3 python3-venv python3-pip

echo "[2/5] ensure project dir exists"
mkdir -p "$PROJECT_DIR"

echo "[3/5] create venv"
cd "$PROJECT_DIR"
rm -rf .venv
$PY_BIN -m venv .venv

echo "[4/5] install deps"
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
pip install -r requirements.txt

echo "[5/5] done"
echo "setup_new_machine.sh completed."
