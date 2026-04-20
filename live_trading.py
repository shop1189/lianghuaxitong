"""
实盘 / 决策快照：5m K 与决策页数据（数据层 V3.18.0 · Gate.io CCXT）。
V3.18.0：在 V3.17 基线上增加主观察池结构风控可开关、导航与备份脚本等；开仓规则内核仍以模块注释与 env 为准。
规则实验轨：sync_experiment_track_from_snapshot — 独立筛选 + 较宽 SL/TP，写入非 virtual_signal。

环境变量速查（规则实验轨 / Kronos-light 强化，重启进程生效）：
  LONGXIA_EXPERIMENT_TRACK     关：0|false|no|off；默认开启
  LONGXIA_EXPERIMENT_MODE      kronos_light（默认）| legacy | kronos_model（未接真模型时同 light）
  LONGXIA_KRONOS_MIN_PROB_EDGE     kronos_light：涨跌概率差阈值（百分点），默认 5（易恢复样本；可再收紧）
  LONGXIA_EXPERIMENT_TREND_EDGE     trend 态概率差上限（与 base+extra 取 min），默认 12
  LONGXIA_EXPERIMENT_MIN_SCORE_ABS   kronos_light：|consistency_score| 下限，默认 0.45
  LONGXIA_EXPERIMENT_EDGE_CHOP_EXTRA / LONGXIA_EXPERIMENT_EDGE_MID_EXTRA  chop/mid 态额外概率差，默认 3 / 0
  LONGXIA_EXPERIMENT_SCORE_CHOP_FLOOR / SCORE_MID_FLOOR  chop/mid 态与 MIN_SCORE 取 max，默认 0.68 / 0.45
  LONGXIA_EXPERIMENT_GATE_RSI_DEV    Gate：RSI 偏离 50 的幅度，默认 12
  LONGXIA_EXPERIMENT_ATR_MIN_PCT     波动过低不做（ATR%/价），默认 0.05
  LONGXIA_EXPERIMENT_TREND_ALLOW_NO_PATTERN  trend 态无裸 K 形态时仍可过（需 gate+mtf 已满足），默认开
  LONGXIA_EXPERIMENT_MID_ALLOW_NO_PATTERN  mid 态无裸 K 形态时仍可过（需 gate+mtf 已满足），默认开
  LONGXIA_EXPERIMENT_ATR_CHOP_MAX / ATR_TREND_MIN  轻量 regime 分档
  LONGXIA_EXPERIMENT_WICK_BODY_RATIO  裸K影线/实体比，默认 0.6
  LONGXIA_EXPERIMENT_PAUSE_SEC       连亏 2 笔后暂停秒数，默认 900
  LONGXIA_EXPERIMENT_DAY_STOP_PCT    单日实验累计盈亏% 熔断，默认 -1.0
  LONGXIA_EXPERIMENT_SAME_DIR_COOLDOWN_SEC  亏损后同向再入场冷却（秒），默认 0 关闭
  LONGXIA_EXPERIMENT_MIN_CONSISTENCY / LONGXIA_EXPERIMENT_MIN_BAYES  仅 legacy
  LONGXIA_EXPERIMENT_SL_PCT / TP1_PCT / TP2_PCT / TP3_PCT  实验轨止损止盈比例
  LONGXIA_EXPERIMENT_USE_FIB_LEVELS     实验轨用 0.618/1.618 斐波微调 SL/TP1（0 关 / 1 开），默认 0
  LONGXIA_EXPERIMENT_TP1_PARTIAL        实验轨：命中 TP1 后部分锁定+抬损至保本，再博 TP2/TP3（0 关 / 1 开，默认 1）
  LONGXIA_EXPERIMENT_PARTIAL_RATIO      上述「TP1 锁定」占名义比例，默认 0.5（剩余继续持仓）
  LONGXIA_EXPERIMENT_BE_BUFFER_PCT      保本止损相对 entry 的缓冲（小数，如 0.0002≈0.02%），默认 0.0002
  LONGXIA_EXPERIMENT_SCAN_INTERVAL_SEC  后台全币种扫描间隔（秒），下限约 15
  LONGXIA_MARKOV_TEMPLATE              Markov 阈值模板 off|strict_chop|balanced，默认 off（仅实验轨）
  LONGXIA_USE_MARKOV_THRESHOLD_TEMPLATE  策略层 Markov 状态模板（0/1），默认 0；为 1 时按 chop/mid/trend 加载 prob/consistency/频率
  LONGXIA_DYNAMIC_LEVELS               主观察池虚拟单/决策页：按近期波动微调 SL/TP（0 关，默认）
  LONGXIA_SCALED_EXIT                  主观察池虚拟单：分批止盈（SL 优先，再 TP1→TP2→TP3；0 关，默认）
  LONGXIA_SCALED_W1 / W2 / W3          分批占原始名义比例，默认 0.5 / 0.3 / 0.2（可和不为 1，会归一化）
  LONGXIA_MAIN_VIRTUAL_TP1_PARTIAL     主观察池：TP1 部分锁定+抬损至保本（与实验轨同思路；默认 1 开）；为 1 时新开仓不写 scaled_mode，与 LONGXIA_SCALED_EXIT 二选一
  LONGXIA_MAIN_VIRTUAL_PARTIAL_RATIO / LONGXIA_MAIN_VIRTUAL_BE_BUFFER_PCT  主池比例与保本缓冲（缺省同实验轨 env）
  LONGXIA_MAIN_PULLBACK_GUARD          主观察池：回调防追单（0 关，默认）
  LONGXIA_MAIN_BTC_ANCHOR_GUARD        BTC 锚定否决顺趋势信号（0 关，默认；开则多一次 BTC K 线拉取）
  LONGXIA_MAIN_EMA_CHASE_GUARD         相对 EMA21 追价过远时降级（0 关，默认）
  LONGXIA_MAIN_VIRTUAL_SL_COOLDOWN_GUARD  主观察池虚拟单同向 SL 后冷却（0 关，默认）
  LONGXIA_MAIN_VIRTUAL_SL_COOLDOWN_SEC  冷却秒数，默认 2700（45 分钟）
  LONGXIA_EXPERIMENT_CLASSIC_SCORE_BONUS  B 组经典规则对 score 的最大加分，默认 0.08（预留，未接逻辑时无影响）
  LONGXIA_MAIN_BREAKOUT_LOOKBACK_BARS   机械突破区间回看 K 线数（不含当前根），默认 48
  LONGXIA_MAIN_BREAKOUT_BUFFER_PCT      突破确认缓冲（百分比），默认 0.08
  LONGXIA_MAIN_FALSE_BREAK_REVERT_BARS  假突破回落观察窗口（根数），默认 6
  LONGXIA_MAIN_BREAKOUT_SIGNAL_FILTER   主观察池：机械触发对信号仅「强→轻」、不因未触发而清空（0 关 / 1 开，默认 1）
  LONGXIA_STRUCTURE_GUARD                结构风控（主观察池虚拟单）：追单拦截+提前平仓；默认 1；0/false 关闭
  LONGXIA_STRUCTURE_EDGE_STRONG / _SOFT / _LITE / _RSI_HIGH / _RSI_LOW / _SOFT_LOSS_PCT / _SOFT_PROFIT_PCT / _MAIN_RELAX  同上模块调参
  LONGXIA_TEACHER_BOOST_TRACK            带单老师·起号轨写入（0 关 / 1 开，默认 0；落库 signal_track=boost）
  LONGXIA_TEACHER_COMBAT_TRACK           带单老师·实操轨写入（0 关 / 1 开，默认 0；落库 signal_track=combat）
  （起号/实操参数表、每日笔数上限等后续接同一前缀，不影响主观察池/实验轨）
可选真 Kronos：integrations/kronos_experiment_optional.py（未接模型前勿依赖 kronos_model）。
"""
from __future__ import annotations
import html
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
import ccxt
import numpy as np
import pandas as pd
from beijing_time import trade_memory_record_for_preview, utc_ms_to_bj_str
from utils.dynamic_levels import widen_levels_from_closes
from utils.exit_feature_flags import (
    dynamic_levels_enabled,
    main_virtual_tp1_partial_enabled,
    scaled_exit_enabled,
)
from utils.main_virtual_tp1_partial import try_apply_main_virtual_tp1_partial
from utils.scaled_exit_rules import try_scaled_virtual_close
from utils.main_observation_guard import (
    apply_signal_guards,
    register_virtual_sl_cooldown,
    virtual_open_blocked,
)
from utils.trade_exit_rules import first_exit_tick, virtual_hit_profit_and_close_px
from data_fetcher import _fetch_current_ticker_price_sync
from data_fetcher import fetch_ohlcv as gate_fetch_ohlcv
from data.fetcher import build_indicator_snapshot
from indicator_upgrade import (
    AdvancedIndicatorEngine,
    detect_kline_pattern,
    rsi as rsi_series,
)
from utils.experiment_track_filters import (
    atr_percent_proxy,
    gate_deviation_ok,
    has_engulfing_or_key_pattern,
    last_bar_wick_dominant,
    markov_regime,
    mtf_aligned,
)
from utils.market_regime_state import (
    USE_MARKOV_THRESHOLD_TEMPLATE,
    RegimeMarkovTracker,
    apply_markov_template_to_thresholds,
    get_threshold_template,
    update_and_summarize_regime,
)

_MEMOS_PREVIEW_MAX = 30
_MEMOS_PREVIEW_TABLE_N = 30
_STATE_FILE = Path(__file__).resolve().parent / "live_trading_state.json"
_MEMOS_HOOK = Path(__file__).resolve().parent / "memos_v316_hook.json"
_THEORY_FILE = Path(__file__).resolve().parent / "trading_theory_library.json"
_BAYES_FILE = Path(__file__).resolve().parent / "bayes_beta_state.json"
_TRADE_MEMORY = Path(__file__).resolve().parent / "trade_memory.json"
_REPO_ROOT = Path(__file__).resolve().parent
_ADV_ENGINE = AdvancedIndicatorEngine(max_bars=300)
_VIRTUAL_BR_TO_REASON = {"sl": "SL", "tp1": "TP1", "tp2": "TP2", "tp3": "TP3"}


