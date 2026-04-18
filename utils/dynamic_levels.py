# -*- coding: utf-8 -*-
"""
基于近期波动（收盘价近似 ATR%）微调 SL/TP 与入场距离；仅当 ``LONGXIA_DYNAMIC_LEVELS=1`` 时由 live_trading 调用。
默认不启用，不改变任何价位。
"""
from __future__ import annotations

from typing import List, Tuple


def _atr_pct_proxy(closes: List[float], period: int = 14) -> float:
    """用收盘价单期收益率绝对均值近似波动%（无高低价时的轻量代理）。"""
    if len(closes) < period + 2:
        return 0.0
    tail = [float(x) for x in closes[-(period + 1) :]]
    s = 0.0
    for i in range(1, len(tail)):
        a, b = tail[i - 1], tail[i]
        if abs(a) < 1e-15:
            continue
        s += abs((b - a) / a)
    return (s / max(1, len(tail) - 1)) * 100.0


def widen_levels_from_closes(
    entry: float,
    direction: str,
    levels: Tuple[float, float, float, float],
    closes: List[float],
    *,
    low_vol_pct: float = 0.04,
    high_vol_pct: float = 0.12,
    widen_max: float = 0.12,
) -> Tuple[float, float, float, float]:
    """
    波动高于 ``high_vol_pct`` 时略放宽各档与入场距离；低于 ``low_vol_pct`` 时略收紧。
    对 SL/TP 使用同一距离系数，保持相对顺序；若破坏几何则回退原档。
    """
    e = float(entry)
    sl, tp1, tp2, tp3 = (float(levels[0]), float(levels[1]), float(levels[2]), float(levels[3]))
    atrp = _atr_pct_proxy(closes)
    if atrp <= 0:
        return sl, tp1, tp2, tp3
    if atrp < low_vol_pct:
        m = -0.03
    elif atrp > high_vol_pct:
        m = min(widen_max, (atrp - high_vol_pct) * 0.5 + 0.04)
    else:
        m = 0.0
    factor = 1.0 + m
    factor = max(0.92, min(1.15, factor))

    d = str(direction or "")
    if d == "模拟入场":
        d = "做多"

    def scale_short() -> Tuple[float, float, float, float]:
        nsl = e + (sl - e) * factor
        ntp1 = e + (tp1 - e) * factor
        ntp2 = e + (tp2 - e) * factor
        ntp3 = e + (tp3 - e) * factor
        return nsl, ntp1, ntp2, ntp3

    def scale_long() -> Tuple[float, float, float, float]:
        nsl = e + (sl - e) * factor
        ntp1 = e + (tp1 - e) * factor
        ntp2 = e + (tp2 - e) * factor
        ntp3 = e + (tp3 - e) * factor
        return nsl, ntp1, ntp2, ntp3

    if d == "做空":
        nsl, ntp1, ntp2, ntp3 = scale_short()
        ok = ntp3 <= ntp2 <= ntp1 <= e <= nsl
    elif d == "做多":
        nsl, ntp1, ntp2, ntp3 = scale_long()
        ok = nsl <= e <= ntp1 <= ntp2 <= ntp3
    else:
        return sl, tp1, tp2, tp3
    if not ok:
        return sl, tp1, tp2, tp3
    return nsl, ntp1, ntp2, ntp3
