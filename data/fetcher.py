"""数据获取模块：恐惧贪婪等仍走 data_feed；K 线快照走 Gate CCXT 现货（按 symbol）。"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta

import ccxt

from data_feed import get_all_data, latest_data

_gate_spot: Any = None


def _gate_spot_ex() -> Any:
    global _gate_spot
    if _gate_spot is None:
        _gate_spot = ccxt.gateio({"enableRateLimit": True})
    return _gate_spot

def get_current_price() -> float:  # 明确返回值类型
    """获取当前BTC价格
    返回：float - BTC价格（兜底值73000.0）
    """
    try:
        data = get_all_data()
        price = data.get("btc_price", 0)
        return price if price > 0 else latest_data.get("btc_price", 73000.0) or 73000.0
    except Exception as e:
        print(f"获取价格失败：{e}")
        return 73000.0

def get_fear_greed() -> int:  # 明确返回值类型
    """获取恐惧贪婪指数
    返回：int - 0-100的整数（兜底值50）
    """
    try:
        return latest_data.get("fear_greed", 50)
    except Exception as e:
        print(f"获取恐惧贪婪指数失败：{e}")
        return 50


def _synthetic_snapshot(symbol: str, limit: int) -> Dict[str, Any]:
    """CCXT 不可用时的兜底（仍仅适合 BTC 量级演示）。"""
    px = float(get_current_price())
    now = datetime.now(timezone.utc)
    n = max(30, int(limit or 500))
    klines: List[Dict[str, Any]] = []
    for i in range(n):
        t = now - timedelta(minutes=(n - i))
        ts = int(t.timestamp() * 1000)
        drift = ((i % 7) - 3) * 0.5
        p = max(1.0, px + drift)
        klines.append(
            {
                "time": ts,
                "open": p,
                "high": p * 1.0005,
                "low": p * 0.9995,
                "close": p,
                "volume": 100.0 + (i % 10),
            }
        )
    return {
        "symbol": symbol,
        "last_close": klines[-1]["close"],
        "klines": klines,
        "count": len(klines),
        "source": "synthetic_fallback_btc_drift",
    }


def build_indicator_snapshot(
    symbol: str = "BTC/USDT", limit: int = 500, force_refresh: bool = False
) -> Dict[str, Any]:
    """Gate.io 现货 1m OHLCV（按 symbol），供决策页与指标计算使用。"""
    sym = (symbol or "BTC/USDT").strip() or "BTC/USDT"
    n = max(30, min(int(limit or 500), 1000))
    try:
        raw = _gate_spot_ex().fetch_ohlcv(sym, timeframe="1m", limit=n)
        klines: List[Dict[str, Any]] = []
        for row in raw:
            klines.append(
                {
                    "time": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]) if len(row) > 5 else 0.0,
                }
            )
        last_close = float(klines[-1]["close"]) if klines else 0.0
        return {
            "symbol": sym,
            "last_close": last_close,
            "klines": klines,
            "count": len(klines),
            "source": "gateio_ccxt_v316",
        }
    except Exception as e:
        print(f"[data.fetcher] build_indicator_snapshot ccxt failed: {e!r}")
        return _synthetic_snapshot(sym, n)