def _virtual_memos_max_catchup() -> int:
    """单次同步最多按「计数差」补开几条虚拟单；超出则只对齐 hook，避免同一秒内刷出数百条同价记录。"""
    try:
        v = int(os.environ.get("LONGXIA_VIRTUAL_MEMOS_MAX_CATCHUP", "10"))
    except ValueError:
        v = 10
    return max(1, min(v, 500))


def _use_markov_threshold_template_resolved(force: Optional[bool]) -> bool:
    """是否启用策略层 Markov 阈值模板：force 优先（回测），否则读环境，否则用代码默认。"""
    if force is not None:
        return bool(force)
    v = os.environ.get("LONGXIA_USE_MARKOV_THRESHOLD_TEMPLATE", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return bool(USE_MARKOV_THRESHOLD_TEMPLATE)


def _experiment_frequency_load() -> Dict[str, float]:
    """实验轨开仓节流：每标的最近开仓 Unix 时间（秒）。"""
    p = _REPO_ROOT / "logs" / "experiment_frequency_state.json"
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {str(k): float(v) for k, v in raw.items()}
    except Exception:
        return {}


def _experiment_frequency_save(d: Dict[str, float]) -> None:
    p = _REPO_ROOT / "logs" / "experiment_frequency_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _experiment_frequency_allow(symbol: str, min_interval_sec: float) -> bool:
    if min_interval_sec <= 0:
        return True
    sym = str(symbol or "").strip()
    if not sym:
        return True
    now = time.time()
    d = _experiment_frequency_load()
    last = float(d.get(sym, 0.0))
    return (now - last) >= float(min_interval_sec)


def _experiment_frequency_mark_entry(symbol: str) -> None:
    sym = str(symbol or "").strip()
    if not sym:
        return
    d = _experiment_frequency_load()
    d[sym] = time.time()
    _experiment_frequency_save(d)


def _trade_memory_parse(raw: Any) -> Tuple[List[dict], Optional[Dict[str, Any]]]:
    """兼容顶层数组或 {\"schema_version\",\"trades\":[]} 包一层。"""
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)], None
    if isinstance(raw, dict) and isinstance(raw.get("trades"), list):
        env = {k: v for k, v in raw.items() if k != "trades"}
        return [x for x in raw["trades"] if isinstance(x, dict)], env
    return [], None


def _trade_memory_write(trades: List[dict], env: Optional[Dict[str, Any]]) -> None:
    try:
        from utils.trade_memory_autobak import maybe_backup_trade_memory

        maybe_backup_trade_memory(_TRADE_MEMORY)
    except Exception:
        pass
    if env is not None:
        out: Dict[str, Any] = {**env, "trades": trades}
        _TRADE_MEMORY.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        _TRADE_MEMORY.write_text(json.dumps(trades, ensure_ascii=False, indent=2), encoding="utf-8")


_BJ = ZoneInfo("Asia/Shanghai")
_LAST_BETA_TS = 0.0
_EVOL_REPORT_PATCHED = False
_MAIN_PREVIEW_PATCHED = False
_GET_REPORT_PATCHED = False
_BG_SCAN_STARTED = False
_EXPERIMENT_SCAN_SYMBOLS = (
    "SOL/USDT",
    "BTC/USDT",
    "ETH/USDT",
    "DOGE/USDT",
    "XRP/USDT",
    "BNB/USDT",
)
def _json_dumps_safe(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)
def trade_memory_preview_rows_html(max_display: int = _MEMOS_PREVIEW_MAX) -> str:
    _ensure_memos_hotfixes()
    _reload_evolution_memory_from_disk()
    if not _TRADE_MEMORY.exists():
        return ""
    try:
        raw = json.loads(_TRADE_MEMORY.read_text(encoding="utf-8"))
    except Exception:
        return '<p class="muted">无法读取 trade_memory.json</p>'
    trades, _ = _trade_memory_parse(raw)
    n = _MEMOS_PREVIEW_TABLE_N
    tail = trades[-n:]
    rows = ""
    for i, r in enumerate(tail):
        disp = trade_memory_record_for_preview(r) if isinstance(r, dict) else r
        rows += f"<tr><td>{html.escape(str(i+1))}</td><td><pre>{html.escape(_json_dumps_safe(disp))}</pre></td></tr>"
    return (
        '<p class="muted" style="margin-top:12px"><b>近期 memos 原始样本（仅展示末尾最多 30 条，只读）</b></p>\n'
        f'<table class="data-table"><thead><tr><th>序号</th><th>记录内容</th></tr></thead><tbody>{rows}</tbody></table>\n'
    )
def _reload_evolution_memory_from_disk() -> None:
    try:
        from evolution_core import ai_evo
        ai_evo.memory.data = ai_evo.memory._load()
    except Exception:
        pass
def _virtual_hit_and_close(
    direction: str,
    price: float,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
) -> Optional[Tuple[float, float]]:
    """判定顺序同 ``utils.trade_exit_rules.first_exit_tick``（SL→TP3→TP2→TP1）；盈亏口径与 evolution_core 一致。"""
    return virtual_hit_profit_and_close_px(
        direction, price, entry, sl, tp1, tp2, tp3
    )
def _sync_virtual_closeouts_for_price(
    price: float,
    symbol: str,
    decision: Optional[Dict[str, Any]] = None,
) -> None:
    """仅撮合 **同一 symbol** 的未平仓虚拟单。禁止用 A 标的现价去判定 B 标的（否则盈亏/止损止盈会错乱）。

    decision：与 get_v313 一致的快照字段（signal_label / prob_* / rsi_1m / live_trading_state），
    供结构风控提前离场；未传则仅走硬 TP/SL，不触发结构离场。
    """
    if price <= 0:
        return
    sym_f = str(symbol or "").strip()
    if not sym_f:
        return
    if not _TRADE_MEMORY.exists():
        return
    try:
        raw = json.loads(_TRADE_MEMORY.read_text(encoding="utf-8"))
    except Exception:
        return
    data, env = _trade_memory_parse(raw)
    if not data:
        return
    changed = False
    close_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    scaled_on = scaled_exit_enabled()
    n_start = len(data)
    for i in range(n_start):
        r = data[i]
        if not isinstance(r, dict):
            continue
        if not r.get("virtual_signal"):
            continue
        if r.get("profit") is not None:
            continue
        r_sym = str(r.get("symbol") or "").strip()
        if r_sym != sym_f:
            continue
        try:
            entry = float(r["entry"])
            sl = float(r["sl"])
            tp1 = float(r["tp1"])
            tp2 = float(r["tp2"])
            tp3 = float(r["tp3"])
        except Exception:
            continue
        direction = str(r.get("direction") or "做多")
        # 主观察池：结构风控提前平仓（与硬 TP/SL 并行；优先于本根后续分支）
        if decision is not None:
            try:
                from utils.structure_guard import early_exit_recommendation

                side_cn = direction
                if side_cn in ("做多", "做空"):
                    ep_ct = float(price)
                    entry_f = float(entry)
                    if side_cn == "做多":
                        unreal = (ep_ct - entry_f) / entry_f * 100.0
                    else:
                        unreal = (entry_f - ep_ct) / entry_f * 100.0
                    exit_now, reason = early_exit_recommendation(
                        side_cn,
                        decision,
                        unreal,
                        None,
                        experiment_track=False,
                    )
                    if exit_now:
                        r["profit"] = round(unreal, 2)
                        r["close"] = round(ep_ct, 6)
                        r["close_time"] = close_iso
                        r["close_reason"] = str(reason)[:120]
                        changed = True
                        continue
            except Exception:
                pass
        if scaled_on and r.get("scaled_mode"):
            res = try_scaled_virtual_close(r, float(price), close_iso)
            if res is not None:
                closed, runner = res
                data[i] = closed
                if str(closed.get("close_reason") or "") == "SL":
                    register_virtual_sl_cooldown(
                        _REPO_ROOT, sym_f, str(closed.get("direction") or "")
                    )
                changed = True
                if runner is not None:
                    data.append(runner)
            continue
        if try_apply_main_virtual_tp1_partial(r, float(price), close_iso):
            changed = True
            if r.get("profit") is not None and str(r.get("close_reason") or "") == "SL":
                register_virtual_sl_cooldown(
                    _REPO_ROOT, sym_f, str(r.get("direction") or "")
                )
            continue
        hit = first_exit_tick(direction, entry, sl, tp1, tp2, tp3, float(price))
        if hit is None:
            continue
        bracket, profit_pct, close_px = hit
        r["profit"] = profit_pct
        r["close"] = round(float(close_px), 6)
        r["close_time"] = close_iso
        r["close_reason"] = _VIRTUAL_BR_TO_REASON.get(bracket, str(bracket).upper())
        if bracket == "sl":
            register_virtual_sl_cooldown(_REPO_ROOT, sym_f, direction)
        changed = True
    if changed:
        _trade_memory_write(data, env)
        _reload_evolution_memory_from_disk()
