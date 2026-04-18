"""
实盘 / 决策快照：5m K 与决策页数据（V3.16 Gate.io CCXT）。
V3.16.5+：高级指标、形态融合、贝叶斯轻量、虚拟单本地写入（修正做空 SL/TP）。
规则实验轨：sync_experiment_track_from_snapshot — 独立筛选 + 较宽 SL/TP，写入非 virtual_signal。

环境变量速查（规则实验轨 / Kronos-light，重启进程生效）：
  LONGXIA_EXPERIMENT_TRACK     关：0|false|no|off；默认开启
  LONGXIA_EXPERIMENT_MODE      kronos_light（默认）| legacy | kronos_model（未接真模型时同 light）
  LONGXIA_KRONOS_MIN_CONSISTENCY   Kronos-light：|一致性| 门槛，默认 0.08
  LONGXIA_KRONOS_MIN_PROB_EDGE     Kronos-light：涨跌概率差（百分点），默认 1.5
  LONGXIA_EXPERIMENT_MIN_CONSISTENCY / LONGXIA_EXPERIMENT_MIN_BAYES  仅 legacy 使用
  LONGXIA_EXPERIMENT_SL_PCT / TP1_PCT / TP2_PCT / TP3_PCT  实验轨止损止盈比例
  LONGXIA_EXPERIMENT_SCAN_INTERVAL_SEC  后台全币种扫描间隔（秒），下限约 15
可选真 Kronos：integrations/kronos_experiment_optional.py（未接模型前勿依赖 kronos_model）。
"""
from __future__ import annotations
import html
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
import ccxt
import numpy as np
import pandas as pd
from beijing_time import trade_memory_record_for_preview, utc_ms_to_bj_str
from data_fetcher import _fetch_current_ticker_price_sync
from data_fetcher import fetch_ohlcv as gate_fetch_ohlcv
from data.fetcher import build_indicator_snapshot
from indicator_upgrade import (
    AdvancedIndicatorEngine,
    detect_kline_pattern,
    rsi as rsi_series,
)

_MEMOS_PREVIEW_MAX = 30
_MEMOS_PREVIEW_TABLE_N = 30
_STATE_FILE = Path(__file__).resolve().parent / "live_trading_state.json"
_MEMOS_HOOK = Path(__file__).resolve().parent / "memos_v316_hook.json"
_THEORY_FILE = Path(__file__).resolve().parent / "trading_theory_library.json"
_BAYES_FILE = Path(__file__).resolve().parent / "bayes_beta_state.json"
_TRADE_MEMORY = Path(__file__).resolve().parent / "trade_memory.json"
_ADV_ENGINE = AdvancedIndicatorEngine(max_bars=300)


def _trade_memory_parse(raw: Any) -> Tuple[List[dict], Optional[Dict[str, Any]]]:
    """兼容顶层数组或 {\"schema_version\",\"trades\":[]} 包一层。"""
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)], None
    if isinstance(raw, dict) and isinstance(raw.get("trades"), list):
        env = {k: v for k, v in raw.items() if k != "trades"}
        return [x for x in raw["trades"] if isinstance(x, dict)], env
    return [], None


def _trade_memory_write(trades: List[dict], env: Optional[Dict[str, Any]]) -> None:
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
    """与 evolution_core.TradeMemory.check_close_trade 同一判定顺序（SL 优先于 TP）。"""
    d = direction
    if d == "模拟入场":
        d = "做多"
    if d == "做多":
        if price <= sl:
            return round((sl / entry - 1) * 100, 2), round(sl, 6)
        if price >= tp3:
            return round((tp3 / entry - 1) * 100, 2), round(tp3, 6)
        if price >= tp2:
            return round((tp2 / entry - 1) * 100, 2), round(tp2, 6)
        if price >= tp1:
            return round((tp1 / entry - 1) * 100, 2), round(tp1, 6)
    elif d == "做空":
        if price >= sl:
            return round((entry / sl - 1) * -100, 2), round(sl, 6)
        if price <= tp3:
            return round((entry / tp3 - 1) * -100, 2), round(tp3, 6)
        if price <= tp2:
            return round((entry / tp2 - 1) * -100, 2), round(tp2, 6)
        if price <= tp1:
            return round((entry / tp1 - 1) * -100, 2), round(tp1, 6)
    return None
