# -*- coding: utf-8 -*-
"""
Hermes HFT 技能库 → 本地「理论节选」自动入脑（供决策页书本提示展示）。

- 真源：`hermes_outbox/hft_strategy_skill_library.md` + `hft_strategy_skill_library.meta.json`（sha256）
- 产出：`data/hft_skill_brain_digest.json`（节选行）
- 不写入 trade_memory、不下单；仅影响快照字段与页面「书本提示 / Hermes 技能库」行。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

_REPO = Path(__file__).resolve().parent.parent
HERMES_MD = _REPO / "hermes_outbox" / "hft_strategy_skill_library.md"
HERMES_META = _REPO / "hermes_outbox" / "hft_strategy_skill_library.meta.json"
DATA_DIR = _REPO / "data"
DIGEST_PATH = DATA_DIR / "hft_skill_brain_digest.json"
LOGS_DIR = _REPO / "logs"
LAST_INGEST_PATH = LOGS_DIR / ".hft_skill_last_ingest.json"


def _parse_md_to_lines(text: str, max_lines: int = 80) -> List[str]:
    """从技能库 Markdown 抽取短句（标题行 + 列表行），上限 max_lines。"""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2]
    out: List[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("```"):
            continue
        if s.startswith("###"):
            t = s.replace("###", "").strip()
            if t:
                out.append(t[:500])
        elif s.startswith("- ") or s.startswith("* "):
            out.append(s[2:].strip()[:500])
        if len(out) >= max_lines:
            break
    return out


def _read_meta_sha256() -> str:
    if not HERMES_META.exists():
        return ""
    try:
        meta = json.loads(HERMES_META.read_text(encoding="utf-8"))
        return str(meta.get("sha256") or "").strip()
    except Exception:
        return ""


def load_hermes_digest_lines() -> List[str]:
    """供 live_trading 合并「Hermes_HFT技能库」条目。"""
    if not DIGEST_PATH.exists():
        return []
    try:
        d = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))
        lines = d.get("lines")
        if isinstance(lines, list):
            return [str(x).strip() for x in lines if str(x).strip()]
    except Exception:
        pass
    return []


def snapshot_brain_meta() -> Dict[str, Any]:
    """写入 get_v313 快照的展示字段（不下单）。"""
    empty = {
        "hft_skill_brain_line_count": 0,
        "hft_skill_brain_sha256": "",
        "hft_skill_brain_preview": "",
        "hft_skill_brain_ingested_at": "",
    }
    if not DIGEST_PATH.exists():
        return dict(empty)
    try:
        d = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(empty)
    lines = d.get("lines") or []
    n = len(lines) if isinstance(lines, list) else int(d.get("line_count") or 0)
    prev = str(lines[0]) if isinstance(lines, list) and lines else ""
    return {
        "hft_skill_brain_line_count": n,
        "hft_skill_brain_sha256": str(d.get("sha256") or ""),
        "hft_skill_brain_preview": prev[:400],
        "hft_skill_brain_ingested_at": str(d.get("ingested_at_utc") or ""),
    }


def run_ingest_from_outbox(force: bool = False) -> Tuple[bool, str]:
    """
    若 meta.sha256 相对上次 digest 有变（或 force），解析 md 并写入 digest。
    返回 (ok, message)。
    """
    if not HERMES_MD.exists():
        return False, "skip: hermes_outbox/hft_strategy_skill_library.md 不存在"
    sha = _read_meta_sha256()
    if not sha:
        return False, "skip: meta.json 无 sha256"
    if DIGEST_PATH.exists() and not force:
        try:
            old = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))
            if str(old.get("sha256") or "") == sha:
                return True, f"unchanged (digest already matches sha256 {sha[:12]}…)"
        except Exception:
            pass
    try:
        md_text = HERMES_MD.read_text(encoding="utf-8")
    except Exception as ex:
        return False, f"read md failed: {ex}"
    lines = _parse_md_to_lines(md_text, 80)
    if not lines:
        return False, "parse: no lines extracted"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "sha256": sha,
        "ingested_at_utc": now,
        "source_md": "hermes_outbox/hft_strategy_skill_library.md",
        "lines": lines,
        "line_count": len(lines),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DIGEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    LAST_INGEST_PATH.write_text(
        json.dumps({"sha256": sha, "ingested_at_utc": now}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True, f"ok: ingested {len(lines)} lines from Hermes skill md (sha256 {sha[:12]}…)"


