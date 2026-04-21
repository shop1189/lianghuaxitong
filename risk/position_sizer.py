"""Single-trade position sizing helpers (Phase-1)."""

from __future__ import annotations

from typing import Dict


def size_position(
    *,
    equity_usdt: float,
    risk_per_trade_pct: float,
    entry: float,
    stop: float,
    fee_slippage_buffer_pct: float,
) -> Dict[str, float]:
    eq = max(0.0, float(equity_usdt))
    risk_pct = max(0.0, float(risk_per_trade_pct))
    e = float(entry)
    s = float(stop)
    buf = max(0.0, float(fee_slippage_buffer_pct))

    stop_pct = 0.0
    if e > 0:
        stop_pct = abs(e - s) / e
    effective_stop_pct = max(0.0, stop_pct + buf)
    risk_usdt = eq * risk_pct
    suggested_notional_usdt = 0.0
    if effective_stop_pct > 0:
        suggested_notional_usdt = risk_usdt / effective_stop_pct

    return {
        "risk_usdt": risk_usdt,
        "stop_pct": stop_pct,
        "effective_stop_pct": effective_stop_pct,
        "suggested_notional_usdt": max(0.0, suggested_notional_usdt),
    }
