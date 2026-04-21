"""Capital truth store (Phase-1, file source only)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from risk import reason_codes as rc

_ROOT = Path(__file__).resolve().parent.parent
_CAPITAL_FILE = _ROOT / "state" / "risk_capital_snapshot.json"


def _ttl_sec() -> int:
    try:
        return max(1, int(os.environ.get("LONGXIA_RISK_CAPITAL_TTL_SEC", "600")))
    except Exception:
        return 600


def load_capital_snapshot() -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    if not _CAPITAL_FILE.exists():
        warnings.append(rc.CAPITAL_FILE_MISSING)
        return {
            "equity_usdt": 0.0,
            "free_margin_usdt": 0.0,
            "open_positions": [],
            "updated_at": "",
            "source": "missing",
        }, warnings

    try:
        raw = json.loads(_CAPITAL_FILE.read_text(encoding="utf-8"))
    except Exception:
        warnings.append(rc.CAPITAL_JSON_INVALID)
        return {
            "equity_usdt": 0.0,
            "free_margin_usdt": 0.0,
            "open_positions": [],
            "updated_at": "",
            "source": "invalid",
        }, warnings

    required = ("equity_usdt", "free_margin_usdt", "open_positions", "updated_at", "source")
    missing = [k for k in required if k not in raw]
    if missing:
        warnings.append(rc.CAPITAL_FIELDS_MISSING)

    try:
        eq = float(raw.get("equity_usdt", 0.0))
    except Exception:
        eq = 0.0
    try:
        fm = float(raw.get("free_margin_usdt", 0.0))
    except Exception:
        fm = 0.0
    pos = raw.get("open_positions")
    if not isinstance(pos, list):
        pos = []
    updated_at = str(raw.get("updated_at") or "")
    source = str(raw.get("source") or "manual")

    try:
        updated_epoch = float(updated_at)
    except Exception:
        updated_epoch = 0.0
    if updated_epoch <= 0 or (time.time() - updated_epoch) > _ttl_sec():
        warnings.append(rc.CAPITAL_STALE)

    return {
        "equity_usdt": max(0.0, eq),
        "free_margin_usdt": max(0.0, fm),
        "open_positions": pos,
        "updated_at": updated_at,
        "source": source,
    }, warnings
