# -*- coding: utf-8 -*-
"""
分批止盈（SL 优先，再按档 TP1→TP2→TP3）；仅当 ``LONGXIA_SCALED_EXIT=1`` 且记录含 ``scaled_mode`` 时生效。
与 ``first_exit_tick`` 的「单点整笔平仓」不同：同一时刻只判当前 stage 对应的一档。

默认不启用；未带 ``scaled_mode`` 的记录走原有整笔逻辑。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from utils.trade_exit_rules import profit_pct_at_bracket


def scaled_weights() -> Tuple[float, float, float]:
    """三档占**原始**名义的比例，默认 0.5 / 0.3 / 0.2。"""
    try:
        w1 = float(os.environ.get("LONGXIA_SCALED_W1", "0.5"))
        w2 = float(os.environ.get("LONGXIA_SCALED_W2", "0.3"))
        w3 = float(os.environ.get("LONGXIA_SCALED_W3", "0.2"))
    except ValueError:
        w1, w2, w3 = 0.5, 0.3, 0.2
    s = w1 + w2 + w3
    if s <= 1e-9:
        return 0.5, 0.3, 0.2
    return w1 / s, w2 / s, w3 / s


def _dir_for_exit(d: str) -> str:
    x = str(d or "")
    if x == "模拟入场":
        return "做多"
    return x


def scaled_hit_bracket(
    direction: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
    price: float,
    stage: int,
) -> Optional[str]:
    """
    返回本 snapshot 命中的档：``sl`` / ``tp1`` / ``tp2`` / ``tp3`` / None。
    顺序：先 SL（对剩余仓位全额），再仅当前 stage 的 TP 档。
    """
    p = float(price)
    d = _dir_for_exit(direction)
    e, s, a, b, c = float(entry), float(sl), float(tp1), float(tp2), float(tp3)
    if d == "做多":
        if p <= s:
            return "sl"
        if stage == 0 and p >= a:
            return "tp1"
        if stage == 1 and p >= b:
            return "tp2"
        if stage == 2 and p >= c:
            return "tp3"
    elif d == "做空":
        if p >= s:
            return "sl"
        if stage == 0 and p <= a:
            return "tp1"
        if stage == 1 and p <= b:
            return "tp2"
        if stage == 2 and p <= c:
            return "tp3"
    return None


def try_scaled_virtual_close(
    r: Dict[str, Any],
    price: float,
    close_iso: str,
) -> Optional[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
    """
    若 ``r`` 为带 ``scaled_mode`` 的未平仓虚拟单，尝试按现价平仓。

    返回：
      - ``None``：未触发或不应由分批逻辑处理；
      - ``(closed_leg, runner_or_none)``：用 ``closed_leg`` 整行替换原开仓行；若有 ``runner`` 则追加为新未平仓单。
    """
    if not r.get("scaled_mode") or r.get("profit") is not None:
        return None
    w1, w2, w3 = scaled_weights()
    stage = int(r.get("scaled_stage", 0) or 0)
    rem = float(r.get("scaled_remaining_orig", 1.0) or 1.0)
    if rem <= 1e-12:
        return None

    direction = str(r.get("direction") or "做多")
    entry = float(r["entry"])
    sl = float(r["sl"])
    tp1 = float(r["tp1"])
    tp2 = float(r["tp2"])
    tp3 = float(r["tp3"])

    br = scaled_hit_bracket(direction, entry, sl, tp1, tp2, tp3, float(price), stage)
    if br is None:
        return None

    sym = str(r.get("symbol") or "")
    gid = str(r.get("scaled_group_id") or r.get("entry_time") or "")
    last_sig = r.get("last_sig")
    date = str(r.get("date") or "")

    def _bracket_to_reason(b: str) -> str:
        return {"sl": "SL", "tp1": "TP1", "tp2": "TP2", "tp3": "TP3"}.get(b, "SL")

    def _px_for(b: str) -> float:
        return {"sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3}[b]

    closed = dict(r)
    closed["close_time"] = close_iso
    closed["close"] = round(_px_for(br), 6)
    closed["close_reason"] = _bracket_to_reason(br)
    closed["scaled_mode"] = False

    if br == "sl":
        pfull = profit_pct_at_bracket(
            _dir_for_exit(direction),
            entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            bracket="sl",
        )
        closed["profit"] = round(pfull * rem, 4)
        closed["scaled_leg"] = "sl_remainder"
        closed["scaled_weight"] = rem
        return closed, None

    # TP 档：按 stage 取占原始名义比例
    w_leg = (w1, w2, w3)[stage]
    if w_leg <= 0:
        return None
    pfull = profit_pct_at_bracket(
        _dir_for_exit(direction),
        entry,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        bracket=br,  # type: ignore[arg-type]
    )
    closed["profit"] = round(pfull * w_leg, 4)
    closed["scaled_leg"] = br
    closed["scaled_weight"] = w_leg

    new_rem = rem - w_leg
    if new_rem <= 1e-9:
        return closed, None

    runner_open_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    runner: Dict[str, Any] = {
        "date": date,
        "entry_time": runner_open_iso,
        "close_time": "—",
        "direction": direction,
        "entry": round(entry, 6),
        "sl": round(sl, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "tp3": round(tp3, 6),
        "close": None,
        "profit": None,
        "virtual_signal": True,
        "symbol": sym,
        "last_sig": last_sig,
        "scaled_mode": True,
        "scaled_stage": stage + 1,
        "scaled_remaining_orig": round(new_rem, 6),
        "scaled_group_id": gid,
        "scaled_parent_leg": br,
    }
    return closed, runner
