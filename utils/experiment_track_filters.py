# -*- coding: utf-8 -*-
"""
规则实验轨（kronos_light 强化）：形态、MTF、ATR、轻量 regime（与 live_trading 快照字段对齐）。
"""
from __future__ import annotations

from typing import Any, Dict, List


def _tf_trend_word(closes: List[float], stride: int) -> str:
    if len(closes) < stride * 3:
        return "震荡"
    sampled = closes[::stride][-40:]
    if len(sampled) < 3:
        return "震荡"
    chg = (sampled[-1] - sampled[0]) / max(sampled[0], 1e-12) * 100
    if chg > 0.04:
        return "上涨"
    if chg < -0.04:
        return "下跌"
    return "震荡"


def atr_percent_proxy(klines: List[Dict[str, Any]], period: int = 14) -> float:
    """最近 `period` 根 K 的 TR 均值 / 现价，作波动率代理。"""
    if len(klines) < period + 1:
        return 0.15
    trs: List[float] = []
    for i in range(-period, 0):
        h = float(klines[i]["high"])
        l = float(klines[i]["low"])
        pc = float(klines[i - 1]["close"])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    atr = sum(trs) / len(trs)
    last_close = float(klines[-1]["close"])
    return atr / max(last_close, 1e-12)


def markov_regime(
    _t5: str,
    atr_pct: float,
    *,
    atr_chop_max: float,
    atr_trend_min: float,
) -> str:
    """轻量三态：按 ATR% 分 chop / mid / trend（保留 t5 参数便于日后接 Markov 转移）。"""
    if atr_pct < atr_chop_max:
        return "chop"
    if atr_pct > atr_trend_min:
        return "trend"
    return "mid"


def gate_deviation_ok(rsi_1m: float, sig_label: str, *, min_dev: float = 12.0) -> bool:
    """Gate：RSI 相对 50 的偏离（强多偏超卖侧、强空偏超买侧）。"""
    if sig_label.startswith("偏多"):
        return rsi_1m <= (50.0 - min_dev)
    if sig_label.startswith("偏空"):
        return rsi_1m >= (50.0 + min_dev)
    return False


def last_bar_wick_dominant(
    klines: List[Dict[str, Any]], *, wick_body_ratio: float = 0.6
) -> bool:
    """影线相对实体占优（模糊小实体不算「清晰裸 K」时可配合形态使用）。"""
    if not klines:
        return False
    k = klines[-1]
    o, h, l, c = float(k["open"]), float(k["high"]), float(k["low"]), float(k["close"])
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    wick = upper + lower
    if body < 1e-12:
        return wick > 0
    return (wick / body) >= wick_body_ratio


def has_engulfing_or_key_pattern(klines: List[Dict[str, Any]]) -> bool:
    """吞没 / 锤 / 流星 / 启明星 / 黄昏星 等（talib 可用时由 indicator_upgrade 识别）。"""
    try:
        from indicator_upgrade import detect_kline_pattern

        pats = detect_kline_pattern(klines)
        keys = ("吞没", "锤", "流星", "启明星", "黄昏星", "刺透", "乌云")
        for p in pats:
            if any(k in p for k in keys):
                return True
    except Exception:
        pass
    return False


def mtf_aligned(closes: List[float], sig_label: str) -> bool:
    """1×stride + 5×stride 趋势词：偏多与偏空均要求两档不与主方向相反。"""
    if not closes:
        return False
    t1 = _tf_trend_word(closes, 1)
    t5 = _tf_trend_word(closes, 5)
    if sig_label.startswith("偏多"):
        return (t1 != "下跌") and (t5 != "下跌")
    if sig_label.startswith("偏空"):
        return (t1 != "上涨") and (t5 != "上涨")
    return False
