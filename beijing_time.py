from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict

_BJ = ZoneInfo("Asia/Shanghai")


def utc_ms_to_bj_str(ms: Any) -> str:
    try:
        m = int(ms)
        if m <= 0:
            return "—"
        dt = datetime.fromtimestamp(m / 1000.0, tz=timezone.utc).astimezone(_BJ)
        return dt.strftime("%Y-%m-%d %H:%M:%S +08:00")
    except Exception:
        return "—"


def format_entry_time_only(record: Dict[str, Any]) -> str:
    v = record.get("entry_time") or record.get("time") or record.get("timestamp")
    if not v:
        return "--:--:--"
    s = str(v)
    if "T" in s:
        # 2026-04-16T15:00:00+08:00 -> 15:00:00
        return s.split("T", 1)[-1][:8]
    return s[:8] if len(s) >= 8 else s


def trade_memory_record_for_preview(record: Dict[str, Any]) -> Dict[str, Any]:
    # 兼容旧主页面调用，保持结构不变并原样回传。
    return dict(record or {})


def transform_value_for_display(v: Any) -> Any:
    # 兼容旧主页面调用，避免复杂类型导致 json dumps 失败。
    if isinstance(v, dict):
        return {str(k): transform_value_for_display(val) for k, val in v.items()}
    if isinstance(v, list):
        return [transform_value_for_display(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)

