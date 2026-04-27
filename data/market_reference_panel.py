from __future__ import annotations

import time
from typing import Any, Dict, Optional

import ccxt
import pandas as pd

_lock_cache: dict[str, dict[str, Any]] = {}
_TTL = 50.0


def _ex() -> Any:
    return ccxt.gateio({"enableRateLimit": True})


def _to_df(rows: list[list[Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _macd_hist(close: pd.Series) -> pd.Series:
    m = _ema(close, 12) - _ema(close, 26)
    sig = _ema(m, 9)
    return m - sig


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.where(d > 0, 0.0).rolling(n).mean()
    dn = (-d.where(d < 0, 0.0)).rolling(n).mean()
    rs = up / dn.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    up = h.diff()
    dn = -l.diff()
    plus_dm = up.where((up > dn) & (up > 0), 0.0)
    minus_dm = dn.where((dn > up) & (dn > 0), 0.0)
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean().replace(0, pd.NA)
    plus_di = 100 * (plus_dm.rolling(n).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(n).mean() / atr)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)) * 100
    return dx.rolling(n).mean()


def _trend(close: pd.Series) -> str:
    if len(close) < 25:
        return "—"
    e9 = _ema(close, 9).iloc[-1]
    e21 = _ema(close, 21).iloc[-1]
    slope = close.iloc[-1] - close.iloc[-6]
    if e9 > e21 and slope > 0:
        return "多头趋势"
    if e9 < e21 and slope < 0:
        return "空头趋势"
    return "震荡偏多" if e9 >= e21 else "震荡偏空"


def _shape_flags(df1h: pd.DataFrame, df4h: pd.DataFrame) -> dict[str, str]:
    out = {"shape_4h": "—", "shape_1h": "—"}
    if len(df4h) >= 4:
        c = df4h["close"].iloc[-4:]
        h = df4h["high"].iloc[-4:]
        if c.iloc[-1] < c.iloc[-2] < c.iloc[-3] and h.iloc[-1] <= h.max():
            out["shape_4h"] = "三推见顶雏形"
    if len(df1h) >= 7:
        h = df1h["high"].iloc[-7:]
        mid = h.iloc[3]
        if mid == h.max() and h.iloc[1] < mid and h.iloc[5] < mid:
            out["shape_1h"] = "简化头肩"
    return out


def get_market_reference(symbol: str, coinglass: Optional[dict] = None) -> Dict[str, Any]:
    k = f"{symbol}"
    hit = _lock_cache.get(k)
    now = time.time()
    if hit and now - hit.get("ts", 0) < _TTL:
        return hit["data"]

    ex = _ex()
    tf_rows = {}
    for tf, lim in (("5m", 220), ("15m", 220), ("1h", 260), ("4h", 260), ("1d", 220)):
        try:
            tf_rows[tf] = ex.fetch_ohlcv(symbol, timeframe=tf, limit=lim)
        except Exception:
            tf_rows[tf] = []

    d5 = _to_df(tf_rows.get("5m", []))
    d15 = _to_df(tf_rows.get("15m", []))
    d1h = _to_df(tf_rows.get("1h", []))
    d4h = _to_df(tf_rows.get("4h", []))
    d1d = _to_df(tf_rows.get("1d", []))

    def cyc(df: pd.DataFrame, name: str) -> Dict[str, Any]:
        if len(df) < 40:
            return {"trend": "—", "adx": None, "macd_strength": "—", "breakout_high": None}
        adx = _adx(df, 14).iloc[-1]
        hist = _macd_hist(df["close"])
        mh = "增强" if len(hist) >= 3 and hist.iloc[-1] > hist.iloc[-2] else "减弱"
        return {
            "trend": _trend(df["close"]),
            "adx": float(adx) if pd.notna(adx) else None,
            "macd_strength": mh,
            "breakout_high": float(df["high"].iloc[-40:].max()),
        }

    c1h = cyc(d1h, "1h")
    c4h = cyc(d4h, "4h")
    c1d = cyc(d1d, "1d")

    rsi5 = float(_rsi(d5["close"], 14).iloc[-1]) if len(d5) >= 20 and pd.notna(_rsi(d5["close"], 14).iloc[-1]) else None
    atr5 = float(_atr(d5, 14).iloc[-1]) if len(d5) >= 20 and pd.notna(_atr(d5, 14).iloc[-1]) else None

    bb_low = bb_mid = bb_up = None
    bb_touch = "—"
    if len(d15) >= 25:
        mid = d15["close"].rolling(20).mean()
        std = d15["close"].rolling(20).std()
        low = mid - 2 * std
        up = mid + 2 * std
        if pd.notna(low.iloc[-1]):
            bb_low = float(low.iloc[-1])
            bb_mid = float(mid.iloc[-1])
            bb_up = float(up.iloc[-1])
            px = float(d15["close"].iloc[-1])
            if px <= bb_low:
                bb_touch = "触下轨"
            elif px >= bb_up:
                bb_touch = "触上轨"
            else:
                bb_touch = "区间内"

    vol_avg10 = None
    vol_ratio = None
    if len(d5) >= 11:
        vol_avg10 = float(d5["volume"].iloc[-11:-1].mean())
        cur = float(d5["volume"].iloc[-1])
        vol_ratio = (cur / vol_avg10) if vol_avg10 and vol_avg10 > 0 else None

    shape = _shape_flags(d1h, d4h)

    gl = (coinglass or {}).get("global_long_percent") if isinstance(coinglass, dict) else None
    gs = (coinglass or {}).get("global_short_percent") if isinstance(coinglass, dict) else None

    out = {
        "cycle_1h": c1h,
        "cycle_4h": c4h,
        "cycle_1d": c1d,
        "rsi_5m": rsi5,
        "atr_5m": atr5,
        "bb_15m": {"low": bb_low, "mid": bb_mid, "up": bb_up, "touch": bb_touch},
        "vol_5m_avg10": vol_avg10,
        "vol_5m_ratio": vol_ratio,
        "shape_4h": shape.get("shape_4h"),
        "shape_1h": shape.get("shape_1h"),
        "long_short_global": {"long": gl, "short": gs},
        "liq_large_points": "暂缺（当前源无公开热力点位端点）",
    }
    _lock_cache[k] = {"ts": now, "data": out}
    return out
