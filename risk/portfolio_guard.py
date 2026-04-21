"""Portfolio level risk warnings (observe-only, Phase-1)."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from risk import reason_codes as rc


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return float(default)


def build_warnings(
    *,
    open_positions: List[Dict[str, Any]],
    new_side: str,
    new_notional_usdt: float,
    new_risk_usdt: float,
    equity_usdt: float,
    day_pnl_pct: float = 0.0,
) -> List[str]:
    warnings: List[str] = []
    eq = max(0.0, float(equity_usdt))
    if eq <= 0:
        return warnings

    max_dir_pct = _env_float("LONGXIA_RISK_MAX_DIRECTION_PCT", 0.015)
    max_port_pct = _env_float("LONGXIA_RISK_MAX_PORTFOLIO_PCT", 0.03)
    day_stop_pct = _env_float("LONGXIA_RISK_DAY_STOP_PCT", -0.015)

    same_dir_notional = 0.0
    for p in open_positions or []:
        if not isinstance(p, dict):
            continue
        if str(p.get("side") or "") == str(new_side):
            try:
                same_dir_notional += abs(float(p.get("notional_usdt", 0.0)))
            except Exception:
                pass
    same_dir_notional += abs(float(new_notional_usdt))

    # Phase-1: no exchange risk engine yet, approximate directional exposure by notional/equity.
    dir_exposure_pct = same_dir_notional / eq
    if dir_exposure_pct > max_dir_pct:
        warnings.append(rc.DIRECTION_EXPOSURE_HIGH)

    portfolio_risk_usdt = abs(float(new_risk_usdt))
    for p in open_positions or []:
        if not isinstance(p, dict):
            continue
        try:
            portfolio_risk_usdt += abs(float(p.get("risk_usdt", 0.0)))
        except Exception:
            pass
    portfolio_risk_pct = portfolio_risk_usdt / eq
    if portfolio_risk_pct > max_port_pct:
        warnings.append(rc.PORTFOLIO_RISK_HIGH)

    if float(day_pnl_pct) <= day_stop_pct:
        warnings.append(rc.DAY_RISK_STOP_HIT)

    return warnings
