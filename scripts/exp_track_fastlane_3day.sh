#!/usr/bin/env bash
# 本脚本属「回测 / 快轨编排」路径：探活跟随 LONGXIA_HTTP_PORT（缺省 8080），与 exp_fastlane_*.env 一致。
# 主 Web / Phase-1 默认实例在 18080（见 docs/RISK_TRUTH_LAYER_PHASE1.md）；勿在快轨里写死 18080。
set -euo pipefail

ROOT_DIR="${1:-$HOME/projects/longxia_system}"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  echo "missing .venv in $ROOT_DIR" >&2
  exit 2
fi

source .venv/bin/activate

TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="outputs/exp_fastlane_${TS}"
LOG_DIR="$RUN_DIR/logs"
mkdir -p "$LOG_DIR"

RECEIPT_JSONL="$RUN_DIR/receipts.jsonl"
RECEIPT_MD="$RUN_DIR/receipts.md"
ROLLBACK_ENV="$RUN_DIR/rollback_baseline.env"
A_ENV="config/exp_fastlane_A.env"
B_ENV="config/exp_fastlane_B.env"
DAY1_A_SEC="${DAY1_A_SEC:-43200}"
DAY1_B_SEC="${DAY1_B_SEC:-43200}"
DAY2_FREEZE_SEC="${DAY2_FREEZE_SEC:-86400}"
AUTO_ONLINE="${AUTO_ONLINE:-1}"

capture_baseline() {
  {
    printf "LONGXIA_EXPERIMENT_MODE=%s\n" "${LONGXIA_EXPERIMENT_MODE:-kronos_light}"
    printf "LONGXIA_EXPERIMENT_TRACK=%s\n" "${LONGXIA_EXPERIMENT_TRACK:-1}"
    printf "LONGXIA_KRONOS_MIN_PROB_EDGE=%s\n" "${LONGXIA_KRONOS_MIN_PROB_EDGE:-5}"
    printf "LONGXIA_EXPERIMENT_MIN_SCORE_ABS=%s\n" "${LONGXIA_EXPERIMENT_MIN_SCORE_ABS:-0.45}"
    printf "LONGXIA_EXPERIMENT_DAY_STOP_PCT=%s\n" "${LONGXIA_EXPERIMENT_DAY_STOP_PCT:--1.0}"
  } > "$ROLLBACK_ENV"
}

ensure_stopped() {
  pkill -f "python3 main.py" >/dev/null 2>&1 || true
  sleep 1
}

start_group() {
  local group="$1"
  local env_file="$2"
  local run_log="$LOG_DIR/${group}_run.log"
  local app_log="$LOG_DIR/${group}_app.log"
  ensure_stopped
  set -a
  source "$env_file"
  set +a
  : > "$app_log"
  nohup python3 main.py >> "$app_log" 2>&1 &
  local pid="$!"
  sleep 8
  local api_json="{}"
  curl -s "http://127.0.0.1:${LONGXIA_HTTP_PORT:-8080}/api/version" > "$LOG_DIR/${group}_api_version.json" || true
  if [ -s "$LOG_DIR/${group}_api_version.json" ]; then
    api_json="$(<"$LOG_DIR/${group}_api_version.json")"
  fi
  {
    echo "group=$group"
    echo "env_file=$env_file"
    echo "start_time=$(date -Is)"
    echo "pid=$pid"
    echo "head=$(git rev-parse HEAD)"
    echo "branch=$(git branch --show-current)"
    echo "api_version=$api_json"
  } > "$run_log"
}

collect_metrics() {
  local group="$1"
  local duration_sec="$2"
  local app_log="$LOG_DIR/${group}_app.log"
  local run_log="$LOG_DIR/${group}_run.log"
  sleep "$duration_sec"
  local metrics
  metrics="$(python3 - "$app_log" <<'PY'
from pathlib import Path
import re, sys
t = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore").lower()
def c(p): return len(re.findall(p, t))
print(f"trigger_count={c(r'signal|open|close|entry|tp1|tp2|tp3')}")
print(f"pause_count={c(r'pause|paused')}")
print(f"circuit_count={c(r'circuit|熔断|day_stop')}")
print(f"traceback_count={c(r'traceback')}")
print(f"error_count={c(r'error|exception|fatal')}")
PY
)"
  {
    echo "end_time=$(date -Is)"
    echo "duration_sec=$duration_sec"
    echo "$metrics"
  } >> "$run_log"
}