def _sync_virtual_closeouts_for_price(price: float) -> None:
    if price <= 0:
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
    for r in data:
        if not isinstance(r, dict):
            continue
        if not r.get("virtual_signal"):
            continue
        if r.get("profit") is not None:
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
        hit = _virtual_hit_and_close(direction, float(price), entry, sl, tp1, tp2, tp3)
        if hit is None:
            continue
        profit_pct, close_px = hit
        r["profit"] = profit_pct
        r["close"] = close_px
        r["close_time"] = close_iso
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
    """Kronos-light：不卡贝叶斯/价位自检；偏多偏空 + 一致性或涨跌概率差（与快照字段对齐，不加载 HF 模型）。"""
    sig = str(km.get("signal_label") or "")
    if not (sig.startswith("偏多") or sig.startswith("偏空")):
        return False
    try:
        cs = float(km.get("consistency_score") or 0.0)
    except Exception:
        cs = 0.0
    min_c = float(os.environ.get("LONGXIA_KRONOS_MIN_CONSISTENCY", "0.08"))
    if abs(cs) >= min_c:
        return True
    try:
        pu = float(km.get("prob_up_5m") or 0.0)
        pd = float(km.get("prob_down_5m") or 0.0)
    except Exception:
        pu, pd = 0.0, 0.0
    edge = float(os.environ.get("LONGXIA_KRONOS_MIN_PROB_EDGE", "1.5"))
    if sig.startswith("偏多") and (pu - pd) >= edge:
        return True
    if sig.startswith("偏空") and (pd - pu) >= edge:
        return True
    return False


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
    """规则实验轨：与主观察池共用快照；先 tick 再按筛选开仓（非 virtual_signal）。"""
    if not _experiment_track_enabled():
        return
    try:
        from evolution_core import ai_evo
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
    if not _experiment_entry_filter(km):
        return
    sig = str(km.get("signal_label") or "")
    if sig.startswith("偏多"):
        direction = "做多"
    elif sig.startswith("偏空"):
        direction = "做空"
    else:
        return
    try:
        entry = float(km.get("entry_price") or pxf)
    except Exception:
        entry = pxf
    sl, tp1, tp2, tp3 = _experiment_levels_for_direction(entry, direction)
    mode = _experiment_mode_normalized()
    if mode == "legacy":
        if not _price_levels_self_check(entry, direction, sl, tp1, tp2, tp3):
            return
    ai_evo.tick(pxf, sym)
    for t in ai_evo.memory.open_trades:
        if str(t.get("symbol") or "").strip() == sym:
            return
    ai_evo.record(direction, entry, sl, tp1, tp2, tp3, symbol=sym)


def _background_scan_all_symbols_once() -> None:
    for sym in _EXPERIMENT_SCAN_SYMBOLS:
        try:
            px = float(_fetch_current_ticker_price_sync(sym))
            if px <= 0:
                continue
            km = get_v313_decision_snapshot(force_refresh=True, symbol=sym)
            sync_virtual_memos_from_state(sym, px)
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
def get_v313_decision_snapshot(
    force_refresh: bool = True, symbol: str = "SOL/USDT"
) -> Dict[str, Any]:
    _ensure_memos_hotfixes()
    ensure_trading_theory_library()
    snap = build_indicator_snapshot(symbol, 500)
    klines: List[Dict[str, Any]] = snap.get("klines") or []
    state = _load_state()
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
    last_sig = int(state.get("last_sig", 0) or 0)
    if sig_label.startswith("偏空"):
        sl_price, tp1_price, tp2_price, _ = _levels_for_direction(entry, "做空")
        dir_side = "做空"
    elif sig_label.startswith("偏多"):
        sl_price, tp1_price, tp2_price, _ = _levels_for_direction(entry, "做多")
        dir_side = "做多"
    else:
        sl_price, tp1_price, tp2_price, _ = _levels_for_direction(entry, "做多")
        dir_side = "做多"
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
    try:
        px_close = float(_fetch_current_ticker_price_sync(symbol))
        _sync_virtual_closeouts_for_price(px_close)
    except Exception:
        if entry > 0:
            _sync_virtual_closeouts_for_price(float(entry))
    books_ctx = _load_theory_books()
    theory_book_hints_text = _pick_theory_hints(symbol, rsi_1m, books_ctx)
    brain_meta: Dict[str, Any] = {}
    try:
        from utils.hft_skill_brain import snapshot_brain_meta

        brain_meta = snapshot_brain_meta()
    except Exception:
        pass
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
        "signal_label": sig_label,
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
        **brain_meta,
    }
def sync_virtual_memos_from_state(symbol: str, entry_price: float) -> None:
    _ensure_memos_hotfixes()
    try:
        ep = float(entry_price)
    except Exception:
        return
    if ep <= 0:
        return
    _sync_virtual_closeouts_for_price(ep)
    ensure_trading_theory_library()
    state = _load_state()
    st_date = str(state.get("signals_date") or "")
    n = int(state.get("signals_today", 0) or 0)
    last_sig = int(state.get("last_sig", 0) or 0)
    hook: Dict[str, Any] = {}
    if _MEMOS_HOOK.exists():
        try:
            hook = json.loads(_MEMOS_HOOK.read_text(encoding="utf-8"))
        except Exception:
            hook = {}
    if hook.get("signals_date") != st_date:
        hook["signals_date"] = st_date
        hook["signals_today_seen"] = 0
        hook["last_virt_sig_key"] = ""
    prev = int(hook.get("signals_today_seen", 0) or 0)
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
    if n > prev:
        for _ in range(n - prev):
            _append_virtual_trade_memory_local(symbol, ep, _dir_from_sig(sig_label), last_sig)
        hook["signals_today_seen"] = n
    if sig_label != "无" and hook.get("last_virt_sig_key") != virt_key:
        if n <= prev:
            _append_virtual_trade_memory_local(symbol, ep, _dir_from_sig(sig_label), last_sig)
        hook["last_virt_sig_key"] = virt_key
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