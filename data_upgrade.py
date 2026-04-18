import time
import requests
import numpy as np
import pandas as pd
from config_upgrade import API, TIMEFRAMES, CACHE
cache_memory = {}

def get_price():
    now = time.time()
    if "price" in cache_memory and now - cache_memory["price"]["time"] < CACHE["price_ttl"]:
        return cache_memory["price"]["data"]
    try:
        res = requests.get(API["binance_price"], params={"symbol": "BTCUSDT"}, timeout=3)
        price = float(res.json()["price"])
        cache_memory["price"] = {"data": price, "time": now}
        return price
    except:
        return cache_memory.get("price", {}).get("data", 0)

def get_klines(timeframe="1m", limit=50):
    now = time.time()
    key = f"kline_{timeframe}"
    if key in cache_memory and now - cache_memory[key]["time"] < CACHE["kline_ttl"]:
        return cache_memory[key]["data"]
    try:
        params = {"symbol": "BTCUSDT", "interval": timeframe, "limit": limit}
        res = requests.get(API["binance_klines"], params=params, timeout=5)
        data = res.json()
        klines = [
            {
                "open": float(d[1]),
                "high": float(d[2]),
                "low": float(d[3]),
                "close": float(d[4]),
                "volume": float(d[5]),
                "time": int(d[6])
            } for d in data
        ]
        cache_memory[key] = {"data": klines, "time": now}
        return klines
    except:
        return cache_memory.get(key, {}).get("data", [])

def get_fear_greed():
    now = time.time()
    key = "fng"
    if key in cache_memory and now - cache_memory[key]["time"] < CACHE["fear_greed_ttl"]:
        return cache_memory[key]["data"]
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        res = requests.get(url, timeout=5)
        fng = int(res.json()["data"][0]["value"])
        cache_memory[key] = {"data": fng, "time": now}
        return fng
    except:
        return cache_memory.get(key, {}).get("data", 50)
# ========== 新增：资金费率 Funding Rate ==========
def get_funding_rate(symbol="BTCUSDT"):
    now = time.time()
    key = "funding_rate"
    if key in cache_memory and now - cache_memory[key]["time"] < CACHE["funding_ttl"]:
        return cache_memory[key]["data"]
    try:
        res = requests.get(API["binance_funding"], params={"symbol": symbol, "limit": 1}, timeout=3)
        funding = float(res.json()[0]["fundingRate"])
        cache_memory[key] = {"data": funding, "time": now}
        return funding
    except:
        return cache_memory.get(key, {}).get("data", 0.0)

# ========== 新增：Taker 主动买卖比 ==========
def get_taker_ratio(symbol="BTCUSDT"):
    now = time.time()
    key = "taker_ratio"
    if key in cache_memory and now - cache_memory[key]["time"] < CACHE["taker_ttl"]:
        return cache_memory[key]["data"]
    try:
        res = requests.get(API["binance_taker"], params={"symbol": symbol, "period": "5m", "limit": 1}, timeout=3)
        data = res.json()[-1]
        buy_ratio = float(data["takerBuyRatio"])
        sell_ratio = float(data["takerSellRatio"])
        cache_memory[key] = {"data": (buy_ratio, sell_ratio), "time": now}
        return buy_ratio, sell_ratio
    except:
        return cache_memory.get(key, {}).get("data", (0.5, 0.5))

# ========== 新增：OI 持仓量 ==========
def get_open_interest(symbol="BTCUSDT"):
    now = time.time()
    key = "open_interest"
    if key in cache_memory and now - cache_memory[key]["time"] < CACHE["oi_ttl"]:
        return cache_memory[key]["data"]
    try:
        res = requests.get(API["binance_oi"], params={"symbol": symbol}, timeout=3)
        oi = float(res.json()["openInterest"])
        cache_memory[key] = {"data": oi, "time": now}
        return oi
    except:
        return cache_memory.get(key, {}).get("data", 0.0)

# ========== 新增：多空持仓比 ==========
def get_long_short_ratio(symbol="BTCUSDT"):
    now = time.time()
    key = "long_short_ratio"
    if key in cache_memory and now - cache_memory[key]["time"] < CACHE["ls_ttl"]:
        return cache_memory[key]["data"]
    try:
        res = requests.get(API["binance_ls_ratio"], params={"symbol": symbol, "period": "5m", "limit": 1}, timeout=3)
        ratio = float(res.json()[-1]["longAccountRatio"])
        cache_memory[key] = {"data": ratio, "time": now}
        return ratio
    except:
        return cache_memory.get(key, {}).get("data", 0.5)


def get_multi_tf_data(symbol="BTCUSDT", use_live=True, base_df=None):
    """
    Multi-timeframe data provider for strategy resonance.
    Returns dict with 5m/1h/1d OHLCV DataFrame.
    - use_live=True: fetch via get_klines
    - base_df: optional 5m DataFrame for backtest resampling (preferred in offline backtest)
    """
    if base_df is not None:
        df5 = base_df.copy()
        if not isinstance(df5.index, pd.DatetimeIndex):
            if "Date" in df5.columns:
                df5 = df5.set_index(pd.to_datetime(df5["Date"], utc=True))
            else:
                raise ValueError("base_df must have DatetimeIndex or Date column")
        df5 = df5[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        df1h = df5.resample("1h").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        ).dropna()
        df1d = df5.resample("1d").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        ).dropna()
        return {"5m": df5, "1h": df1h, "1d": df1d}

    if not use_live:
        raise ValueError("use_live=False requires base_df")

    def _to_df(tf, limit):
        rows = get_klines(timeframe=tf, limit=limit)
        if not rows:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        data = pd.DataFrame(
            {
                "Open": [float(x["open"]) for x in rows],
                "High": [float(x["high"]) for x in rows],
                "Low": [float(x["low"]) for x in rows],
                "Close": [float(x["close"]) for x in rows],
                "Volume": [float(x["volume"]) for x in rows],
                "Date": pd.to_datetime([int(x["time"]) for x in rows], unit="ms", utc=True),
            }
        ).set_index("Date")
        return data

    return {
        "5m": _to_df("5m", 1500),
        "1h": _to_df("1h", 2000),
        "1d": _to_df("1d", 1200),
    }