def _patch_strategy_analyzer_get_report() -> None:
    global _GET_REPORT_PATCHED
    if _GET_REPORT_PATCHED:
        return
    try:
        from evolution_core import StrategyAnalyzer
        def _patched_get_report(self):
            print("DEBUG: StrategyAnalyzer.get_report 被 patch 调用，今日模拟入场统计已刷新")
            print("DEBUG: StrategyAnalyzer.get_report 被调用，统计已刷新")
            print("DEBUG: StrategyAnalyzer.get_report 被调用，统计已强制刷新")
            today = datetime.now(_BJ).strftime("%Y-%m-%d")
            data = self.m.data
            rows = [r for r in data if isinstance(r, dict)]
            all_closed = [r for r in rows if r.get("profit") is not None]
            virtual_today = [
                r for r in rows if r.get("virtual_signal") and r.get("date") == today
            ]
            if not all_closed and not virtual_today:
                return {"status": "waiting"}
            t_total = len(all_closed)
            t_win = len([r for r in all_closed if float(r["profit"]) > 0])
            t_loss = t_total - t_win
            t_winr = round(t_win / t_total * 100, 2) if t_total else 0
            day_closed_all = [r for r in all_closed if r.get("date") == today]
            d_total = len(day_closed_all)
            d_win = len([r for r in day_closed_all if float(r["profit"]) > 0])
            d_loss = d_total - d_win
            d_winr = round(d_win / d_total * 100, 2) if d_total else 0
            longs = [r for r in all_closed if r.get("direction") in ("做多", "模拟入场")]
            shorts = [r for r in all_closed if r.get("direction") == "做空"]
            l_win = len([r for r in longs if float(r["profit"]) > 0])
            s_win = len([r for r in shorts if float(r["profit"]) > 0])
            l_winr = round(l_win / len(longs) * 100, 2) if longs else 0
            s_winr = round(s_win / len(shorts) * 100, 2) if shorts else 0
            day_closed_nv = [
                r
                for r in all_closed
                if r.get("date") == today and not r.get("virtual_signal")
            ]
            def _tkey(x: Dict) -> str:
                return str(x.get("entry_time") or "")
            day_orders = sorted(day_closed_nv + virtual_today, key=_tkey)
            return {
                "总交易": t_total,
                "总赢": t_win,
                "总亏": t_loss,
                "总胜率": t_winr,
                "今日交易": d_total,
                "今日模拟入场": len(virtual_today),
                "今日赢": d_win,
                "今日亏": d_loss,
                "今日胜率": d_winr,
                "做多胜率": l_winr,
                "做空胜率": s_winr,
                "今日订单": day_orders,
            }
        StrategyAnalyzer.get_report = _patched_get_report
        _GET_REPORT_PATCHED = True
    except Exception:
        pass
def _patch_evolution_report_reload() -> None:
    global _EVOL_REPORT_PATCHED
    if _EVOL_REPORT_PATCHED:
        return
    try:
        from evolution_core import ai_evo
        _orig = ai_evo.report
        def _report_reload() -> Any:
            _ensure_memos_hotfixes()
            _reload_evolution_memory_from_disk()
            return _orig()
        ai_evo.report = _report_reload
        _EVOL_REPORT_PATCHED = True
    except Exception:
        pass
def _patch_main_trade_memory_preview() -> None:
    global _MAIN_PREVIEW_PATCHED
    try:
        import builtins
        import sys

        builtins._longxia_trade_memory_preview_rows_html = trade_memory_preview_rows_html
        for _name in ("__main__", "main"):
            _m = sys.modules.get(_name)
            if _m is not None and hasattr(_m, "_trade_memory_preview_rows"):
                _MAIN_PREVIEW_PATCHED = True
    except Exception:
        pass
def _ensure_memos_hotfixes() -> None:
    _patch_strategy_analyzer_get_report()
    _patch_evolution_report_reload()
    _patch_main_trade_memory_preview()
def _load_state() -> Dict[str, Any]:
    try:
        raw = _STATE_FILE.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception:
        return {}


