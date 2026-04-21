"""Leverage recommendation policy (Phase-1)."""

from __future__ import annotations

from typing import Dict, Optional


def recommend_leverage(
    *,
    symbol: str,
    atr_pct: Optional[float] = None,
    liquidity_tier: Optional[str] = None,
) -> Dict[str, object]:
    tier = str(liquidity_tier or "mid").strip().lower()
    if tier == "high":
        max_lv = 20
    elif tier == "low":
        max_lv = 8
    else:
        max_lv = 12

    rec = min(8, max_lv)
    reason = [f"tier={tier}"]
    if atr_pct is not None:
        try:
            a = float(atr_pct)
            if a >= 0.015:
                rec = min(rec, 3)
                reason.append("high_volatility")
            elif a >= 0.008:
                rec = min(rec, 5)
                reason.append("mid_volatility")
            else:
                reason.append("low_volatility")
        except Exception:
            reason.append("atr_invalid")
    else:
        reason.append("atr_missing")

    rec = max(1, min(int(rec), int(max_lv)))
    return {
        "recommended_leverage": rec,
        "max_allowed_leverage": int(max_lv),
        "reason": ",".join(reason),
        "symbol": symbol,
    }
