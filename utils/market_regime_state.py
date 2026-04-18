# -*- coding: utf-8 -*-
"""
轻量 Markov 行情状态：记录 chop/mid/trend 转移计数，输出下一状态经验分布。
状态文件：logs/market_regime_state.json（与 experiment_risk 类似，勿提交密钥）
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

_STATES = ("chop", "mid", "trend")


def _default_state() -> Dict[str, Any]:
    return {
        "last_regime": "",
        "transitions": {a: {b: 0 for b in _STATES} for a in _STATES},
        "steps": 0,
    }


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return _default_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _default_state()
        out = _default_state()
        out["last_regime"] = str(raw.get("last_regime") or "")
        tr = raw.get("transitions")
        if isinstance(tr, dict):
            for a in _STATES:
                row = tr.get(a)
                if isinstance(row, dict):
                    for b in _STATES:
                        try:
                            out["transitions"][a][b] = int(row.get(b) or 0)
                        except Exception:
                            pass
        try:
            out["steps"] = int(raw.get("steps") or 0)
        except Exception:
            pass
        return out
    except Exception:
        return _default_state()


def _save(path: Path, st: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def _next_prob_from_row(st: Dict[str, Any], current: str) -> Dict[str, float]:
    current = current if current in _STATES else "mid"
    row = st["transitions"].get(current) or {b: 0 for b in _STATES}
    tot = sum(max(0, int(row.get(b) or 0)) for b in _STATES)
    if tot <= 0:
        return {s: round(1.0 / 3.0, 4) for s in _STATES}
    return {
        s: round(max(0, int(row.get(s) or 0)) / tot, 4) for s in _STATES
    }


def update_and_summarize_regime(
    repo_root: Path,
    current_regime: str,
    *,
    state_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    记录一次状态转移并返回当前状态 + 下一状态经验概率（基于「从当前态出发」的历史计数）。
    current_regime: chop | mid | trend（与 experiment_kronos_regime 一致）
    """
    cur = str(current_regime or "").strip().lower()
    if cur not in _STATES:
        cur = "mid"
    path = state_path or (repo_root / "logs" / "market_regime_state.json")
    st = _load(path)
    last = str(st.get("last_regime") or "")
    if last in _STATES:
        st["transitions"][last][cur] = int(st["transitions"][last].get(cur) or 0) + 1
        st["steps"] = int(st.get("steps") or 0) + 1
    st["last_regime"] = cur
    _save(path, st)

    npb = _next_prob_from_row(st, cur)
    line = (
        f"当前 {cur} ｜ 下一状态经验分布："
        f"chop {npb['chop']*100:.1f}% · mid {npb['mid']*100:.1f}% · trend {npb['trend']*100:.1f}% "
        f"（样本步数 {st['steps']}）"
    )
    try:
        state_file = str(path.relative_to(repo_root))
    except ValueError:
        state_file = str(path)
    return {
        "current": cur,
        "next_prob": npb,
        "transitions": st["transitions"],
        "steps": st["steps"],
        "state_file": state_file,
        "line": line,
    }


class RegimeMarkovTracker:
    """回测用：内存中累计转移，不写文件；与 update_and_summarize_regime 统计口径一致。"""

    def __init__(self) -> None:
        self._st = _default_state()

    def step(self, current_regime: str) -> Dict[str, Any]:
        cur = str(current_regime or "").strip().lower()
        if cur not in _STATES:
            cur = "mid"
        last = str(self._st.get("last_regime") or "")
        if last in _STATES:
            self._st["transitions"][last][cur] = int(self._st["transitions"][last].get(cur) or 0) + 1
            self._st["steps"] = int(self._st.get("steps") or 0) + 1
        self._st["last_regime"] = cur
        npb = _next_prob_from_row(self._st, cur)
        line = (
            f"[回测] 当前 {cur} ｜ 下一状态："
            f"chop {npb['chop']*100:.1f}% · mid {npb['mid']*100:.1f}% · trend {npb['trend']*100:.1f}% "
            f"（步数 {self._st['steps']}）"
        )
        return {
            "current": cur,
            "next_prob": npb,
            "transitions": self._st["transitions"],
            "steps": self._st["steps"],
            "line": line,
        }


def apply_markov_template_to_thresholds(
    *,
    regime: str,
    edge_base: float,
    edge_extra: float,
    need_edge: float,
    score_floor: float,
    next_prob: Dict[str, float],
    template: str,
) -> tuple[float, float]:
    """
    仅调整实验轨数值门槛；template=off 时返回原值。
    strict_chop：震荡概率占优时略收紧；趋势占优时略放宽。
    balanced：幅度减半。
    """
    t = str(template or "off").strip().lower()
    if t not in ("strict_chop", "balanced"):
        return need_edge, score_floor
    p_chop = float(next_prob.get("chop") or 0.0)
    p_mid = float(next_prob.get("mid") or 0.0)
    p_trend = float(next_prob.get("trend") or 0.0)
    mult = 1.0 if t == "strict_chop" else 0.5
    need_edge_f = float(need_edge)
    score_f = float(score_floor)
    if p_chop >= max(p_trend, p_mid) and p_chop >= (1.0 / 3.0):
        need_edge_f += mult * 1.5
        score_f += mult * 0.015
    elif p_trend >= max(p_chop, p_mid) and p_trend >= (1.0 / 3.0):
        need_edge_f = max(edge_base + edge_extra * 0.5, need_edge_f - mult * 1.0)
        score_f = max(0.65, score_f - mult * 0.01)
    return round(need_edge_f, 4), round(score_f, 4)
