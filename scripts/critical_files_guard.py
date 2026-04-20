#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键文件守护：
1) 生成基线（文件存在 + sha256 + 大小）
2) 周期巡检（缺失/篡改告警）
3) 输出状态 JSON + 可追加日志
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "logs"
BASELINE_PATH = LOG_DIR / "critical_files_baseline.json"
STATUS_PATH = LOG_DIR / "critical_files_guard_status.json"

# 按你这次事故保护最核心的主链路文件
CRITICAL_FILES = [
    "main.py",
    "live_trading.py",
    "data_fetcher.py",
    "data/fetcher.py",
    "evolution_core.py",
    "utils/trade_exit_rules.py",
    "utils/experiment_risk_state.py",
    "utils/experiment_track_filters.py",
    "scripts/run_daily_review.sh",
    "scripts/run_backtest_autotask.sh",
    "scripts/github_bidirectional_sync.sh",
]


@dataclass
class FileFingerprint:
    path: str
    size: int
    sha256: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _build_current_fingerprints(files: List[str]) -> Dict[str, FileFingerprint]:
    out: Dict[str, FileFingerprint] = {}
    for rel in files:
        p = REPO_ROOT / rel
        if not p.exists() or not p.is_file():
            continue
        out[rel] = FileFingerprint(path=rel, size=p.stat().st_size, sha256=_sha256(p))
    return out


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def init_baseline(files: List[str]) -> int:
    current = _build_current_fingerprints(files)
    missing = [f for f in files if f not in current]
    payload = {
        "generated_at_utc": _utc_now(),
        "repo_root": str(REPO_ROOT),
        "files_total": len(files),
        "files_present": len(current),
        "files_missing": missing,
        "fingerprints": {k: asdict(v) for k, v in current.items()},
    }
    _write_json(BASELINE_PATH, payload)
    if missing:
        print("baseline_created_with_missing_files")
        print(json.dumps({"missing": missing}, ensure_ascii=False))
        return 2
    print("baseline_created")
    print(str(BASELINE_PATH))
    return 0


def check_against_baseline() -> int:
    if not BASELINE_PATH.exists():
        _write_json(
            STATUS_PATH,
            {
                "checked_at_utc": _utc_now(),
                "ok": False,
                "reason": "baseline_not_found",
                "baseline_path": str(BASELINE_PATH),
            },
        )
        print("baseline_not_found")
        return 3

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    expected = baseline.get("fingerprints") or {}

    missing: List[str] = []
    changed: List[dict] = []

    for rel, fp in expected.items():
        p = REPO_ROOT / rel
        if not p.exists() or not p.is_file():
            missing.append(rel)
            continue
        cur_size = p.stat().st_size
        cur_sha = _sha256(p)
        exp_size = int(fp.get("size", -1))
        exp_sha = str(fp.get("sha256", ""))
        if cur_size != exp_size or cur_sha != exp_sha:
            changed.append(
                {
                    "path": rel,
                    "expected_size": exp_size,
                    "current_size": cur_size,
                    "expected_sha256": exp_sha,
                    "current_sha256": cur_sha,
                }
            )

    ok = not missing and not changed
    status = {
        "checked_at_utc": _utc_now(),
        "ok": ok,
        "missing_files": missing,
        "changed_files": changed,
        "baseline_path": str(BASELINE_PATH),
    }
    _write_json(STATUS_PATH, status)
    print(json.dumps(status, ensure_ascii=False))
    return 0 if ok else 2


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Critical files guard")
    p.add_argument("--init-baseline", action="store_true", help="Create/refresh baseline")
    p.add_argument("--check", action="store_true", help="Check against baseline")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Non-zero exit on check failure (recommended for cron/startup)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.init_baseline and not args.check:
        print("use --init-baseline or --check", file=sys.stderr)
        return 1

    code = 0
    if args.init_baseline:
        code = init_baseline(CRITICAL_FILES)
    if args.check:
        code = check_against_baseline()

    if args.strict:
        return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

