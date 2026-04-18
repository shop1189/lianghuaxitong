import json
import time
import numpy as np
import pandas as pd

try:
    import talib
except Exception:
    talib = None

try:
    import pandas_ta as pta
except Exception:
    try:
        import pandas_ta_classic as pta
        print("✅ 使用 pandas_ta_classic 作为备选")
    except Exception:
        pta = None
        print("⚠️ 两个 pandas_ta 都无法导入")


from typing import Any, Dict, List, Tuple

# 指标配置
INDICATORS = {
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "bollinger_period": 20,
    "bollinger_dev": 2,
}

# ========== EMA ==========
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


# ========== RSI(14) ==========
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


# ========== MACD（快慢线 + 信号线 + 柱状） ==========
def macd(series: pd.Series):
    fast_ema = ema(series, INDICATORS["macd_fast"])
    slow_ema = ema(series, INDICATORS["macd_slow"])
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, INDICATORS["macd_signal"])
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


# ========== 布林带 ==========
def bollinger(series: pd.Series):
    period = INDICATORS["bollinger_period"]
    dev = INDICATORS["bollinger_dev"]
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + dev * std
    lower = middle - dev * std
    return upper, middle, lower


# ========== 支撑位 / 阻力位 ==========
def support_resistance(klines: List[Dict]):
    lows = [x["low"] for x in klines]
    highs = [x["high"] for x in klines]
    support = np.percentile(lows, 10)
    resistance = np.percentile(highs, 90)
    return round(support, 2), round(resistance, 2)


# ========== 成交量放量确认 ==========
def volume_analysis(klines: List[Dict]):
    if len(klines) < 20:
        return "⚪ 平量"
    volumes = [x["volume"] for x in klines[-20:]]
    avg_vol = np.mean(volumes[:-1])
    current = volumes[-1]
    if current > avg_vol * 1.3:
        return "🔴 放量"
    elif current < avg_vol * 0.7:
        return "🟢 缩量"
    return "⚪ 平量"


