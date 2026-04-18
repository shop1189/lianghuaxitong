from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import ccxt

from data.fetcher import build_indicator_snapshot, get_current_price

_gate: Any = None


def _gate_ex() -> Any:
    global _gate
    if _gate is None:
        _gate = ccxt.gateio({"enableRateLimit": True})
    return _gate


def log_v317_engine_ready() -> None:
    print("[v317] proxy data_fetcher ready (data layer V3.17.0)")


def log_v316_engine_ready() -> None:
    """兼容旧名：与 log_v317_engine_ready 相同。"""
    log_v317_engine_ready()


async def fetch_current_ticker_price(symbol: str = "SOL/USDT") -> float:
    sym = (symbol or "SOL/USDT").strip() or "SOL/USDT"

    def _run() -> float:
        try:
            t = _gate_ex().fetch_ticker(sym)
            v = t.get("last") or t.get("close") or 0.0
            return float(v)
        except Exception:
            return float(get_current_price())

    return await asyncio.to_thread(_run)


def _fetch_current_ticker_price_sync(symbol: str = "SOL/USDT") -> float:
    sym = (symbol or "SOL/USDT").strip() or "SOL/USDT"
    try:
        t = _gate_ex().fetch_ticker(sym)
        v = t.get("last") or t.get("close") or 0.0
        return float(v)
    except Exception:
        return float(get_current_price())


def fetch_ticker(symbol: str) -> Dict[str, Any]:
    """供决策页展示 Gate 现货 ticker 原始字段（含时间戳等）。"""
    sym = (symbol or "SOL/USDT").strip() or "SOL/USDT"
    return _gate_ex().fetch_ticker(sym)


def fetch_ohlcv(symbol: str, timeframe: str = "1m", limit: int = 200) -> List[List[Any]]:
    # 使用现有缓存快照拼接成 OHLCV 结构，兼容 live_trading 的调用格式。
    snap = build_indicator_snapshot(symbol, max(50, int(limit or 200)))
    rows = []
    for k in (snap.get("klines") or [])[-int(limit or 200):]:
        rows.append(
            [
                int(k.get("time") or 0),
                float(k.get("open") or 0.0),
                float(k.get("high") or 0.0),
                float(k.get("low") or 0.0),
                float(k.get("close") or 0.0),
                float(k.get("volume") or 0.0),
            ]
        )
    return rows

