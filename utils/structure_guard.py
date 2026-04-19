# -*- coding: utf-8 -*-
"""
结构风控：反转 / 深回调识别、追单拦截、提前离场建议（仅函数层，不单独写盘）。

启用：默认开启；环境变量 LONGXIA_STRUCTURE_GUARD=0/false/off 可关闭（主观察池虚拟单已接入 live_trading）。
实验轨略敏、主观察池略钝：experiment_track=False 时提高概率阈值（更难触发拦截/离场）。

上层调用：trade/records.structure_early_exit_hint / structure_entry_blocked；
实盘接入请在持仓循环中传入 get_v313_decision_snapshot 风格快照，并自行合并开关。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any, Dict, Optional, Tuple


def _guard_enabled() -> bool:
    """默认开启；显式 LONGXIA_STRUCTURE_GUARD=0/false/no/off 时关闭。"""
    v = os.environ.get("LONGXIA_STRUCTURE_GUARD", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


@dataclass
class StructureGuardParams:
    """可调阈值；未传时使用代码默认，可被环境变量覆盖（LONGXIA_STRUCTURE_*）。"""

    entry_opp_prob_edge: float = 11.0  # 强反转：概率领先幅度（百分点）
    soft_prob_edge: float = 6.5  # 软条件：概率领先
    edge_lite: float = 0.0  # 0 表示用 max(2, entry_opp_prob_edge - 2)
    rsi_extreme_high: float = 72.0  # 多单：超买 + 概率偏下 时辅助离场
    rsi_extreme_low: float = 28.0  # 空单对称
    soft_exit_loss_pct: float = 0.12  # 软离场：浮亏 ≤ -该值（百分比）
    soft_exit_profit_pct: float = 0.06  # 软离场：浮盈 ≥ 该值（百分比）
    main_pool_edge_relax: float = 2.0  # 非实验轨：概率阈值 + 该值（更钝）


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).strip())
    except ValueError:
        return default


def _default_params_from_env() -> StructureGuardParams:
    return StructureGuardParams(
        entry_opp_prob_edge=_float_env("LONGXIA_STRUCTURE_EDGE_STRONG", 11.0),
        soft_prob_edge=_float_env("LONGXIA_STRUCTURE_EDGE_SOFT", 6.5),
        edge_lite=_float_env("LONGXIA_STRUCTURE_EDGE_LITE", 0.0),
        rsi_extreme_high=_float_env("LONGXIA_STRUCTURE_RSI_HIGH", 72.0),
        rsi_extreme_low=_float_env("LONGXIA_STRUCTURE_RSI_LOW", 28.0),
        soft_exit_loss_pct=_float_env("LONGXIA_STRUCTURE_SOFT_LOSS_PCT", 0.12),
        soft_exit_profit_pct=_float_env("LONGXIA_STRUCTURE_SOFT_PROFIT_PCT", 0.06),
        main_pool_edge_relax=_float_env("LONGXIA_STRUCTURE_MAIN_RELAX", 2.0),
    )


def _resolve_params(
    guard_params: Optional[StructureGuardParams],
    *,
    experiment_track: bool,
) -> StructureGuardParams:
    base = _default_params_from_env() if guard_params is None else guard_params
    p = replace(base)
    if not experiment_track:
        p = replace(
            p,
            entry_opp_prob_edge=p.entry_opp_prob_edge + p.main_pool_edge_relax,
            soft_prob_edge=p.soft_prob_edge + p.main_pool_edge_relax * 0.5,
        )
    return p


def _signal_label(km: Dict[str, Any]) -> str:
    return str(km.get("signal_label") or "").strip()


def _last_sig(km: Dict[str, Any]) -> int:
    st = km.get("live_trading_state")
    if not isinstance(st, dict):
        return 0
    try:
        return int(st.get("last_sig", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _probs(km: Dict[str, Any]) -> Tuple[float, float]:
    try:
        pu = float(km.get("prob_up_5m") if km.get("prob_up_5m") is not None else km.get("prob_up") or 50.0)
    except (TypeError, ValueError):
        pu = 50.0
    try:
        pd = float(km.get("prob_down_5m") if km.get("prob_down_5m") is not None else km.get("prob_down") or 50.0)
    except (TypeError, ValueError):
        pd = 50.0
    return pu, pd


def _rsi(km: Dict[str, Any]) -> Optional[float]:
    try:
        r = km.get("rsi_1m")
        if r is None:
            return None
        return float(r)
    except (TypeError, ValueError):
        return None


def _edge_lite_value(p: StructureGuardParams) -> float:
    if p.edge_lite > 0:
        return p.edge_lite
    return max(2.0, p.entry_opp_prob_edge - 2.0)


def _is_neutral_signal(sig: str) -> bool:
    if not sig or sig == "无":
        return True
    if "观望" in sig:
        return True
    if "无明确" in sig:
        return True
    return False


def early_exit_recommendation(
    open_side_cn: str,
    decision_snapshot: Dict[str, Any],
    unrealized_pnl_pct: Optional[float],
    guard_params: Optional[StructureGuardParams] = None,
    *,
    experiment_track: bool = True,
) -> Tuple[bool, str]:
    """
    返回 (是否建议立即平仓, 原因码)。
    原因码前缀 structure_exit: 便于 close_reason 统计。
    """
    if not _guard_enabled():
        return False, "hold"

    p = _resolve_params(guard_params, experiment_track=experiment_track)
    sig = _signal_label(decision_snapshot)
    ls = _last_sig(decision_snapshot)
    pu, pd = _probs(decision_snapshot)
    rsi = _rsi(decision_snapshot)
    edge = p.entry_opp_prob_edge
    soft_e = p.soft_prob_edge

    side = str(open_side_cn or "").strip()
    if side == "做多":
        # 强反转
        if ls <= -1:
            return True, "structure_exit:exit:long:strong_last_sig_bearish"
        if sig.startswith("偏空（强）"):
            return True, "structure_exit:exit:long:strong_short_label"
        if (pd - pu) >= edge:
            return True, "structure_exit:exit:long:strong_prob_down"

        # RSI 超买且概率已偏下
        if (
            rsi is not None
            and rsi >= p.rsi_extreme_high
            and pd > pu
        ):
            return True, "structure_exit:exit:long:rsi_high_prob_down"

        # 软：中性类标签 + 反向概率抬头 + 浮盈/浮亏达阈值
        if unrealized_pnl_pct is not None and _is_neutral_signal(sig):
            try:
                upnl = float(unrealized_pnl_pct)
            except (TypeError, ValueError):
                upnl = 0.0
            if (pd - pu) >= soft_e and (
                upnl <= -p.soft_exit_loss_pct or upnl >= p.soft_exit_profit_pct
            ):
                return True, "structure_exit:exit:long:soft_neutral_prob"

    elif side == "做空":
        if ls >= 1:
            return True, "structure_exit:exit:short:strong_last_sig_bullish"
        if sig.startswith("偏多（强）"):
            return True, "structure_exit:exit:short:strong_long_label"
        if (pu - pd) >= edge:
            return True, "structure_exit:exit:short:strong_prob_up"

        if (
            rsi is not None
            and rsi <= p.rsi_extreme_low
            and pu > pd
        ):
            return True, "structure_exit:exit:short:rsi_low_prob_up"

        if unrealized_pnl_pct is not None and _is_neutral_signal(sig):
            try:
                upnl = float(unrealized_pnl_pct)
            except (TypeError, ValueError):
                upnl = 0.0
            if (pu - pd) >= soft_e and (
                upnl <= -p.soft_exit_loss_pct or upnl >= p.soft_exit_profit_pct
            ):
                return True, "structure_exit:exit:short:soft_neutral_prob"

    return False, "hold"


def block_trend_chase_entry(
    want_side_cn: str,
    decision_snapshot: Dict[str, Any],
    guard_params: Optional[StructureGuardParams] = None,
    *,
    experiment_track: bool = True,
) -> Tuple[bool, str]:
    """
    若 True，则不建议本根沿 want 方向追趋势开仓（盘面已倒向反向或概率已明显偏一边）。
    轻标签需配合概率边或 last_sig，避免误杀正常回调。
    """
    if not _guard_enabled():
        return False, ""

    p = _resolve_params(guard_params, experiment_track=experiment_track)
    sig = _signal_label(decision_snapshot)
    ls = _last_sig(decision_snapshot)
    pu, pd = _probs(decision_snapshot)
    edge = p.entry_opp_prob_edge
    el = _edge_lite_value(p)
    soft_e = p.soft_prob_edge

    want = str(want_side_cn or "").strip()

    if want == "做多":
        if sig.startswith("偏空（强）"):
            return True, "block:chase_long:strong_short_label"
        if ls < 0 and (pd - pu) >= el:
            return True, "block:chase_long:bearish_sig_and_prob"
        if (pd - pu) >= edge:
            return True, "block:chase_long:prob_down_leads"
        if sig.startswith("偏空（轻）") and (pd - pu) >= soft_e:
            return True, "block:chase_long:light_short_prob"

    elif want == "做空":
        if sig.startswith("偏多（强）"):
            return True, "block:chase_short:strong_long_label"
        if ls > 0 and (pu - pd) >= el:
            return True, "block:chase_short:bullish_sig_and_prob"
        if (pu - pd) >= edge:
            return True, "block:chase_short:prob_up_leads"
        if sig.startswith("偏多（轻）") and (pu - pd) >= soft_e:
            return True, "block:chase_short:light_long_prob"

    return False, ""
