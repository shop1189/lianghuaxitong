#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动将 Hermes outbox 技能库 md 解析进 data/hft_skill_brain_digest.json，
供决策页「书本提示 / Hermes 技能库」行使用。

建议 cron：每天北京时间 09:12（晚于 Hermes 约 09:05 导出 + 本机 rsync），或 */30 * * * *。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from utils.hft_skill_brain import run_ingest_from_outbox

    ap = argparse.ArgumentParser(description="Hermes HFT 技能库 → 本地 digest")
    ap.add_argument("--force", action="store_true", help="忽略 sha256 未变化，强制重解析")
    args = ap.parse_args()
    ok, msg = run_ingest_from_outbox(force=args.force)
    print(msg)
    if ok:
        return 0
    if msg.startswith("unchanged") or msg.startswith("skip"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
