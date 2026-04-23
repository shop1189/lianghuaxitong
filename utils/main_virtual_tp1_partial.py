# -*- coding: utf-8 -*-
"""
主观察池虚拟单（trade_memory · virtual_signal）：TP1 命中后部分锁定 + 抬损至保本，余仓博 TP2/TP3。
与 evolution_core 实验轨逻辑对齐；字段前缀 main_* 便于与实验轨区分。

需与 ``LONGXIA_SCALED_EXIT`` 分批模式二选一：新开仓若启用本规则，则不写 scaled_mode（见 live_trading 开仓）。
"""
from __future__ import annotations

import os
from typing import Any, Dict

from utils.exit_feature_flags import main_virtual_tp1_partial_enabled
from utils.trade_exit_rules import first_exit_tick, first_exit_tick_post_tp1

_REASON = {"sl": "SL", "tp1": "TP1", "tp2": "TP2", "tp3": "TP3"}


def _partial_ratio() -> float:
    try:
        pr = float(
            os.environ.get(
                "LONGXIA_MAIN_VIRTUAL_PARTIAL_RATIO",
                os.environ.get("LONGXIA_EXPERIMENT_PARTIAL_RATIO", "0.5"),
            )
        )
    except ValueError:
        pr = 0.5
    return max(0.05, min(pr, 0.95))


def _be_buffer() -> float:
    try:
        return float(
            os.environ.get(
                "LONGXIA_MAIN_VIRTUAL_BE_BUFFER_PCT",
                os.environ.get("LONGXIA_EXPERIMENT_BE_BUFFER_PCT", "0.0002"),
            )
        )
    except ValueError:
        return 0.0002


def _arm(r: Dict[str, Any], hit: Any) -> None:
    pr = _partial_ratio()
    be_buf = _be_buffer()
    entry = float(r["entry"])
    d = str(r.get("direction") or "做多")
    if d == "模拟入场":
        d = "做多"
    if d == "做多":
        r["sl"] = round(entry * (1.0 + be_buf), 6)
    elif d == "做空":
        r["sl"] = round(entry * (1.0 - be_buf), 6)
    r["main_tp1_done"] = True
    r["main_partial_ratio"] = round(pr, 4)
    r["main_locked_pct"] = round(float(hit[1]) * pr, 4)


def _blended(r: Dict[str, Any], hit: Any) -> float:
    pr = float(r.get("main_partial_ratio") or 0.5)
    locked = float(r.get("main_locked_pct") or 0.0)
    p_full = float(hit[1])
    return round(locked + (1.0 - pr) * p_full, 2)


def try_apply_main_virtual_tp1_partial(
    r: Dict[str, Any],
    price: float,
    close_iso: str,
) -> bool:
    """
    若适用则在本函数内完成「抬损 / 平仓」并直接改写字典 r。
    返回 True：本 tick 已处理（调用方应 persist 且不再走整笔 first_exit_tick）。
    返回 False：交回原有整笔平仓逻辑。
    """
    if not main_virtual_tp1_partial_enabled():
        return False
    if r.get("profit") is not None:
        return False

    direction = str(r.get("direction") or "做多")
    entry = float(r["entry"])
    sl = float(r["sl"])
    tp1 = float(r["tp1"])
    tp2 = float(r["tp2"])
    tp3 = float(r["tp3"])
    p = float(price)

    if r.get("main_tp1_done"):
        hit = first_exit_tick_post_tp1(direction, entry, sl, tp2, tp3, p)
        if hit is None:
            return False
        r["profit"] = _blended(r, hit)
        r["close"] = round(float(hit[2]), 6)
        r["close_time"] = close_iso
        br = str(hit[0])
        if br == "sl":
            r["close_reason"] = "BE"
        else:
            r["close_reason"] = _REASON.get(br, br.upper())
        r["tp1_hit"] = True
        r["partial_ratio"] = r.get("main_partial_ratio")
        r["partial_locked_pct"] = r.get("main_locked_pct")
        return True

    hit = first_exit_tick(direction, entry, sl, tp1, tp2, tp3, p)
    if hit is None:
        return False
    if str(hit[0]) == "tp1":
        _arm(r, hit)
        return True
    return False
