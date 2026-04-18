# -*- coding: utf-8 -*-
"""
规则实验轨风控：连亏暂停、单日累计亏损熔断、单向持仓、同向冷却（与 live_trading 协同）。
状态文件：logs/experiment_risk_state.json（目录已 .gitignore）
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo

_BJ = ZoneInfo("Asia/Shanghai")


def _state_path(repo_root: Path) -> Path:
    d = repo_root / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "experiment_risk_state.json"


def bj_today() -> str:
    return datetime.now(_BJ).strftime("%Y-%m-%d")


def _default_state() -> Dict[str, Any]:
    return {
        "bj_date": "",
        "pause_until_unix": 0.0,
        "consecutive_losses": 0,
        "day_pnl_pct": 0.0,
        "dir_pause_until": {},
    }


def load_state(repo_root: Path) -> Dict[str, Any]:
    p = _state_path(repo_root)
    if not p.exists():
        return _default_state()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            out = _default_state()
            out.update({k: raw[k] for k in out if k in raw})
            if "dir_pause_until" in raw and isinstance(raw["dir_pause_until"], dict):
                out["dir_pause_until"] = {
                    str(k): float(v) for k, v in raw["dir_pause_until"].items()
                }
            return out
    except Exception:
        pass
    return _default_state()


def save_state(repo_root: Path, st: Dict[str, Any]) -> None:
    p = _state_path(repo_root)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def _rollover(st: Dict[str, Any]) -> None:
    today = bj_today()
    if st.get("bj_date") != today:
        st["bj_date"] = today
        st["consecutive_losses"] = 0
        st["day_pnl_pct"] = 0.0


def register_close(
    repo_root: Path,
    profit_pct: float,
    *,
    direction: str,
    pause_sec: float,
    max_consecutive_before_pause: int = 2,
) -> None:
    """实验轨平仓后：更新连亏、暂停、日累计、同向冷却。"""
    st = load_state(repo_root)
    _rollover(st)
    st["day_pnl_pct"] = float(st.get("day_pnl_pct") or 0.0) + float(profit_pct)

    cooldown_sec = float(os.environ.get("LONGXIA_EXPERIMENT_SAME_DIR_COOLDOWN_SEC", "0") or 0.0)

    if profit_pct < 0:
        st["consecutive_losses"] = int(st.get("consecutive_losses") or 0) + 1
        if cooldown_sec > 0 and direction in ("做多", "做空"):
            dp = st.setdefault("dir_pause_until", {})
            assert isinstance(dp, dict)
            dp[direction] = time.time() + cooldown_sec
    else:
        st["consecutive_losses"] = 0

    if int(st.get("consecutive_losses") or 0) >= max(1, max_consecutive_before_pause):
        st["pause_until_unix"] = time.time() + max(0.0, pause_sec)
        st["consecutive_losses"] = 0

    save_state(repo_root, st)


def is_paused(repo_root: Path) -> bool:
    st = load_state(repo_root)
    _rollover(st)
    save_state(repo_root, st)
    return time.time() < float(st.get("pause_until_unix") or 0.0)


def day_loss_exceeded(repo_root: Path) -> bool:
    st = load_state(repo_root)
    _rollover(st)
    save_state(repo_root, st)
    limit = float(os.environ.get("LONGXIA_EXPERIMENT_DAY_STOP_PCT", "-1.0"))
    return float(st.get("day_pnl_pct") or 0.0) <= limit


def direction_in_cooldown(repo_root: Path, direction: str) -> bool:
    st = load_state(repo_root)
    _rollover(st)
    save_state(repo_root, st)
    dp = st.get("dir_pause_until") or {}
    if not isinstance(dp, dict):
        return False
    until = float(dp.get(direction) or 0.0)
    return time.time() < until


def direction_blocked_by_single_side(want: str) -> bool:
    """全账户实验仓：已存在反向未平仓则不再开。"""
    if want not in ("做多", "做空"):
        return True
    try:
        from evolution_core import ai_evo

        opp = "做空" if want == "做多" else "做多"
        for t in ai_evo.memory.open_trades:
            if str(t.get("direction") or "") == opp:
                return True
    except Exception:
        pass
    return False
