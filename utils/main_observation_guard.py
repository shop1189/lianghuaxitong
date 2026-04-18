# -*- coding: utf-8 -*-
"""
主观察池（虚拟 memos）附加防护层：回调防追单、BTC 锚定、EMA 追价距离、同向 SL 后冷却。
默认全部关闭（环境变量为 0/false/off），不改变现有行为；逐项开启后叠加生效。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from indicator_upgrade import ema
from utils.dynamic_levels import _atr_pct_proxy


def _env_on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _f(x: object, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def main_pullback_state(
    klines: List[Dict[str, Any]],
    t1h: str,
    t4h: str,
) -> Dict[str, Any]:
    """
    识别 1m 结构上的「相对近期极值的回撤/反抽」，用于防趋势追单。
    direction: down_pullback | up_pullback | none
    """
    out: Dict[str, Any] = {
        "active": False,
        "deep": False,
        "direction": "none",
        "reason": "",
    }
    if not _env_on("LONGXIA_MAIN_PULLBACK_GUARD", "0"):
        return out
    if not klines or len(klines) < 80:
        return out
    try:
        closes = [float(k["close"]) for k in klines]
        highs = [float(k["high"]) for k in klines]
        lows = [float(k["low"]) for k in klines]
    except Exception:
        return out
    lb = int(os.environ.get("LONGXIA_MAIN_PULLBACK_LOOKBACK_BARS", "72"))
    lb = max(20, min(lb, len(klines) - 2))
    retrace_thr = float(os.environ.get("LONGXIA_MAIN_PULLBACK_RETRACE_PCT", "0.9"))
    gap_pct = float(os.environ.get("LONGXIA_MAIN_PULLBACK_EMA_GAP_PCT", "0.25"))
    deep_mult = float(os.environ.get("LONGXIA_MAIN_PULLBACK_DEEP_MULT", "1.5"))

    seg_h = highs[-lb:]
    seg_l = lows[-lb:]
    px = closes[-1]
    recent_high = max(seg_h)
    recent_low = min(seg_l)
    s = pd.Series(closes, dtype=float)
    e13 = float(ema(s, 13).iloc[-1])
    e21 = float(ema(s, 21).iloc[-1])

    bull_bg = (t1h != "下跌" and t4h != "下跌") and (
        t1h == "上涨" or t4h == "上涨"
    )
    bear_bg = (t1h != "上涨" and t4h != "上涨") and (
        t1h == "下跌" or t4h == "下跌"
    )

    rh = max(recent_high, 1e-12)
    rl = max(recent_low, 1e-12)
    drop_from_high_pct = (recent_high - px) / rh * 100.0
    bounce_from_low_pct = (px - recent_low) / rl * 100.0

    if bull_bg and drop_from_high_pct >= retrace_thr:
        deep = drop_from_high_pct >= retrace_thr * deep_mult
        ema_pull = (e13 > px) and ((e13 - px) / px * 100.0 >= gap_pct)
        out["active"] = True
        out["deep"] = deep or ema_pull
        out["direction"] = "down_pullback"
        out["reason"] = (
            f"多头背景下自近{lb}根高点回撤 {drop_from_high_pct:.2f}% "
            f"(阈值≥{retrace_thr}%)"
        )
        return out

    if bear_bg and bounce_from_low_pct >= retrace_thr:
        deep = bounce_from_low_pct >= retrace_thr * deep_mult
        ema_pull = (px > e13) and ((px - e13) / px * 100.0 >= gap_pct)
        out["active"] = True
        out["deep"] = deep or ema_pull
        out["direction"] = "up_pullback"
        out["reason"] = (
            f"空头背景下自近{lb}根低点反抽 {bounce_from_low_pct:.2f}% "
            f"(阈值≥{retrace_thr}%)"
        )
        return out

    return out


def btc_anchor_state(btc_klines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """BTC 自近端极值回撤/反抽是否过大（用于全市场锚定，默认关）。"""
    out: Dict[str, Any] = {
        "active": False,
        "risk_off_long": False,
        "risk_off_short": False,
        "drop_from_high_pct": None,
        "bounce_from_low_pct": None,
        "reason": "",
    }
    if not _env_on("LONGXIA_MAIN_BTC_ANCHOR_GUARD", "0"):
        return out
    if not btc_klines or len(btc_klines) < 80:
        return out
    try:
        closes = [float(k["close"]) for k in btc_klines]
        highs = [float(k["high"]) for k in btc_klines]
        lows = [float(k["low"]) for k in btc_klines]
    except Exception:
        return out
    lb = int(os.environ.get("LONGXIA_MAIN_BTC_LOOKBACK_BARS", "72"))
    lb = max(20, min(lb, len(btc_klines) - 2))
    pct_floor = float(os.environ.get("LONGXIA_MAIN_BTC_PULLBACK_MIN_PCT", "1.0"))
    atr_mult = float(os.environ.get("LONGXIA_MAIN_BTC_ATR_MULT", "1.5"))
    atrp = _atr_pct_proxy(closes, period=14)
    thr = max(pct_floor, atr_mult * atrp) if atrp > 0 else pct_floor

    recent_high = max(highs[-lb:])
    recent_low = min(lows[-lb:])
    px = closes[-1]
    rh = max(recent_high, 1e-12)
    rl = max(recent_low, 1e-12)
    drop = (recent_high - px) / rh * 100.0
    bounce = (px - recent_low) / rl * 100.0
    out["drop_from_high_pct"] = round(drop, 4)
    out["bounce_from_low_pct"] = round(bounce, 4)

    if drop >= thr:
        out["active"] = True
        out["risk_off_long"] = True
        out["reason"] = f"BTC 近{lb}根高点回撤 {drop:.2f}% ≥ max({pct_floor}%, {atr_mult}×ATR%)"
    elif bounce >= thr:
        out["active"] = True
        out["risk_off_short"] = True
        out["reason"] = f"BTC 近{lb}根低点反抽 {bounce:.2f}% ≥ max({pct_floor}%, {atr_mult}×ATR%)"
    return out


def ema_chase_state(closes: List[float], sig_label: str) -> Dict[str, Any]:
    """高位追多 / 低位追空：相对 EMA21 偏离过大则标记 block（默认关）。"""
    out: Dict[str, Any] = {"block": False, "reason": ""}
    if not _env_on("LONGXIA_MAIN_EMA_CHASE_GUARD", "0"):
        return out
    if len(closes) < 65:
        return out
    max_pct = float(os.environ.get("LONGXIA_MAIN_EMA_CHASE_MAX_PCT", "0.45"))
    s = pd.Series(closes, dtype=float)
    e21 = float(ema(s, 21).iloc[-1])
    px = float(closes[-1])
    if e21 <= 0:
        return out
    dev_pct = abs(px - e21) / e21 * 100.0
    if sig_label.startswith("偏多") and px > e21 * (1.0 + max_pct / 100.0):
        out["block"] = True
        out["reason"] = f"价高于 EMA21 偏离 {dev_pct:.2f}%（上限 {max_pct}%）"
    elif sig_label.startswith("偏空") and px < e21 * (1.0 - max_pct / 100.0):
        out["block"] = True
        out["reason"] = f"价低于 EMA21 偏离 {dev_pct:.2f}%（上限 {max_pct}%）"
    return out


def apply_signal_guards(
    sig_label: str,
    *,
    klines: List[Dict[str, Any]],
    t1h: str,
    t4h: str,
    closes: List[float],
    btc_klines: Optional[List[Dict[str, Any]]],
) -> Tuple[str, Dict[str, Any]]:
    """
    顺序：回调 → EMA 追价 → BTC 锚定；仅降级标签，不引入新「开仓」类型。
    """
    sig = sig_label
    pb = main_pullback_state(klines, t1h, t4h)
    btc: Dict[str, Any] = btc_anchor_state(btc_klines) if btc_klines else {}

    if pb.get("active"):
        d = str(pb.get("direction") or "")
        if sig.startswith("偏多") and d == "down_pullback":
            if bool(pb.get("deep")):
                sig = "无"
            elif sig.startswith("偏多（强）"):
                sig = "偏多（轻）"
        elif sig.startswith("偏空") and d == "up_pullback":
            if bool(pb.get("deep")):
                sig = "无"
            elif sig.startswith("偏空（强）"):
                sig = "偏空（轻）"

    ec = ema_chase_state(closes, sig)
    if ec.get("block"):
        if sig.startswith("偏多（强）"):
            sig = "偏多（轻）"
        elif sig.startswith("偏空（强）"):
            sig = "偏空（轻）"
        elif sig.startswith("偏多（轻）"):
            sig = "无"
        elif sig.startswith("偏空（轻）"):
            sig = "无"

    if btc.get("risk_off_long") and sig.startswith("偏多"):
        sig = "无"
    if btc.get("risk_off_short") and sig.startswith("偏空"):
        sig = "无"

    extra = {
        "main_pullback_active": bool(pb.get("active")),
        "main_pullback_deep": bool(pb.get("deep")),
        "main_pullback_direction": str(pb.get("direction") or "none"),
        "main_pullback_reason": str(pb.get("reason") or ""),
        "main_ema_chase_block": bool(ec.get("block")),
        "main_ema_chase_reason": str(ec.get("reason") or ""),
        "main_btc_anchor_active": bool(btc.get("active")),
        "main_btc_risk_off_long": bool(btc.get("risk_off_long")),
        "main_btc_risk_off_short": bool(btc.get("risk_off_short")),
        "main_btc_drop_from_high_pct": btc.get("drop_from_high_pct"),
        "main_btc_bounce_from_low_pct": btc.get("bounce_from_low_pct"),
        "main_btc_anchor_reason": str(btc.get("reason") or ""),
    }
    return sig, extra


# --- 虚拟单：同向 SL 后冷却（logs 下 JSON）---

def _cooldown_path(repo_root: Path) -> Path:
    d = repo_root / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "main_virtual_sl_cooldown.json"


def _load_cooldown(repo_root: Path) -> Dict[str, Any]:
    p = _cooldown_path(repo_root)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_cooldown(repo_root: Path, data: Dict[str, Any]) -> None:
    _cooldown_path(repo_root).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def register_virtual_sl_cooldown(repo_root: Path, symbol: str, direction: str) -> None:
    """主观察池虚拟单触发 SL 后，同向冷却一段时间（仅当开关开启）。"""
    if not _env_on("LONGXIA_MAIN_VIRTUAL_SL_COOLDOWN_GUARD", "0"):
        return
    sec = int(os.environ.get("LONGXIA_MAIN_VIRTUAL_SL_COOLDOWN_SEC", "2700"))
    if sec <= 0:
        return
    sym = str(symbol or "").strip()
    if not sym:
        return
    d = str(direction or "")
    key = "long_until" if "多" in d else ("short_until" if "空" in d else "")
    if not key:
        return
    st = _load_cooldown(repo_root)
    cur = st.get(sym) if isinstance(st.get(sym), dict) else {}
    cur = dict(cur)
    cur[key] = time.time() + float(sec)
    st[sym] = cur
    _save_cooldown(repo_root, st)


def virtual_open_blocked(repo_root: Path, symbol: str, direction: str) -> bool:
    """是否因同向 SL 冷却而暂不开新虚拟单。"""
    if not _env_on("LONGXIA_MAIN_VIRTUAL_SL_COOLDOWN_GUARD", "0"):
        return False
    sym = str(symbol or "").strip()
    if not sym:
        return False
    d = str(direction or "")
    key = "long_until" if d == "做多" else ("short_until" if d == "做空" else "")
    if not key:
        return False
    st = _load_cooldown(repo_root).get(sym)
    if not isinstance(st, dict):
        return False
    until = _f(st.get(key), 0.0)
    return time.time() < until
