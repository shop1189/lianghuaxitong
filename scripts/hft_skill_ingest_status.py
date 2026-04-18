#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比 hermes_outbox meta.sha256 与本地 digest / 上次 ingest 标记（运维提示，不向量化）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

META = ROOT / "hermes_outbox" / "hft_strategy_skill_library.meta.json"
DIGEST = ROOT / "data" / "hft_skill_brain_digest.json"
MARK = ROOT / "logs" / ".hft_skill_last_ingest.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mark-ingested",
        action="store_true",
        help="将当前 digest 的 sha256 记为已人工确认（写入 logs 旁路标记，可选）",
    )
    args = ap.parse_args()
    sha_meta = ""
    if META.exists():
        try:
            sha_meta = str(json.loads(META.read_text(encoding="utf-8")).get("sha256") or "")
        except Exception:
            pass
    sha_digest = ""
    nlines = 0
    if DIGEST.exists():
        try:
            d = json.loads(DIGEST.read_text(encoding="utf-8"))
            sha_digest = str(d.get("sha256") or "")
            lines = d.get("lines") or []
            nlines = len(lines) if isinstance(lines, list) else int(d.get("line_count") or 0)
        except Exception:
            pass
    need = sha_meta and sha_meta != sha_digest
    print(f"meta_sha256={sha_meta[:16] if sha_meta else '—'}…")
    print(f"digest_sha256={sha_digest[:16] if sha_digest else '—'}… digest_lines={nlines}")
    print(f"recommend_ingest={'yes' if need else 'no'}")
    if args.mark_ingested and DIGEST.exists() and sha_digest:
        MARK.parent.mkdir(parents=True, exist_ok=True)
        MARK.write_text(
            json.dumps({"marked_sha256": sha_digest}, indent=2),
            encoding="utf-8",
        )
        print("marked ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