# ========== K线形态（完整版：单根 + 组合）【原有逻辑保留】==========
def detect_kline_pattern(klines: List[Dict]) -> List[str]:
    if len(klines) < 3:
        return []

    open_arr = np.array([x["open"] for x in klines], dtype=float)
    high_arr = np.array([x["high"] for x in klines], dtype=float)
    low_arr = np.array([x["low"] for x in klines], dtype=float)
    close_arr = np.array([x["close"] for x in klines], dtype=float)

    signals = []

    # 反转形态（talib可用时）
    if talib is not None:
        if talib.CDLHAMMER(open_arr, high_arr, low_arr, close_arr)[-1] != 0:
            signals.append("🔨 锤头线（底部反转）")
        if talib.CDLSHOOTINGSTAR(open_arr, high_arr, low_arr, close_arr)[-1] != 0:
            signals.append("🌠 流星线（顶部反转）")
        if talib.CDLENGULFING(open_arr, high_arr, low_arr, close_arr)[-1] > 0:
            signals.append("🔥 看涨吞没（强反转）")
        if talib.CDLENGULFING(open_arr, high_arr, low_arr, close_arr)[-1] < 0:
            signals.append("💥 看跌吞没（强反转）")
        if talib.CDLHARAMI(open_arr, high_arr, low_arr, close_arr)[-1] > 0:
            signals.append("📌 看涨孕线")
        if talib.CDLHARAMI(open_arr, high_arr, low_arr, close_arr)[-1] < 0:
            signals.append("📌 看跌孕线")
        if talib.CDLDARKCLOUDCOVER(open_arr, high_arr, low_arr, close_arr)[-1] != 0:
            signals.append("☁️ 乌云盖顶（见顶）")
        if talib.CDLPIERCING(open_arr, high_arr, low_arr, close_arr)[-1] != 0:
            signals.append("☀️ 刺透形态（见底）")
        if talib.CDLMORNINGSTAR(open_arr, high_arr, low_arr, close_arr)[-1] != 0:
            signals.append("⭐ 启明星（大底）")
        if talib.CDLEVENINGSTAR(open_arr, high_arr, low_arr, close_arr)[-1] != 0:
            signals.append("🌙 黄昏星（大顶）")
        if talib.CDL3WHITESOLDIERS(open_arr, high_arr, low_arr, close_arr)[-1] != 0:
            signals.append("⚔️ 三白兵（强势上涨）")
        if talib.CDL3BLACKCROWS(open_arr, high_arr, low_arr, close_arr)[-1] != 0:
            signals.append("⚫ 三只乌鸦（强势下跌）")
        if talib.CDLDOJI(open_arr, high_arr, low_arr, close_arr)[-1] != 0:
            signals.append("✧ 十字星（变盘预警）")

    # 三连组合
    close_vals = [x["close"] for x in klines]
    if len(close_vals) >= 3:
        if close_vals[-1] > close_vals[-2] > close_vals[-3]:
            signals.append("📈 三连阳（趋势延续）")
        elif close_vals[-1] < close_vals[-2] < close_vals[-3]:
            signals.append("📉 三连阴（趋势延续）")
    # ========== 新增：经典组合形态 ==========
    # 上升/下降三法
    if talib is not None:
        if talib.CDLRISEFALL3METHODS(open_arr, high_arr, low_arr, close_arr)[-1] > 0:
            signals.append("📶 上升三法（趋势延续）")
        if talib.CDLRISEFALL3METHODS(open_arr, high_arr, low_arr, close_arr)[-1] < 0:
            signals.append("📉 下降三法（趋势延续）")
        # 分离线（看涨/看跌）
        if talib.CDLSEPARATINGLINES(open_arr, high_arr, low_arr, close_arr)[-1] > 0:
            signals.append("📶 看涨分离线（趋势延续）")
        if talib.CDLSEPARATINGLINES(open_arr, high_arr, low_arr, close_arr)[-1] < 0:
            signals.append("📉 看跌分离线（趋势延续）")
    # 顶/底分型（手动判断）
    if len(klines) >= 3:
        # 顶分型：中间K线最高，左右两边都低
        if high_arr[-2] > high_arr[-1] and high_arr[-2] > high_arr[-3]:
            if low_arr[-2] > low_arr[-1] and low_arr[-2] > low_arr[-3]:
                signals.append("🔺 顶分型（见顶预警）")
        # 底分型：中间K线最低，左右两边都高
        if low_arr[-2] < low_arr[-1] and low_arr[-2] < low_arr[-3]:
            if high_arr[-2] < high_arr[-1] and high_arr[-2] < high_arr[-3]:
                signals.append("🔻 底分型（见底预警）")

    return signals