def _state_slice_for_symbol(raw: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """读取当前交易对的状态：新结构为根级 `by_symbol.{pair}`；旧版为根级扁平字段。
    若误用整份 JSON 根对象取 `signals_today`，在仅含 `by_symbol` 时恒为 0，虚拟 memos 与页面计数会失效。"""
    if not isinstance(raw, dict):
        return {}
    sym = str(symbol or "").strip()
    nested = raw.get("by_symbol")
    if isinstance(nested, dict) and sym:
        block = nested.get(sym)
        return dict(block) if isinstance(block, dict) else {}
    if nested is None:
        return raw
    return {}
def _tf_trend_word(closes: List[float], stride: int) -> str:
    if len(closes) < stride * 3:
        return "震荡"
    sampled = closes[::stride][-40:]
    if len(sampled) < 3:
        return "震荡"
    chg = (sampled[-1] - sampled[0]) / max(sampled[0], 1e-12) * 100
    if chg > 0.04:
        return "上涨"
    if chg < -0.04:
        return "下跌"
    return "震荡"
def _calc_probs(rsi_1m: float, trend_score: float) -> tuple[float, float]:
    if rsi_1m < 30:
        prob_up = 65 + trend_score * 10
    elif rsi_1m > 70:
        prob_up = 35 - trend_score * 10
    else:
        prob_up = 50 + trend_score * 5
    prob_up = max(30.0, min(70.0, prob_up))
    prob_up = round(prob_up, 1)
    prob_down = round(100.0 - prob_up, 1)
    return prob_up, prob_down
def _fetch_latest_5m_candle(symbol: str) -> Optional[Dict[str, Any]]:
    rows: List[List[Any]] = gate_fetch_ohlcv(symbol, timeframe="5m", limit=2)
    if not rows:
        return None
    ts, o, h, l, c, v = rows[-1]
    return {
        "time": int(ts),
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "volume": float(v),
    }
class LiveTrading:
    """现货 / 永续合约 ticker（仅快照用，与 data_fetcher 现货逻辑一致）。"""
    def fetch_current_ticker_price(self, symbol: str) -> str:
        """Gate.io 现货实时价（与 data_fetcher 一致）。"""
        try:
            price = float(_fetch_current_ticker_price_sync(symbol))
            return f"{price:.4f}" if price < 1000 else f"{price:.2f}"
        except Exception:
            return "—"
    def fetch_futures_ticker_price(self, symbol: str) -> str:
        """获取 Gate.io 永续合约实时价（swap）"""
        try:
            futures_ex = ccxt.gateio({"enableRateLimit": True})
            futures_ex.options["defaultType"] = "swap"
            ticker = futures_ex.fetch_ticker(symbol)
            price = float(ticker["last"])
            return f"{price:.4f}" if price < 1000 else f"{price:.2f}"
        except Exception:
            return "—"
_LT = LiveTrading()
# ---------------------------------------------------------------------------
# trading_theory_library.json
# ---------------------------------------------------------------------------
def ensure_trading_theory_library() -> None:
    if _THEORY_FILE.exists():
        return
    payload = {
        "version": 1,
        "books": {
            "日本蜡烛图技术": [
                "反转日需成交量确认",
                "吞没形态实体应覆盖前一根大部",
            ],
            "裸K线交易法": [
                "Pin Bar 影线需显著大于实体",
                "内包K突破母K极值再跟进",
            ],
            "短线交易秘诀": [
                "顺势轻仓，逆势观望",
                "冷却与重复信号需去重",
            ],
            "以交易为生": [
                "风险先定，再谈收益",
                "纪律重于预测",
            ],
            "专业投机原理": [
                "趋势、位置、形态共振更可靠",
                "概率优势需大样本验证",
            ],
        },
    }
    _THEORY_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_theory_books() -> Dict[str, List[str]]:
    """五书 + Hermes 技能库节选（digest）；不写 trade_memory。"""
    ensure_trading_theory_library()
    try:
        raw = json.loads(_THEORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    books: Dict[str, List[str]] = dict(raw.get("books") or {})
    try:
        from utils.hft_skill_brain import load_hermes_digest_lines

        hermes_lines = load_hermes_digest_lines()
    except Exception:
        hermes_lines = []
    if hermes_lines:
        books["Hermes_HFT技能库"] = hermes_lines
    return books


def _pick_theory_hints(
    symbol: str,
    rsi_1m: float,
    books: Dict[str, List[str]],
) -> str:
    """按当前上下文从五本书 + Hermes 节选各抽 0～2 条短句，供手动跟单对照（参考）。"""
    hints: List[str] = []
    order = [
        "日本蜡烛图技术",
        "裸K线交易法",
        "短线交易秘诀",
        "以交易为生",
        "专业投机原理",
    ]
    for title in order:
        rows = books.get(title) or []
        if not rows:
            continue
        i = (abs(hash(str(symbol))) + int(rsi_1m * 10)) % len(rows)
        hints.append(f"【{title}】{rows[i]}")
    hft_rows = books.get("Hermes_HFT技能库") or []
    if hft_rows:
        i1 = (abs(hash(str(symbol))) + int(rsi_1m)) % len(hft_rows)
        hints.append(f"【Hermes_HFT技能库】{hft_rows[i1]}")
        if len(hft_rows) > 1:
            i2 = (i1 + 7) % len(hft_rows)
            hints.append(f"【Hermes_HFT技能库·补】{hft_rows[i2]}")
    if not hints:
        return "（当前未命中额外抽书条款；规则仍以指标与形态为准）"
    return " ".join(hints)


# ---------------------------------------------------------------------------
# 贝叶斯 Beta（轻量，与 45s 刷新对齐节流）
# ---------------------------------------------------------------------------
def _beta_load() -> Tuple[float, float]:
    try:
        if _BAYES_FILE.exists():
            d = json.loads(_BAYES_FILE.read_text(encoding="utf-8"))
            return float(d.get("alpha", 2)), float(d.get("beta", 2))
    except Exception:
        pass
    return 2.0, 2.0
def _beta_save(alpha: float, beta: float) -> None:
    _BAYES_FILE.write_text(
        json.dumps({"alpha": alpha, "beta": beta, "updated": time.time()}, indent=2),
        encoding="utf-8",
    )
def beta_posterior_mean() -> float:
    a, b = _beta_load()
    return a / (a + b + 1e-9)
def beta_update_from_score_throttled(score: float) -> float:
    global _LAST_BETA_TS
    a, b = _beta_load()
    now = time.time()
    if now - _LAST_BETA_TS < 44.0:
        return a / (a + b + 1e-9)
    _LAST_BETA_TS = now
    win_w = max(0.0, min(1.0, (score + 1) / 2))
    lose_w = 1.0 - win_w
    a += win_w * 0.35
    b += lose_w * 0.35
    _beta_save(a, b)
    return a / (a + b + 1e-9)


def beta_posterior_mean_for_replay_bar(
    score: float, bar_ts_sec: float, st: Dict[str, Any]
) -> float:
    """与 ``beta_update_from_score_throttled`` 同更新律，用于 bar 回放。

    - 使用 K 线时间 ``bar_ts_sec``（秒）做 44s 节流，与线上用 wall clock 不同但回放单调递增、可复现；
    - 仅读写 ``st`` 中 ``alpha`` / ``beta`` / ``last_update_ts``，**不**读写到 ``bayes_beta_state.json``。

    ``get_v313_decision_snapshot`` 在合并 ``experiment_km_for_bar`` 前写入 ``bayes_posterior_winrate``；
    回测侧应对 ``km_bar`` 做同等字段补齐，否则 ``_experiment_entry_filter_legacy`` 易因 post=0 恒不满足。
    """
    a = float(st.get("alpha", 2.0))
    b = float(st.get("beta", 2.0))
    last = float(st.get("last_update_ts", -1e30))
    if bar_ts_sec - last < 44.0:
        return a / (a + b + 1e-9)
    win_w = max(0.0, min(1.0, (score + 1) / 2))
    lose_w = 1.0 - win_w
    a += win_w * 0.35
    b += lose_w * 0.35
    st["alpha"] = a
    st["beta"] = b
    st["last_update_ts"] = bar_ts_sec
    return a / (a + b + 1e-9)
# ---------------------------------------------------------------------------
# PatternRecognizer：在 detect_kline_pattern 基础上扩展
# ---------------------------------------------------------------------------
class PatternRecognizer:
    @staticmethod
    def _pin_inside(klines: List[Dict]) -> List[str]:
        out: List[str] = []
        if len(klines) < 2:
            return out
        o, h, l, c = (
            float(klines[-1]["open"]),
            float(klines[-1]["high"]),
            float(klines[-1]["low"]),
            float(klines[-1]["close"]),
        )
        body = abs(c - o)
        rng = max(h - l, 1e-12)
        upper = h - max(o, c)
        lower = min(o, c) - l
        if body < 0.25 * rng and upper > 1.8 * body and upper > lower * 1.2:
            out.append("📍 看跌 Pin Bar（裸K）")
        if body < 0.25 * rng and lower > 1.8 * body and lower > upper * 1.2:
            out.append("📍 看涨 Pin Bar（裸K）")
        p, q = klines[-2], klines[-1]
        h2, l2 = float(p["high"]), float(p["low"])
        h1, l1 = float(q["high"]), float(q["low"])
        if h1 < h2 and l1 > l2:
            out.append("📦 内包K线（整理）")
        return out
    @staticmethod
    def _chart_fractal(klines: List[Dict]) -> List[str]:
        out: List[str] = []
        if len(klines) < 25:
            return out
        highs = np.array([float(x["high"]) for x in klines[-25:]])
        lows = np.array([float(x["low"]) for x in klines[-25:]])
        if highs[-1] > np.percentile(highs, 85) and lows[-1] > lows[-5]:
            out.append("🔻 简化头肩顶嫌疑（弱）")
        if lows[-1] < np.percentile(lows, 15) and highs[-1] < highs[-5]:
            out.append("🔺 简化头肩底嫌疑（弱）")
        rh = float(np.std(highs[-15:]))
        rl = float(np.std(lows[-15:]))
        if rh < float(np.std(highs[-25:-10])) * 0.6 and rl < float(np.std(lows[-25:-10])) * 0.6:
            out.append("📐 三角形收敛（简化）")
        return out
    @staticmethod
    def _three_drives(klines: List[Dict]) -> List[str]:
        if len(klines) < 20:
            return []
        c = np.array([float(x["close"]) for x in klines[-20:]])
        piv: List[Tuple[int, float, str]] = []
        for i in range(2, len(c) - 2):
            if c[i] < c[i - 1] and c[i] < c[i + 1]:
                piv.append((i, c[i], "L"))
            if c[i] > c[i - 1] and c[i] > c[i + 1]:
                piv.append((i, c[i], "H"))
        if len(piv) >= 3 and piv[-1][2] == "L" and piv[-2][2] == "H" and piv[-3][2] == "L":
            return ["🎯 三推见底雏形（弱）"]
        if len(piv) >= 3 and piv[-1][2] == "H" and piv[-2][2] == "L" and piv[-3][2] == "H":
            return ["🎯 三推见顶雏形（弱）"]
        return []
    @staticmethod
    def fib_levels(last_swing_high: float, last_swing_low: float) -> Dict[str, float]:
        lo = min(last_swing_low, last_swing_high)
        hi = max(last_swing_low, last_swing_high)
        r = hi - lo
        if r <= 0:
            return {}
        return {
            "fib_0.382": hi - 0.382 * r,
            "fib_0.618": hi - 0.618 * r,
            "fib_1.618_up": lo + 1.618 * r,
            "fib_1.618_down": hi - 1.618 * r,
        }
    @classmethod
    def merge_patterns(cls, klines: List[Dict]) -> Tuple[List[str], Dict[str, float]]:
        base = detect_kline_pattern(klines[-64:]) if len(klines) >= 3 else []
        extra: List[str] = []
        extra.extend(cls._pin_inside(klines[-4:]))
        extra.extend(cls._chart_fractal(klines))
        extra.extend(cls._three_drives(klines))
        fib_map: Dict[str, float] = {}
        if len(klines) >= 40:
            seg = klines[-40:]
            hi = max(float(x["high"]) for x in seg)
            lo = min(float(x["low"]) for x in seg)
            fib_map = cls.fib_levels(hi, lo)
        seen = set()
        merged: List[str] = []
        for p in base + extra:
            if p not in seen:
                seen.add(p)
                merged.append(p)
        return merged, fib_map
def _levels_for_direction(entry: float, direction: str) -> Tuple[float, float, float, float]:
    e = float(entry)
    if direction == "做空":
        sl = e * (1.0 + 0.003)
        tp1 = e * (1.0 - 0.0012)
        tp2 = e * (1.0 - 0.0045)
        return sl, tp1, tp2, tp2
    sl = e * (1.0 - 0.003)
    tp1 = e * (1.0 + 0.0012)
    tp2 = e * (1.0 + 0.0045)
    return sl, tp1, tp2, tp2


def _experiment_track_enabled() -> bool:
    v = os.environ.get("LONGXIA_EXPERIMENT_TRACK", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _env_experiment_fib_on() -> bool:
    """LONGXIA_EXPERIMENT_USE_FIB_LEVELS=1 时对实验轨 SL/TP1 做斐波位修正（默认关）。"""
    v = os.environ.get("LONGXIA_EXPERIMENT_USE_FIB_LEVELS", "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _levels_with_fib(
    entry: float,
    direction: str,
    base: Tuple[float, float, float, float],
    fib_map: Optional[Dict[str, Any]],
) -> Tuple[Tuple[float, float, float, float], Dict[str, Any]]:
    """
    用 swing 区间斐波（0.618 回撤、1.618 扩展）微调实验轨价位；不改变则 levels_source=fixed_pct。
    fib_map 键与 PatternRecognizer.merge_patterns 一致：fib_0.618、fib_1.618_up/down。
    """
    sl, tp1, tp2, tp3 = (float(base[0]), float(base[1]), float(base[2]), float(base[3]))
    e = float(entry)
    meta: Dict[str, Any] = {"levels_source": "fixed_pct"}
    if not fib_map or not isinstance(fib_map, dict) or not _env_experiment_fib_on():
        return (sl, tp1, tp2, tp3), meta
    try:
        f618 = float(fib_map.get("fib_0.618") or 0.0)
    except Exception:
        f618 = 0.0
    try:
        f1u = float(fib_map.get("fib_1.618_up") or 0.0)
    except Exception:
        f1u = 0.0
    try:
        f1d = float(fib_map.get("fib_1.618_down") or 0.0)
    except Exception:
        f1d = 0.0
    changed = False
    if direction == "做多":
        if f618 > 0 and sl < f618 < e:
            sl = f618
            changed = True
        if f1u > 0 and e < f1u:
            ntp1 = min(tp1, f1u)
            if abs(ntp1 - tp1) > 1e-12 * max(e, 1.0):
                tp1 = ntp1
                changed = True
    elif direction == "做空":
        if f618 > 0 and e < f618 < sl:
            sl = f618
            changed = True
        if f1d > 0 and f1d < e:
            ntp1 = min(tp1, f1d)
            if abs(ntp1 - tp1) > 1e-12 * max(e, 1.0):
                tp1 = ntp1
                changed = True
    if changed:
        meta["levels_source"] = "fib_dynamic"
        if f618 > 0:
            meta["fib_0_618"] = f618
        if f1u > 0:
            meta["fib_1_618_up"] = f1u
        if f1d > 0:
            meta["fib_1_618_down"] = f1d
    return (sl, tp1, tp2, tp3), meta


def _experiment_levels_for_direction(
    entry: float, direction: str
) -> Tuple[float, float, float, float]:
    """规则实验轨 SL/TP：默认比主观察池更宽，具体比例可用环境变量再调。"""
    e = float(entry)
    sl_pct = float(os.environ.get("LONGXIA_EXPERIMENT_SL_PCT", "0.008"))
    tp1_pct = float(os.environ.get("LONGXIA_EXPERIMENT_TP1_PCT", "0.004"))
    tp2_pct = float(os.environ.get("LONGXIA_EXPERIMENT_TP2_PCT", "0.01"))
    tp3_pct = float(os.environ.get("LONGXIA_EXPERIMENT_TP3_PCT", "0.016"))
    if direction == "做空":
        sl = e * (1.0 + sl_pct)
        tp1 = e * (1.0 - tp1_pct)
        tp2 = e * (1.0 - tp2_pct)
        tp3 = e * (1.0 - tp3_pct)
        return sl, tp1, tp2, tp3
    sl = e * (1.0 - sl_pct)
    tp1 = e * (1.0 + tp1_pct)
    tp2 = e * (1.0 + tp2_pct)
    tp3 = e * (1.0 + tp3_pct)
    return sl, tp1, tp2, tp3


def _price_levels_self_check(
    entry: float,
    direction: str,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
) -> bool:
    try:
        e, s, a, b, c = (
            float(entry),
            float(sl),
            float(tp1),
            float(tp2),
            float(tp3),
        )
    except Exception:
        return False
    if min(e, s, a, b, c) <= 0:
        return False
    if direction == "做多":
        return s < e < a <= b <= c
    if direction == "做空":
        return s > e > a >= b >= c
    return False


def _experiment_mode_normalized() -> str:
    m = os.environ.get("LONGXIA_EXPERIMENT_MODE", "kronos_light").strip().lower()
    if m in ("legacy", "kronos_light", "kronos_model"):
        return m
    return "kronos_light"


def _experiment_entry_filter_legacy(km: Dict[str, Any]) -> bool:
    """旧版实验轨：强一致性 + 贝叶斯（偏严，易长时间无单）。"""
    sig = str(km.get("signal_label") or "")
    if not (sig.startswith("偏多") or sig.startswith("偏空")):
        return False
    try:
        cs = float(km.get("consistency_score") or 0.0)
    except Exception:
        cs = 0.0
    min_c = float(os.environ.get("LONGXIA_EXPERIMENT_MIN_CONSISTENCY", "0.35"))
    if abs(cs) < min_c:
        return False
    try:
        post = float(km.get("bayes_posterior_winrate") or 0.0)
    except Exception:
        post = 0.0
    min_b = float(os.environ.get("LONGXIA_EXPERIMENT_MIN_BAYES", "0.45"))
    if post < min_b:
        return False
    return True


def _experiment_entry_filter_kronos_light(km: Dict[str, Any]) -> bool:
    """Kronos-light：仅强多/强空；概率差、consistency、Gate+裸K、MTF+ATR、regime 调阈值（依赖快照 experiment_*）。"""
    sig = str(km.get("signal_label") or "")
    if not (sig.startswith("偏多（强）") or sig.startswith("偏空（强）")):
        return False
    regime = str(km.get("experiment_kronos_regime") or "mid")
    edge_base = float(os.environ.get("LONGXIA_KRONOS_MIN_PROB_EDGE", "5"))
    edge_chop = float(os.environ.get("LONGXIA_EXPERIMENT_EDGE_CHOP_EXTRA", "3"))
    edge_mid = float(os.environ.get("LONGXIA_EXPERIMENT_EDGE_MID_EXTRA", "0"))
    extra = edge_chop if regime == "chop" else (edge_mid if regime == "mid" else 0.0)
    use_tpl = bool(km.get("experiment_markov_template_enabled"))
    if use_tpl:
        need_edge = float(km.get("experiment_markov_need_edge") or edge_base)
        score_floor = float(km.get("experiment_markov_score_floor") or 0.7)
    else:
        need_edge = edge_base + extra
        if regime == "trend":
            trend_cap = float(os.environ.get("LONGXIA_EXPERIMENT_TREND_EDGE", "12"))
            need_edge = min(need_edge, trend_cap)
        score_floor0 = float(os.environ.get("LONGXIA_EXPERIMENT_MIN_SCORE_ABS", "0.45"))
        s_chop = float(os.environ.get("LONGXIA_EXPERIMENT_SCORE_CHOP_FLOOR", "0.68"))
        s_mid = float(os.environ.get("LONGXIA_EXPERIMENT_SCORE_MID_FLOOR", "0.45"))
        score_floor = score_floor0
        if regime == "chop":
            score_floor = max(score_floor, s_chop)
        elif regime == "mid":
            score_floor = max(score_floor, s_mid)
    tpl = str(km.get("markov_template") or os.environ.get("LONGXIA_MARKOV_TEMPLATE", "off")).strip().lower()
    if tpl in ("strict_chop", "balanced"):
        npb = km.get("markov_next_prob") or {}
        need_edge, score_floor = apply_markov_template_to_thresholds(
            regime=regime,
            edge_base=edge_base,
            edge_extra=0.0 if use_tpl else extra,
            need_edge=need_edge,
            score_floor=score_floor,
            next_prob=npb if isinstance(npb, dict) else {},
            template=tpl,
        )
    try:
        pu = float(km.get("prob_up_5m") or 0.0)
        pd = float(km.get("prob_down_5m") or 0.0)
    except Exception:
        pu, pd = 0.0, 0.0
    if sig.startswith("偏多") and (pu - pd) < need_edge:
        return False
    if sig.startswith("偏空") and (pd - pu) < need_edge:
        return False
    try:
        cs = float(km.get("consistency_score") or 0.0)
    except Exception:
        cs = 0.0
    abs_score = abs(cs)
    if abs_score < score_floor:
        return False
    if not km.get("experiment_kronos_gate_ok"):
        return False
    if not km.get("experiment_kronos_mtf_ok"):
        return False
    pattern_ok = bool(km.get("experiment_kronos_pattern_ok"))
    allow_trend_np = os.environ.get(
        "LONGXIA_EXPERIMENT_TREND_ALLOW_NO_PATTERN", "1"
    ).strip().lower() not in ("0", "false", "no", "off")
    allow_mid_np = os.environ.get(
        "LONGXIA_EXPERIMENT_MID_ALLOW_NO_PATTERN", "1"
    ).strip().lower() not in ("0", "false", "no", "off")
    if not pattern_ok:
        if regime == "trend" and allow_trend_np:
            pass
        elif regime == "mid" and allow_mid_np:
            pass
        else:
            return False
    if not km.get("experiment_atr_vol_ok"):
        return False
    return True


def _experiment_entry_filter(km: Dict[str, Any]) -> bool:
    mode = _experiment_mode_normalized()
    if mode == "legacy":
        return _experiment_entry_filter_legacy(km)
    if mode == "kronos_model":
        # 第二阶段：接 integrations.kronos_experiment_optional；未实现前与 kronos_light 一致
        return _experiment_entry_filter_kronos_light(km)
    return _experiment_entry_filter_kronos_light(km)


def sync_experiment_track_from_snapshot(
    symbol: str, px: float, km: Dict[str, Any]
) -> None:
    """规则实验轨：与主观察池共用快照；先 tick（平仓+风控登记）再按筛选开仓（非 virtual_signal）。"""
    if not _experiment_track_enabled():
        return
    try:
        from evolution_core import ai_evo
        from utils.experiment_risk_state import (
            day_loss_exceeded,
            direction_blocked_by_single_side,
            direction_in_cooldown,
            is_paused,
            register_close,
        )
    except Exception:
        return
    try:
        pxf = float(px)
    except Exception:
        return
    if pxf <= 0:
        return
    sym = str(symbol or "").strip()
    if not sym:
        return
    pause_sec = float(os.environ.get("LONGXIA_EXPERIMENT_PAUSE_SEC", "900"))
    close_ret = ai_evo.tick(pxf, sym)
    if close_ret:
        profit_pct, dir_closed = close_ret
        register_close(
            _REPO_ROOT,
            profit_pct,
            direction=str(dir_closed),
            pause_sec=pause_sec,
            max_consecutive_before_pause=2,
        )
    if is_paused(_REPO_ROOT):
        return
    if day_loss_exceeded(_REPO_ROOT):
        return
    if not _experiment_entry_filter(km):
        return
    if km.get("experiment_markov_template_enabled"):
        mf = float(km.get("experiment_markov_max_frequency_sec") or 0.0)
        if mf > 0 and not _experiment_frequency_allow(sym, mf):
            return
    sig = str(km.get("signal_label") or "")
    if sig.startswith("偏多"):
        direction = "做多"
    elif sig.startswith("偏空"):
        direction = "做空"
    else:
        return
    if direction_blocked_by_single_side(direction):
        return
    if direction_in_cooldown(_REPO_ROOT, direction):
        return
    try:
        entry = float(km.get("entry_price") or pxf)
    except Exception:
        entry = pxf
    base_lv = _experiment_levels_for_direction(entry, direction)
    sl, tp1, tp2, tp3 = base_lv
    fib_meta: Dict[str, Any] = {"levels_source": "fixed_pct"}
    if _env_experiment_fib_on():
        lv2, fib_meta = _levels_with_fib(
            entry, direction, base_lv, km.get("fib_levels")
        )
        sl, tp1, tp2, tp3 = lv2
    mk_tpl = str(km.get("markov_template") or "")
    tpl_en = bool(km.get("experiment_markov_template_enabled"))
    extra_meta: Dict[str, Any] = {
        "markov_template": mk_tpl,
        "experiment_markov_template_enabled": tpl_en,
    }
    extra_meta.update(fib_meta)
    mode = _experiment_mode_normalized()
    if mode == "legacy":
        if not _price_levels_self_check(entry, direction, sl, tp1, tp2, tp3):
            return
    for t in ai_evo.memory.open_trades:
        if str(t.get("symbol") or "").strip() == sym:
            return
    ai_evo.record(
        direction,
        entry,
        sl,
        tp1,
        tp2,
        tp3,
        symbol=sym,
        **extra_meta,
    )
    if km.get("experiment_markov_template_enabled"):
        mf = float(km.get("experiment_markov_max_frequency_sec") or 0.0)
        if mf > 0:
            _experiment_frequency_mark_entry(sym)


def _background_scan_all_symbols_once() -> None:
    for sym in _EXPERIMENT_SCAN_SYMBOLS:
        try:
            px = float(_fetch_current_ticker_price_sync(sym))
            if px <= 0:
                continue
            km = get_v313_decision_snapshot(force_refresh=True, symbol=sym)
            sync_virtual_memos_from_state(sym, px, decision=km)
            sync_experiment_track_from_snapshot(sym, px, km)
        except Exception:
            continue


def _start_background_scan_thread_if_needed() -> None:
    global _BG_SCAN_STARTED
    if _BG_SCAN_STARTED:
        return
    _BG_SCAN_STARTED = True
    interval = float(os.environ.get("LONGXIA_EXPERIMENT_SCAN_INTERVAL_SEC", "60"))

    def _loop() -> None:
        time.sleep(3.0)
        while True:
            try:
                _background_scan_all_symbols_once()
            except Exception:
                pass
            time.sleep(max(15.0, interval))

    threading.Thread(target=_loop, daemon=True).start()


def _append_virtual_trade_memory_local(
    symbol: str, entry: float, direction_label: str, last_sig: int
) -> None:
    today = datetime.now(_BJ).strftime("%Y-%m-%d")
    entry = float(entry)
    if direction_label == "做空":
        d = "做空"
        sl, tp1, tp2, tp3 = _levels_for_direction(entry, "做空")
    elif direction_label == "做多":
        d = "做多"
        sl, tp1, tp2, tp3 = _levels_for_direction(entry, "做多")
    else:
        d = "模拟入场"
        sl, tp1, tp2, tp3 = _levels_for_direction(entry, "做多")
    widen_dir = "做空" if d == "做空" else "做多"
    if dynamic_levels_enabled():
        try:
            snap = build_indicator_snapshot(symbol, 500)
            klines_lv = snap.get("klines") or []
            closes_lv = [float(k["close"]) for k in klines_lv]
            if closes_lv:
                sl, tp1, tp2, tp3 = widen_levels_from_closes(
                    entry, widen_dir, (sl, tp1, tp2, tp3), closes_lv
                )
        except Exception:
            pass
    rec = {
        "date": today,
        "entry_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "close_time": "—",
        "direction": d,
        "entry": round(entry, 6),
        "sl": round(sl, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "tp3": round(tp3, 6),
        "close": None,
        "profit": None,
        "virtual_signal": True,
        "symbol": symbol,
        "last_sig": last_sig,
    }
    if scaled_exit_enabled() and not main_virtual_tp1_partial_enabled():
        rec["scaled_mode"] = True
        rec["scaled_stage"] = 0
        rec["scaled_remaining_orig"] = 1.0
        rec["scaled_group_id"] = uuid.uuid4().hex
    data: List[dict] = []
    env: Optional[Dict[str, Any]] = None
    if _TRADE_MEMORY.exists():
        try:
            raw = json.loads(_TRADE_MEMORY.read_text(encoding="utf-8"))
            data, env = _trade_memory_parse(raw)
        except Exception:
            data, env = [], None
    data.append(rec)
    _trade_memory_write(data, env)
    _reload_evolution_memory_from_disk()
def _resource_line() -> str:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.05)
        ram = psutil.virtual_memory().percent
        return f"CPU {cpu:.1f}% · 内存 {ram:.1f}%"
    except Exception:
        return "CPU/内存：不可用（可 pip install psutil）"
def _rr_fee_hint(entry: float, sl: float, tp1: float, direction: str) -> str:
    try:
        e, s, t = float(entry), float(sl), float(tp1)
        risk = abs(e - s)
        rew = abs(t - e)
        rr = rew / (risk + 1e-12)
        fee = 0.16
        return f"R:R≈{rr:.2f} · 双边手续费约{fee:.2f}%"
    except Exception:
        return "R:R：—"
def _sig_label_from_rsi_t5(rsi_1m: float, t5: str) -> str:
    sig_label = "无"
    if rsi_1m < 35 and t5 in ("上涨", "震荡"):
        sig_label = "偏多（轻）"
    elif rsi_1m > 65 and t5 in ("下跌", "震荡"):
        sig_label = "偏空（轻）"
    return sig_label


def experiment_km_for_bar(
    symbol: str,
    klines: List[Dict[str, Any]],
    closes: List[float],
    *,
    rsi_1m: float,
    t5: str,
    sig_label: str,
    score: float,
    prob_up: float,
    prob_down: float,
    markov_tracker: Optional[Any] = None,
    markov_template: Optional[str] = None,
    force_markov_threshold_template: Optional[bool] = None,
) -> Dict[str, Any]:
    """实验轨筛选所需字段 + Markov（供 get_v313 与 backtest 共用）。"""
    experiment_atr_pct = atr_percent_proxy(klines) if klines else 0.0
    atr_chop_max = float(os.environ.get("LONGXIA_EXPERIMENT_ATR_CHOP_MAX", "0.12"))
    atr_trend_min = float(os.environ.get("LONGXIA_EXPERIMENT_ATR_TREND_MIN", "0.22"))
    experiment_kronos_regime = markov_regime(
        t5, experiment_atr_pct, atr_chop_max=atr_chop_max, atr_trend_min=atr_trend_min
    )
    experiment_kronos_mtf_ok = mtf_aligned(closes, sig_label)
    wick_ratio = float(os.environ.get("LONGXIA_EXPERIMENT_WICK_BODY_RATIO", "0.6"))
    experiment_kronos_pattern_ok = has_engulfing_or_key_pattern(
        klines
    ) or last_bar_wick_dominant(klines, wick_body_ratio=wick_ratio)
    gate_dev = float(os.environ.get("LONGXIA_EXPERIMENT_GATE_RSI_DEV", "12"))
    experiment_kronos_gate_ok = gate_deviation_ok(rsi_1m, sig_label, min_dev=gate_dev)
    atr_min_pct = float(os.environ.get("LONGXIA_EXPERIMENT_ATR_MIN_PCT", "0.05"))
    experiment_atr_vol_ok = experiment_atr_pct >= atr_min_pct

    tpl = (markov_template or os.environ.get("LONGXIA_MARKOV_TEMPLATE", "off")).strip().lower()
    if tpl not in ("off", "strict_chop", "balanced"):
        tpl = "off"
    if markov_tracker is not None:
        ms = markov_tracker.step(experiment_kronos_regime)
        next_prob = ms["next_prob"]
        markov_regime_line = str(ms.get("line") or "")
        markov_regime_state = {k: v for k, v in ms.items() if k != "line"}
    else:
        ms = update_and_summarize_regime(_REPO_ROOT, experiment_kronos_regime)
        next_prob = ms["next_prob"]
        markov_regime_line = str(ms.get("line") or "")
        markov_regime_state = {k: v for k, v in ms.items() if k != "line"}

    use_tpl = _use_markov_threshold_template_resolved(force_markov_threshold_template)
    tpl_cfg: Dict[str, Any] = {}
    tpl_line = "—（未启用策略层 Markov 阈值模板）"
    tpl_name = ""
    need_edge_v: Optional[float] = None
    score_floor_v: Optional[float] = None
    max_freq_sec = 0.0
    if use_tpl:
        tpl_cfg = get_threshold_template(experiment_kronos_regime)
        tpl_name = str(tpl_cfg.get("template_name") or "")
        need_edge_v = float(tpl_cfg.get("probability_diff_threshold") or 18.0)
        score_floor_v = float(tpl_cfg.get("consistency_score_threshold") or 0.7)
        max_freq_sec = float(tpl_cfg.get("max_frequency_sec") or 0.0)
        if max_freq_sec >= 60:
            freq_zh = f"每{int(max_freq_sec // 60)}分钟最多1单"
        else:
            freq_zh = f"每{int(max(1, max_freq_sec))}秒最多1单"
        tpl_line = (
            f"当前策略模板：{tpl_name}（Markov，状态={experiment_kronos_regime}）｜"
            f"prob_diff≥{need_edge_v}%｜consistency≥{score_floor_v * 100:.0f}%｜频率≤{freq_zh}"
        )

    return {
        "symbol": symbol,
        "signal_label": sig_label,
        "consistency_score": score,
        "prob_up_5m": prob_up,
        "prob_down_5m": prob_down,
        "experiment_kronos_regime": experiment_kronos_regime,
        "experiment_kronos_mtf_ok": experiment_kronos_mtf_ok,
        "experiment_kronos_pattern_ok": experiment_kronos_pattern_ok,
        "experiment_kronos_gate_ok": experiment_kronos_gate_ok,
        "experiment_atr_vol_ok": experiment_atr_vol_ok,
        "experiment_atr_pct": experiment_atr_pct,
        "markov_next_prob": next_prob,
        "markov_regime_state": markov_regime_state,
        "markov_regime_line": markov_regime_line,
        "markov_template": tpl,
        "experiment_markov_template_enabled": use_tpl,
        "experiment_markov_template_config": tpl_cfg if use_tpl else {},
        "experiment_markov_template_line": tpl_line,
        "experiment_markov_template": tpl_name if use_tpl else "",
        "experiment_markov_need_edge": need_edge_v,
        "experiment_markov_score_floor": score_floor_v,
        "experiment_markov_max_frequency_sec": max_freq_sec,
    }


def _apply_breakout_to_signal_label(sig_label: str, breakout: Dict[str, Any]) -> str:
    """
    机械触发对主观察池信号：不利时只把「强」降为「轻」，不因 mode=none 或未触发而写成「无」，保留样本量。
    """
    v = os.environ.get("LONGXIA_MAIN_BREAKOUT_SIGNAL_FILTER", "1").strip().lower()
    if v in ("0", "false", "no", "off"):
        return sig_label
    mode = str(breakout.get("mode") or "none")
    bdir = str(breakout.get("direction") or "none")

    def relax_strong(s: str) -> str:
        if s.startswith("偏多（强）"):
            return "偏多（轻）"
        if s.startswith("偏空（强）"):
            return "偏空（轻）"
        return s

    if mode == "false_break":
        if bdir == "up" and sig_label.startswith("偏多"):
            return relax_strong(sig_label)
        if bdir == "down" and sig_label.startswith("偏空"):
            return relax_strong(sig_label)
    if mode in ("breakout", "retest_confirm"):
        if bdir == "down" and sig_label.startswith("偏多"):
            return relax_strong(sig_label)
        if bdir == "up" and sig_label.startswith("偏空"):
            return relax_strong(sig_label)
    return sig_label


def _breakout_trigger_state(
    klines: List[Dict[str, Any]],
    realtime_price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    三套机械触发条件（主观察池快照 + 软过滤；不接下单）：
      breakout — 区间带缓冲的有效突破
      false_break — 窗口内刺破区间极值后收回
      retest_confirm — 曾有效突破后回踩近区间边界再站回
    判定现价优先用 realtime_price（CCXT ticker），缺省则退回最后一根 K 收盘价。
    """
    out: Dict[str, Any] = {
        "mode": "none",
        "direction": "none",
        "reason": "",
        "up_threshold": None,
        "down_threshold": None,
        "range_high": None,
        "range_low": None,
        "eval_price": None,
        "price_basis": "last_close",
    }
    try:
        lb = int(os.environ.get("LONGXIA_MAIN_BREAKOUT_LOOKBACK_BARS", "48"))
    except ValueError:
        lb = 48
    try:
        buf = float(os.environ.get("LONGXIA_MAIN_BREAKOUT_BUFFER_PCT", "0.08"))
    except ValueError:
        buf = 0.08
    try:
        rev = int(os.environ.get("LONGXIA_MAIN_FALSE_BREAK_REVERT_BARS", "6"))
    except ValueError:
        rev = 6
    lb = max(10, min(lb, 500))
    rev = max(2, min(rev, 30))

    if not klines or len(klines) < lb + 2:
        out["reason"] = "K线不足"
        return out

    try:
        highs = [float(k["high"]) for k in klines]
        lows = [float(k["low"]) for k in klines]
        closes = [float(k["close"]) for k in klines]
    except (KeyError, TypeError, ValueError):
        out["reason"] = "K线字段异常"
        return out

    rh = max(highs[-lb - 1 : -1])
    rl = min(lows[-lb - 1 : -1])
    up_th = rh * (1.0 + buf / 100.0)
    down_th = rl * (1.0 - buf / 100.0)
    out["range_high"] = round(rh, 8)
    out["range_low"] = round(rl, 8)
    out["up_threshold"] = round(up_th, 8)
    out["down_threshold"] = round(down_th, 8)

    use_rt = realtime_price is not None and float(realtime_price) > 0
    c = float(realtime_price) if use_rt else closes[-1]
    out["eval_price"] = round(c, 8)
    out["price_basis"] = "ticker" if use_rt else "last_close"
    pxn = "现价(ticker)" if use_rt else "收盘"

    tail_h = highs[-rev:]
    tail_l = lows[-rev:]

    if max(tail_h) > rh and c <= rh:
        out["mode"] = "false_break"
        out["direction"] = "up"
        out["reason"] = (
            f"近{rev}根曾刺破区间上沿 {rh:.6f}，{pxn} {c:.6f} 于上沿下方（假上破）"
        )
        return out
    if min(tail_l) < rl and c >= rl:
        out["mode"] = "false_break"
        out["direction"] = "down"
        out["reason"] = (
            f"近{rev}根曾刺破区间下沿 {rl:.6f}，{pxn} {c:.6f} 于下沿上方（假下破）"
        )
        return out

    if c > up_th:
        out["mode"] = "breakout"
        out["direction"] = "up"
        out["reason"] = (
            f"{pxn} {c:.6f} 站上突破线 {up_th:.6f}（区间高 {rh:.6f} +{buf}%）"
        )
        return out
    if c < down_th:
        out["mode"] = "breakout"
        out["direction"] = "down"
        out["reason"] = (
            f"{pxn} {c:.6f} 跌破突破线 {down_th:.6f}（区间低 {rl:.6f} -{buf}%）"
        )
        return out

    span = min(len(closes) - 2, max(rev * 3, lb))
    prev_closes = closes[-span - 1 : -1]
    had_up = any(x > up_th for x in prev_closes)
    had_down = any(x < down_th for x in prev_closes)

    if had_up and rh < c <= up_th and lows[-1] <= rh * (1.0 + buf / 100.0):
        out["mode"] = "retest_confirm"
        out["direction"] = "up"
        out["reason"] = (
            f"此前曾收上突破线 {up_th:.6f}，{pxn}回踩近上沿 {rh:.6f} 后为 {c:.6f}"
        )
        return out
    if (
        had_down
        and down_th < c < rl
        and highs[-1] >= rl * (1.0 - buf / 100.0)
    ):
        out["mode"] = "retest_confirm"
        out["direction"] = "down"
        out["reason"] = (
            f"此前曾跌破突破线 {down_th:.6f}，{pxn}回抽近下沿 {rl:.6f} 后为 {c:.6f}"
        )
        return out

    out["reason"] = "未触发（区间内或未满足回踩条件）"
    return out


def get_v313_decision_snapshot(
    force_refresh: bool = True, symbol: str = "SOL/USDT"
) -> Dict[str, Any]:
    _ensure_memos_hotfixes()
    ensure_trading_theory_library()
    snap = build_indicator_snapshot(symbol, 500)
    klines: List[Dict[str, Any]] = snap.get("klines") or []
    state = _state_slice_for_symbol(_load_state(), symbol)
    closes = [float(k["close"]) for k in klines]
    rsi_1m = 50.0
    if len(closes) >= 15:
        s = rsi_series(pd.Series(closes), 14)
        rsi_1m = float(s.iloc[-1]) if pd.notna(s.iloc[-1]) else 50.0
    t5 = _tf_trend_word(closes, 5)
    t15 = _tf_trend_word(closes, 15)
    t1h = _tf_trend_word(closes, 60)
    t4h = _tf_trend_word(closes, 240)
    ts_hi = 1 if t1h == "上涨" else (-1 if t1h == "下跌" else 0)
    ts_4h = 1 if t4h == "上涨" else (-1 if t4h == "下跌" else 0)
    trend_score = max(-1.0, min(1.0, (ts_hi + ts_4h) / 2))
    if t1h == "震荡" and t4h == "震荡":
        big_trend = "1H+4H 震荡"
    elif ts_hi >= 0 and ts_4h >= 0:
        big_trend = "1H+4H 多头趋势"
    elif ts_hi <= 0 and ts_4h <= 0:
        big_trend = "1H+4H 空头趋势"
    else:
        big_trend = "1H+4H 震荡"
    prob_up, prob_down = _calc_probs(rsi_1m, trend_score)
    patterns, fib_map = PatternRecognizer.merge_patterns(klines)
    pat_str = "、".join(patterns[:8]) if patterns else "无特殊形态"
    adv = _ADV_ENGINE.compute(symbol, klines)
    last_ts = int(klines[-1]["time"]) if klines else 0
    latest_bar_time = utc_ms_to_bj_str(last_ts) if last_ts else "—"
    cycle_judgment = f"5m={t5} | 15m={t15} | 1H={t1h} | 4H={t4h}"
    technical_indicators = f"RSI(1m)={rsi_1m:.1f} | K线形态={pat_str}"
    trend_status = f"1H+4H {big_trend.replace('1H+4H ', '')} | 资金健康：正常"
    entry = float(klines[-1]["close"]) if klines else 0.0
    score = 0.0
    st = adv.get("supertrend_pro", {}).get("dir", "")
    if st == "多头":
        score += 0.25
    elif st == "空头":
        score -= 0.25
    ema3 = adv.get("ema3_cross", "")
    if "多头" in ema3:
        score += 0.15
    if "空头" in ema3:
        score -= 0.15
    if "上破" in adv.get("sar_breaks", "") or "偏多" in adv.get("sar_breaks", ""):
        score += 0.1
    if "下破" in adv.get("sar_breaks", "") or "偏空" in adv.get("sar_breaks", ""):
        score -= 0.1
    if "翻多" in adv.get("macd", ""):
        score += 0.08
    if "翻空" in adv.get("macd", ""):
        score -= 0.08
    if rsi_1m < 35:
        score += 0.12
    if rsi_1m > 65:
        score -= 0.12
    if t5 == "上涨":
        score += 0.05
    if t5 == "下跌":
        score -= 0.05
    score = max(-1.0, min(1.0, score))
    post = beta_update_from_score_throttled(score)
    sig_label = _sig_label_from_rsi_t5(rsi_1m, t5)
    if score >= 0.45 and sig_label.startswith("偏多"):
        sig_label = "偏多（强）"
    elif score <= -0.45 and sig_label.startswith("偏空"):
        sig_label = "偏空（强）"
    elif score >= 0.45 and sig_label == "无":
        sig_label = "偏多（强）"
    elif score <= -0.45 and sig_label == "无":
        sig_label = "偏空（强）"
    sig_label_before_main_guard = sig_label
    btc_klines_guard: Optional[List[Dict[str, Any]]] = None
    if os.environ.get("LONGXIA_MAIN_BTC_ANCHOR_GUARD", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        try:
            if str(symbol).strip() == "BTC/USDT":
                btc_klines_guard = klines
            else:
                btc_klines_guard = (
                    build_indicator_snapshot("BTC/USDT", 500).get("klines") or []
                )
        except Exception:
            btc_klines_guard = None
    sig_label, guard_meta = apply_signal_guards(
        sig_label,
        klines=klines,
        t1h=t1h,
        t4h=t4h,
        closes=closes,
        btc_klines=btc_klines_guard,
    )
    rt_breakout: Optional[float] = None
    try:
        rt_breakout = float(_fetch_current_ticker_price_sync(symbol))
        if rt_breakout <= 0:
            rt_breakout = None
    except Exception:
        rt_breakout = None
    breakout = _breakout_trigger_state(klines, realtime_price=rt_breakout)
    sig_label = _apply_breakout_to_signal_label(sig_label, breakout)
    last_sig = int(state.get("last_sig", 0) or 0)
    if sig_label.startswith("偏空"):
        sl_price, tp1_price, tp2_price, tp3_price = _levels_for_direction(entry, "做空")
        dir_side = "做空"
    elif sig_label.startswith("偏多"):
        sl_price, tp1_price, tp2_price, tp3_price = _levels_for_direction(entry, "做多")
        dir_side = "做多"
    else:
        sl_price, tp1_price, tp2_price, tp3_price = _levels_for_direction(entry, "做多")
        dir_side = "做多"
    if dynamic_levels_enabled() and closes:
        sl_price, tp1_price, tp2_price, tp3_price = widen_levels_from_closes(
            entry, dir_side, (sl_price, tp1_price, tp2_price, tp3_price), closes
        )
    cooldown_left = "—"
    last_iso = state.get("last_signal_bar_iso")
    if last_iso and klines:
        try:
            sig_t = datetime.fromisoformat(str(last_iso).replace("Z", "+00:00"))
            last_bar_t = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
            bars = max(0, int((last_bar_t - sig_t).total_seconds() // 60))
            cooldown_left = str(max(0, 3 - (bars % 4)))
        except Exception:
            pass
    fib_note = ""
    if fib_map:
        fib_note = "斐波关键位已算 " + ",".join(f"{k}={v:.4f}" for k, v in list(fib_map.items())[:2])
    explain = (
        f"Super Trend Pro:{adv.get('supertrend_pro', dict()).get('dir', '—')} + "
        f"{adv.get('ema3_cross', '')} + {adv.get('sar_breaks', '')} + "
        f"{adv.get('order_blocks', '')} + 贝叶斯后验胜率{post*100:.1f}% ，"
        f"建议{sig_label}"
        + (f" + {fib_note}" if fib_note else "")
        + f" · {_rr_fee_hint(entry, sl_price, tp1_price, dir_side)}"
    )
    res_line = _resource_line()
    trend_status = trend_status + f" | 【资源】{res_line}"
    trend_status = trend_status + (
        f" | 机械触发:{breakout.get('mode', 'none')}/{breakout.get('direction', 'none')}"
    )
    sync_hint = "已同步（见 memos 钩子）"
    prob_model_line = (
        f"概率模型：上涨{prob_up}% | 下跌{prob_down}% | 【信号解读】{explain} | 【信号转单状态】{sync_hint}"
    )
    spot_price = _LT.fetch_current_ticker_price(symbol)
    futures_price = _LT.fetch_futures_ticker_price(symbol)
    ticker_lines_text = (
        f"实时成交价(CCXT ticker,Gate现货)：{spot_price} USDT\n"
        f"合约实时成交价（Gate永续）: {futures_price} USDT （与网页合约价一致，用于手动跟单）"
    )
    structure_guard_km = {
        "signal_label": sig_label,
        "prob_up_5m": prob_up,
        "prob_down_5m": prob_down,
        "rsi_1m": rsi_1m,
        "live_trading_state": state,
    }
    try:
        px_close = float(_fetch_current_ticker_price_sync(symbol))
        _sync_virtual_closeouts_for_price(
            px_close, symbol, decision=structure_guard_km
        )
    except Exception:
        if entry > 0:
            _sync_virtual_closeouts_for_price(
                float(entry), symbol, decision=structure_guard_km
            )
    books_ctx = _load_theory_books()
    theory_book_hints_text = _pick_theory_hints(symbol, rsi_1m, books_ctx)
    brain_meta: Dict[str, Any] = {}
    try:
        from utils.hft_skill_brain import snapshot_brain_meta

        brain_meta = snapshot_brain_meta()
    except Exception:
        pass
    ekm = experiment_km_for_bar(
        symbol,
        klines,
        closes,
        rsi_1m=rsi_1m,
        t5=t5,
        sig_label=sig_label_before_main_guard,
        score=score,
        prob_up=prob_up,
        prob_down=prob_down,
        markov_tracker=None,
        markov_template=None,
    )
    return {
        "symbol": symbol,
        "prediction_cycle": "下一根 5 分钟 K线",
        "latest_bar_time": latest_bar_time,
        "prob_up_5m": prob_up,
        "prob_down_5m": prob_down,
        "big_trend": big_trend,
        "cycle_judgment": f"周期判断：{cycle_judgment}",
        "technical_indicators": f"技术指标：{technical_indicators}",
        "trend_status": trend_status,
        "prob_model_line": prob_model_line,
        "rsi_1m": rsi_1m,
        "entry_price": entry,
        "sl_price": sl_price,
        "tp1_price": tp1_price,
        "tp2_price": tp2_price,
        "tp3_price": tp3_price,
        "signal_label": sig_label,
        "signal_label_before_main_guard": sig_label_before_main_guard,
        **guard_meta,
        "main_breakout_mode": str(breakout.get("mode") or "none"),
        "main_breakout_direction": str(breakout.get("direction") or "none"),
        "main_breakout_reason": str(breakout.get("reason") or ""),
        "main_breakout_up_threshold": breakout.get("up_threshold"),
        "main_breakout_down_threshold": breakout.get("down_threshold"),
        "main_breakout_range_high": breakout.get("range_high"),
        "main_breakout_range_low": breakout.get("range_low"),
        "main_breakout_eval_price": breakout.get("eval_price"),
        "main_breakout_price_basis": str(breakout.get("price_basis") or "last_close"),
        "cooldown_left": cooldown_left,
        "signals_today": state.get("signals_today", "—"),
        "last_signal_bar_iso": state.get("last_signal_bar_iso", "—"),
        "live_trading_state": state,
        "indicator_snapshot_meta": {
            "count": snap.get("count"),
            "source": snap.get("source"),
            "last_close": snap.get("last_close"),
            "fetched_at_ms": snap.get("fetched_at_ms"),
            "klines_fetch_mode": snap.get("klines_fetch_mode"),
            "klines_fetch_build": snap.get("klines_fetch_build"),
        },
        "candle_5m": _fetch_latest_5m_candle(symbol),
        "advanced_indicators": adv,
        "pattern_list": patterns,
        "fib_levels": fib_map,
        "consistency_score": score,
        "bayes_posterior_winrate": post,
        "signal_human_explain": explain,
        "resource_monitor": res_line,
        "virtual_order_status": sync_hint,
        "spot_ticker_price_str": spot_price,
        "futures_ticker_price_str": futures_price,
        "ticker_display_lines": ticker_lines_text,
        "theory_book_hints_text": theory_book_hints_text,
        **ekm,
        **brain_meta,
    }


def sync_virtual_memos_from_state(
    symbol: str,
    entry_price: float,
    *,
    decision: Optional[Dict[str, Any]] = None,
) -> None:
    """主观察池虚拟开单：与 `live_trading_state.json` 计数对齐，并用与决策页一致的 `signal_label` 生成 memos（含 score 强信号）。

    `decision` 应传入 `get_v313_decision_snapshot` 的返回值；若省略则仅按 RSI+5m 粗算标签（后台兜底），可能与页面不一致。
    Hook 按 **标的** 单独记 `signals_today_seen` / `last_virt_sig_key`，避免多币种共用根字段互相覆盖导致长时间不落新单。
    """
    _ensure_memos_hotfixes()
    try:
        ep = float(entry_price)
    except Exception:
        return
    if ep <= 0:
        return
    _sync_virtual_closeouts_for_price(ep, symbol, decision=decision)
    ensure_trading_theory_library()
    state = _state_slice_for_symbol(_load_state(), symbol)
    st_date = str(state.get("signals_date") or "")
    n = int(state.get("signals_today", 0) or 0)
    last_sig = int(state.get("last_sig", 0) or 0)
    hook: Dict[str, Any] = {}
    if _MEMOS_HOOK.exists():
        try:
            hook = json.loads(_MEMOS_HOOK.read_text(encoding="utf-8"))
        except Exception:
            hook = {}
    hook.setdefault("by_symbol", {})
    sym_hook: Dict[str, Any] = hook["by_symbol"].setdefault(symbol, {})
    if sym_hook.get("signals_date") != st_date:
        sym_hook["signals_date"] = st_date
        sym_hook["signals_today_seen"] = 0
        sym_hook["last_virt_sig_key"] = ""
    prev = int(sym_hook.get("signals_today_seen", 0) or 0)

    if decision is not None:
        sig_label = str(decision.get("signal_label") or "").strip() or "无"
    else:
        snap = build_indicator_snapshot(symbol, 500)
        klines = snap.get("klines") or []
        closes = [float(k["close"]) for k in klines]
        rsi_1m = 50.0
        if len(closes) >= 15:
            s = rsi_series(pd.Series(closes), 14)
            rsi_1m = float(s.iloc[-1]) if pd.notna(s.iloc[-1]) else 50.0
        t5 = _tf_trend_word(closes, 5)
        sig_label = _sig_label_from_rsi_t5(rsi_1m, t5)

    def _dir_from_sig(lb: str) -> str:
        if lb.startswith("偏多"):
            return "做多"
        if lb.startswith("偏空"):
            return "做空"
        return "模拟入场"

    virt_key = f"{st_date}|{symbol}|{sig_label}|{last_sig}"
    vdir = _dir_from_sig(sig_label)
    vblocked = virtual_open_blocked(_REPO_ROOT, symbol, vdir)
    sg_blocked = False
    if decision is not None and vdir in ("做多", "做空"):
        try:
            from utils.structure_guard import block_trend_chase_entry

            blocked, _br = block_trend_chase_entry(
                vdir, decision, None, experiment_track=False
            )
            if blocked:
                sg_blocked = True
        except Exception:
            pass
    if n > prev and not vblocked and not sg_blocked:
        delta = n - prev
        cap = _virtual_memos_max_catchup()
        if delta > cap:
            # 常见于：换日/新 hook、或首次同步时 prev=0 而 state 里 signals_today 已是全天累计，
            # 若按差值循环 append 会在同一 HTTP 请求内写入数百条同秒、同价记录。
            pass
        else:
            for _ in range(delta):
                _append_virtual_trade_memory_local(symbol, ep, vdir, last_sig)
    if (
        sig_label != "无"
        and sym_hook.get("last_virt_sig_key") != virt_key
        and not vblocked
        and not sg_blocked
    ):
        if n <= prev:
            _append_virtual_trade_memory_local(symbol, ep, vdir, last_sig)
    sym_hook["signals_today_seen"] = n
    sym_hook["last_virt_sig_key"] = virt_key
    _MEMOS_HOOK.write_text(json.dumps(hook, ensure_ascii=False, indent=2), encoding="utf-8")
def start_live_bot_background() -> None:
    ensure_trading_theory_library()
    _ensure_memos_hotfixes()
    _start_background_scan_thread_if_needed()


import sys

if "__main__" in sys.modules:
    # 不再覆盖 main.py 自定义的样本分轨预览函数。
    pass
_ensure_memos_hotfixes()

# === 热修复完成（语法错误已修复 + 三个小毛病一次性解决）===
# 1. f-string 括号不匹配问题已彻底修复
# 2. 近期memos原始样本现在最多显示30条
# 3. 今日模拟入场统计已实时同步
# 4. 已平仓检测 + 今日盈亏/胜率已实时更新（SL打到也会自动计数）
# 使用方法：替换服务器上的 live_trading.py 后，pkill -f live_trading.py && python3 live_trading.py 即可生效。

import builtins

builtins.trade_memory_preview_rows_html = trade_memory_preview_rows_html
_ensure_memos_hotfixes()
_ensure_memos_hotfixes()
_ensure_memos_hotfixes()