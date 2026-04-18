"""共享行情快照：供 data/fetcher 合成指标与恐惧贪婪兜底。"""
from __future__ import annotations

from data_upgrade import get_fear_greed, get_price

latest_data: dict = {"btc_price": 0.0, "fear_greed": 50}


def get_all_data() -> dict:
    try:
        px = float(get_price() or 0.0)
    except Exception:
        px = 0.0
    try:
        fng = int(get_fear_greed())
    except Exception:
        fng = 50
    global latest_data
    latest_data = {"btc_price": px, "fear_greed": fng}
    return dict(latest_data)