# ---------------------------------------------------------------------------
# AdvancedIndicatorEngine：最近 300 根，缓存 45 秒
# ---------------------------------------------------------------------------
class AdvancedIndicatorEngine:
    _cache: Dict[str, Any] = {}
    _TTL = 45.0

    def __init__(self, max_bars: int = 300):
        self.max_bars = max_bars

    def _key(self, symbol: str, last_ts: int) -> str:
        return f"{symbol}|{last_ts}"

    def _df(self, klines: List[Dict]) -> pd.DataFrame:
        chunk = klines[-self.max_bars :] if len(klines) > self.max_bars else klines
        return pd.DataFrame(
            {
                "open": [float(x["open"]) for x in chunk],
                "high": [float(x["high"]) for x in chunk],
                "low": [float(x["low"]) for x in chunk],
                "close": [float(x["close"]) for x in chunk],
                "volume": [float(x.get("volume", 0) or 0) for x in chunk],
            }
        )

    def _supertrend_pro(self, df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> Tuple[str, float]:
        """Super Trend Pro：优先 pandas_ta；否则 ATR 通道近似。"""
        if len(df) < period + 2:
            return "数据不足", 0.0
        h, l, c = df["high"], df["low"], df["close"]
        if pta is not None:
            try:
                st = pta.supertrend(h, l, c, length=period, multiplier=mult)
                if st is not None and not st.empty:
                    col_dir = [x for x in st.columns if x.startswith("SUPERTd")]
                    col_line = [x for x in st.columns if x.startswith("SUPERT_")]
                    if col_dir and col_line:
                        d = float(st[col_dir[0]].iloc[-1])
                        v = float(st[col_line[0]].iloc[-1])
                        if d > 0:
                            return "多头", v
                        if d < 0:
                            return "空头", v
                        return "中性", v
            except Exception:
                pass
        hi = h.values
        lo = l.values
        cl = c.values
        if talib is None:
            return "ATR不可用", 0.0
        atr = talib.ATR(hi, lo, cl, timeperiod=period)
        hl2 = (h + l) / 2.0
        upper = hl2 + mult * pd.Series(atr)
        lower = hl2 - mult * pd.Series(atr)
        i = len(df) - 1
        if cl[i] > upper.iloc[i]:
            return "多头", float(lower.iloc[i])
        if cl[i] < lower.iloc[i]:
            return "空头", float(upper.iloc[i])
        return "中性", float(hl2.iloc[i])

    def _ema_triple_cross(self, df: pd.DataFrame) -> str:
        c = df["close"]
        if len(df) < 60:
            return "数据不足"
        e9 = ema(c, 9)
        e21 = ema(c, 21)
        e55 = ema(c, 55)
        a, b, d = e9.iloc[-1], e21.iloc[-1], e55.iloc[-1]
        if a > b > d:
            return "三均线多头排列"
        if a < b < d:
            return "三均线空头排列"
        if e9.iloc[-2] <= e21.iloc[-2] and a > b:
            return "短期金叉"
        if e9.iloc[-2] >= e21.iloc[-2] and a < b:
            return "短期死叉"
        return "三均线缠绕"

    def _sar_breaks(self, df: pd.DataFrame, acc: float = 0.02, max_acc: float = 0.2) -> str:
        if talib is None or len(df) < 5:
            return "SAR不可用"
        sar = talib.SAR(df["high"].values, df["low"].values, acceleration=acc, maximum=max_acc)
        c = df["close"].values
        if c[-1] > sar[-1] and c[-2] <= sar[-2]:
            return "SAR上破（偏多）"
        if c[-1] < sar[-1] and c[-2] >= sar[-2]:
            return "SAR下破（偏空）"
        return "SAR未破位"

    def _squeeze_momentum(self, df: pd.DataFrame) -> str:
        if pta is None or len(df) < 30:
            return "挤压动量：数据不足或未安装pandas_ta"
        try:
            sq = pta.squeeze(df["high"], df["low"], df["close"])
            if sq is None or sq.empty:
                return "挤压动量：—"
            last = sq.iloc[-1]
            for col in sq.columns:
                if "MOM" in col.upper() or "SQZ" in col.upper():
                    v = last.get(col, np.nan)
                    if pd.notna(v):
                        if float(v) > 0:
                            return "挤压释放：动量向上"
                        if float(v) < 0:
                            return "挤压释放：动量向下"
            return "挤压：收缩中"
        except Exception:
            return "挤压动量：计算跳过"

    def _macd_summary(self, df: pd.DataFrame) -> str:
        if len(df) < 40:
            return "MACD：数据不足"
        m, s, h = macd(df["close"])
        if h.iloc[-1] > 0 and h.iloc[-2] <= 0:
            return "MACD柱翻多"
        if h.iloc[-1] < 0 and h.iloc[-2] >= 0:
            return "MACD柱翻空"
        if m.iloc[-1] > s.iloc[-1]:
            return "MACD线在信号线上方"
        return "MACD线在信号线下方"

    def _order_blocks(self, df: pd.DataFrame, lookback: int = 40) -> str:
        if len(df) < lookback + 2:
            return "订单块：数据不足"
        sl = df.iloc[-lookback:]
        idx = sl["low"].idxmin()
        i = sl.index.get_loc(idx)
        if isinstance(i, slice):
            i = i.start or 0
        if i + 1 < len(sl):
            row = sl.iloc[i + 1]
            if row["close"] > row["open"]:
                return "潜在看涨订单块（简化）"
        idx2 = sl["high"].idxmax()
        j = sl.index.get_loc(idx2)
        if isinstance(j, slice):
            j = j.start or 0
        if j + 1 < len(sl):
            row2 = sl.iloc[j + 1]
            if row2["close"] < row2["open"]:
                return "潜在看跌订单块（简化）"
        return "订单块：未显著"

    def _fib_bollinger(self, df: pd.DataFrame, period: int = 20) -> str:
        if len(df) < period + 2:
            return "斐波布林带：数据不足"
        mid = df["close"].rolling(period).mean()
        std = df["close"].rolling(period).std()
        u1 = mid + 1.618 * std
        l1 = mid - 1.618 * std
        c = df["close"].iloc[-1]
        if c >= u1.iloc[-1]:
            return "价格触及斐波布林上轨（1.618）"
        if c <= l1.iloc[-1]:
            return "价格触及斐波布林下轨（1.618）"
        return "斐波布林带：中轨附近"

    def _roc_momentum(self, df: pd.DataFrame, period: int = 10) -> str:
        """价格动量：ROC（Rate of Change），与 MACD 互补。"""
        if len(df) < period + 1:
            return "动量(ROC)：数据不足"
        c = df["close"].astype(float)
        if talib is not None:
            roc = talib.ROC(c.values, timeperiod=period)
            v = float(roc[-1]) if len(roc) and not np.isnan(roc[-1]) else 0.0
        else:
            a, b = float(c.iloc[-1]), float(c.iloc[-1 - period])
            v = (a / b - 1.0) * 100.0 if b else 0.0
        if v > 0.4:
            return f"动量(ROC{period})：偏多（{v:.2f}%）"
        if v < -0.4:
            return f"动量(ROC{period})：偏空（{v:.2f}%）"
        return f"动量(ROC{period})：中性（{v:.2f}%）"

    def _liquidation_proxy(self, df: pd.DataFrame) -> str:
        if len(df) < 30:
            return "爆仓分布：数据不足"
        v = df["volume"]
        rng = (df["high"] - df["low"]).replace(0, np.nan)
        z = (v.iloc[-1] - v.rolling(30).mean().iloc[-1]) / (v.rolling(30).std().iloc[-1] + 1e-9)
        wick = (df["high"] - np.maximum(df["open"], df["close"])) + (
            np.minimum(df["open"], df["close"]) - df["low"]
        )
        wr = (wick / rng).iloc[-1]
        if z > 2.0 and wr > 1.2:
            return "爆仓分布：放量长影线（模拟）"
        if z > 2.0:
            return "爆仓分布：成交量异常（模拟）"
        return "爆仓分布：正常"

    def compute(self, symbol: str, klines: List[Dict]) -> Dict[str, Any]:
        if not klines:
            return {}
        last_ts = int(klines[-1].get("time", 0) or 0)
        k = self._key(symbol, last_ts)
        now = time.time()
        hit = AdvancedIndicatorEngine._cache.get(k)
        if hit and now - hit.get("ts", 0) < self._TTL:
            return hit["data"]

        df = self._df(klines)
        st_dir, st_v = self._supertrend_pro(df, 10, 3.0)
        out = {
            "supertrend_pro": {"dir": st_dir, "value": st_v},
            "ema3_cross": self._ema_triple_cross(df),
            "sar_breaks": self._sar_breaks(df),
            "squeeze": self._squeeze_momentum(df),
            "macd": self._macd_summary(df),
            "momentum": self._roc_momentum(df, 10),
            "order_blocks": self._order_blocks(df),
            "fib_bollinger": self._fib_bollinger(df),
            "liquidation_proxy": self._liquidation_proxy(df),
        }
        AdvancedIndicatorEngine._cache[k] = {"ts": now, "data": out}
        return out
