# -*- coding: utf-8 -*-
"""
平仓档位判定与盈亏 %（与 `evolution_core.TradeMemory.check_close_trade` 公式对齐）。

- **判定顺序**：**SL → TP3 → TP2 → TP1**（先命中先平）。
- **实验轨 TP1 部分止盈后**：同顺序但不含 TP1，见 ``first_exit_tick_post_tp1``（SL 已抬至保本附近）。
- **tick 模式**：仅使用当前价 `price`（实验轨 `ai_evo.tick`、虚拟单同步里传入的 last）。
- 盈亏百分比与 `check_close_trade` / `save_record` 使用的口径一致；**成交价**在 `evolution_core` 里仍记 **当时传入的 current_price**（非强行改写成理论 TP 价）。
"""
from __future__ import annotations

from typing import Optional, Tuple

Bracket = str  # "sl" | "tp1" | "tp2" | "tp3"


def profit_pct_at_bracket(
    direction: str,
    entry: float,
    *,
    sl: float = 0.0,
    tp1: float = 0.0,
    tp2: float = 0.0,
    tp3: float = 0.0,
    bracket: Bracket = "sl",
) -> float:
    """给定已命中的档位，返回与 evolution_core 一致的 profit（%）。"""
    e = float(entry)
    if direction == "做多":
        if bracket == "sl":
            return round((float(sl) / e - 1) * 100, 2)
        px = float(tp3 if bracket == "tp3" else (tp2 if bracket == "tp2" else tp1))
        return round((px / e - 1) * 100, 2)
    if direction == "做空":
        if bracket == "sl":
            return round((e - float(sl)) / e * 100, 2)
        px = float(tp3 if bracket == "tp3" else (tp2 if bracket == "tp2" else tp1))
        return round((e - px) / e * 100, 2)
    return 0.0


def first_exit_tick(
    direction: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
    price: float,
) -> Optional[Tuple[Bracket, float, float]]:
    """
    单点 tick：若 `price` 触发某一档，返回 (档位, profit_%, 该档价格)。

    虚拟单里「模拟入场」按做多处理，与现有 live_trading 一致。
    """
    d = str(direction or "")
    if d == "模拟入场":
        d = "做多"
    e, s, a, b, c = float(entry), float(sl), float(tp1), float(tp2), float(tp3)
    p = float(price)
    if d == "做多":
        if p <= s:
            return ("sl", round((s / e - 1) * 100, 2), s)
        if p >= c:
            return ("tp3", round((c / e - 1) * 100, 2), c)
        if p >= b:
            return ("tp2", round((b / e - 1) * 100, 2), b)
        if p >= a:
            return ("tp1", round((a / e - 1) * 100, 2), a)
    elif d == "做空":
        if p >= s:
            return ("sl", round((e - s) / e * 100, 2), s)
        if p <= c:
            return ("tp3", round((e - c) / e * 100, 2), c)
        if p <= b:
            return ("tp2", round((e - b) / e * 100, 2), b)
        if p <= a:
            return ("tp1", round((e - a) / e * 100, 2), a)
    return None


def first_exit_tick_post_tp1(
    direction: str,
    entry: float,
    sl: float,
    tp2: float,
    tp3: float,
    price: float,
) -> Optional[Tuple[Bracket, float, float]]:
    """
    TP1 已部分止盈并抬损至保本后：仅判断 SL(实为保本附近) / TP3 / TP2，顺序与 ``first_exit_tick`` 一致（先 SL，再 TP3→TP2）。
    不含 TP1。
    """
    d = str(direction or "")
    if d == "模拟入场":
        d = "做多"
    e, s, b, c = float(entry), float(sl), float(tp2), float(tp3)
    p = float(price)
    if d == "做多":
        if p <= s:
            return ("sl", round((s / e - 1) * 100, 2), s)
        if p >= c:
            return ("tp3", round((c / e - 1) * 100, 2), c)
        if p >= b:
            return ("tp2", round((b / e - 1) * 100, 2), b)
    elif d == "做空":
        if p >= s:
            return ("sl", round((e - s) / e * 100, 2), s)
        if p <= c:
            return ("tp3", round((e - c) / e * 100, 2), c)
        if p <= b:
            return ("tp2", round((e - b) / e * 100, 2), b)
    return None


def virtual_hit_profit_and_close_px(
    direction: str,
    price: float,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
) -> Optional[Tuple[float, float]]:
    """
    供 `live_trading._virtual_hit_and_close` 使用：返回 (profit_pct, close_px)。

    `close_px` 取触发档位价格（6 位小数），与原先虚拟单写入习惯一致。
    """
    hit = first_exit_tick(direction, entry, sl, tp1, tp2, tp3, price)
    if hit is None:
        return None
    _br, profit_pct, fill_px = hit
    return profit_pct, round(float(fill_px), 6)