append_receipt() {
  local group="$1"
  local env_file="$2"
  local run_log="$LOG_DIR/${group}_run.log"
  python3 - "$group" "$env_file" "$run_log" "$RECEIPT_JSONL" <<'PY'
import json, sys
from pathlib import Path
group, env_file, run_log, out = sys.argv[1:]
kv = {}
for line in Path(run_log).read_text(encoding="utf-8", errors="ignore").splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        kv[k] = v
env = {}
for line in Path(env_file).read_text(encoding="utf-8", errors="ignore").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
obj = {
    "time_range": f"{kv.get('start_time','')} -> {kv.get('end_time','')}",
    "head": kv.get("head",""),
    "branch": kv.get("branch",""),
    "group": group,
    "pid": kv.get("pid",""),
    "env": env,
    "trigger_count": int(kv.get("trigger_count","0") or 0),
    "error_count": int(kv.get("error_count","0") or 0),
    "traceback_count": int(kv.get("traceback_count","0") or 0),
    "pause_count": int(kv.get("pause_count","0") or 0),
    "circuit_count": int(kv.get("circuit_count","0") or 0),
    "api_version": kv.get("api_version","{}"),
}
with Path(out).open("a", encoding="utf-8") as f:
    f.write(json.dumps(obj, ensure_ascii=False) + "\n")
PY
}

pick_winner() {
  python3 - "$RECEIPT_JSONL" <<'PY'
import json, sys
from pathlib import Path
rows = [json.loads(x) for x in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if x.strip()]
ab = [x for x in rows if x["group"] in ("A","B")]
if len(ab) < 2:
    print("A")
    raise SystemExit
def score(x):
    return x["error_count"]*50 + x["traceback_count"]*100 + x["circuit_count"]*10 + x["pause_count"]*5 + max(0, x["trigger_count"]-2000)
a = next(x for x in ab if x["group"]=="A")
b = next(x for x in ab if x["group"]=="B")
print("A" if score(a) <= score(b) else "B")
PY
}

build_md() {
  python3 - "$RECEIPT_JSONL" "$RECEIPT_MD" <<'PY'
import json, sys
from pathlib import Path
src, out = map(Path, sys.argv[1:])
rows = [json.loads(x) for x in src.read_text(encoding="utf-8").splitlines() if x.strip()] if src.exists() else []
lines = ["# Experiment Track Fastlane Receipts"]
for r in rows:
    err = int(r["error_count"]) + int(r["traceback_count"])
    lines.extend([
        "",
        f"- 时间段: {r['time_range']}",
        f"- HEAD: {r['head']}",
        f"- 组别: {r['group']}",
        f"- PID: {r['pid']}",
        f"- 开/平触发次数: {r['trigger_count']}",
        f"- 异常: {'无' if err == 0 else err}",
        f"- 熔断/暂停: circuit={r['circuit_count']}, pause={r['pause_count']}",
    ])
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

day0() {
  git fetch origin
  local dirty
  dirty="$(git status --porcelain=v1 || true)"
  if [ -n "$dirty" ]; then
    {
      echo "git_pull=skipped_dirty_worktree"
      echo "dirty_files:"
      echo "$dirty"
      echo "HEAD=$(git rev-parse HEAD)"
      echo "origin/main=$(git rev-parse origin/main 2>/dev/null || echo unknown)"
    } > "$RUN_DIR/git_preflight.txt"
  else
    git pull --ff-only origin main
    echo "git_pull=ok_ff_only" > "$RUN_DIR/git_preflight.txt"
  fi
  python3 -m py_compile live_trading.py utils/experiment_track_filters.py utils/experiment_risk_state.py evolution_core.py data/fetcher.py data_fetcher.py main.py
}

day0
capture_baseline

start_group "A" "$A_ENV"
collect_metrics "A" "$DAY1_A_SEC"
append_receipt "A" "$A_ENV"

start_group "B" "$B_ENV"
collect_metrics "B" "$DAY1_B_SEC"
append_receipt "B" "$B_ENV"
build_md

WINNER="$(pick_winner)"
echo "winner=$WINNER" > "$RUN_DIR/meta.txt"
WIN_ENV="$A_ENV"
[ "$WINNER" = "B" ] && WIN_ENV="$B_ENV"

start_group "DAY2_${WINNER}" "$WIN_ENV"
collect_metrics "DAY2_${WINNER}" "$DAY2_FREEZE_SEC"
append_receipt "DAY2_${WINNER}" "$WIN_ENV"
build_md

ensure_stopped
if [ "$AUTO_ONLINE" = "1" ]; then
  set -a
  source "$WIN_ENV"
  set +a
  nohup python3 main.py >> "$LOG_DIR/day3_online.log" 2>&1 &
  ONLINE_PID="$!"
  {
    echo "online_at=$(date -Is)"
    echo "online_group=$WINNER"
    echo "online_pid=$ONLINE_PID"
    echo "rollback_env=$ROLLBACK_ENV"
  } >> "$RUN_DIR/meta.txt"
else
  {
    echo "online_at=SKIPPED"
    echo "online_group=$WINNER"
    echo "online_pid=SKIPPED"
    echo "rollback_env=$ROLLBACK_ENV"
  } >> "$RUN_DIR/meta.txt"
fi
