#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段 A 最小闭环回测（V3.18.0+）：
- 数据：Gate.io / CCXT（data_fetcher.fetch_ohlcv，与线上一致）
- 平仓：utils.trade_exit_rules.first_exit_tick（同源）；bar 内用 OHLC 保守判定
- SL/TP：复用 live_trading._levels_for_direction（main）/ _experiment_levels_for_direction（experiment）
- 入场：与决策页同一套轻量信号核（RSI + 多周期 trend 词 + AdvancedIndicatorEngine 计分 → 强/轻标签）

输出：trades.csv + summary.json（默认 outputs/backtest/）
净口径：单笔净盈亏% = 毛盈亏% − 双边手续费（默认 0.16%，与主系统文案一致）。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from data_fetcher import fetch_ohlcv
from indicator_upgrade import AdvancedIndicatorEngine, rsi as rsi_series
from live_trading import (
    _calc_probs,
    _experiment_entry_filter,
    _experiment_mode_normalized,
    _experiment_levels_for_direction,
    _levels_for_direction,
    _sig_label_from_rsi_t5,
    _tf_trend_word,
    beta_posterior_mean_for_replay_bar,
    experiment_km_for_bar,
)
from utils.market_regime_state import RegimeMarkovTracker
from utils.trade_exit_rules import first_exit_tick

_REPO = Path(__file__).resolve().parent
_ADV = AdvancedIndicatorEngine(max_bars=300)
# 与 live_trading 手续费口径一致（双边合计百分点）
_BACKTEST_FEE_PCT = 0.16


def _trade_stats_extended(trades: List[Dict[str, Any]], fee_pct: float = _BACKTEST_FEE_PCT) -> Dict[str, Any]:
    """毛/净胜率、净盈亏汇总、净值简单回撤、逐笔净收益 Sharpe（样本内）。"""
    if not trades:
        return {
            "win_rate_gross_pct": 0.0,
            "win_rate_net_pct": 0.0,
            "avg_net_profit_pct": 0.0,
            "sum_net_profit_pct": 0.0,
            "max_drawdown_net_pct": 0.0,
            "sharpe_net": 0.0,
        }
    gross = [float(t["profit_pct"]) for t in trades]
    nets = [g - fee_pct for g in gross]
    n = len(trades)
    wins_g = sum(1 for g in gross if g > 0)
    wins_n = sum(1 for x in nets if x > 0)
    wr_g = round(wins_g / n * 100, 2)
    wr_n = round(wins_n / n * 100, 2)
    avg_net = round(sum(nets) / n, 4)
    sum_net = round(sum(nets), 4)
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in nets:
        eq += x
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
    max_dd = round(max_dd, 4)
    if len(nets) > 1:
        m = statistics.mean(nets)
        s = statistics.stdev(nets)
        sharpe = round(m / s * (len(nets) ** 0.5), 4) if s > 1e-12 else 0.0
    else:
        sharpe = 0.0
    return {
        "win_rate_gross_pct": wr_g,
        "win_rate_net_pct": wr_n,
        "avg_net_profit_pct": avg_net,
        "sum_net_profit_pct": sum_net,
        "max_drawdown_net_pct": max_dd,
        "sharpe_net": sharpe,
    }


def _ohlcv_to_klines(rows: List[List[Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ts, o, h, l, c, v in rows:
        out.append(
            {
                "time": int(ts),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(v),
            }
        )
    return out


def _compute_sig_label_like_v313(
    symbol: str, klines: List[Dict[str, Any]], closes: List[float]
) -> str:
    """与 get_v313 信号标签同构（略去贝叶斯节流，仅用于回测标签）。"""
    rsi_1m = 50.0
    if len(closes) >= 15:
        s = rsi_series(pd.Series(closes), 14)
        rsi_1m = float(s.iloc[-1]) if pd.notna(s.iloc[-1]) else 50.0
    t5 = _tf_trend_word(closes, 5)
    adv = _ADV.compute(symbol, klines)
    score = 0.0
    st = adv.get("supertrend_pro", {}).get("dir", "")
    if st == "多头":
        score += 0.25
    elif st == "空头":
        score -= 0.25
    ema3 = adv.get("ema3_cross", "")
    if "多头" in str(ema3):
        score += 0.15
    if "空头" in str(ema3):
        score -= 0.15
    if "上破" in str(adv.get("sar_breaks", "")) or "偏多" in str(adv.get("sar_breaks", "")):
        score += 0.1
    if "下破" in str(adv.get("sar_breaks", "")) or "偏空" in str(adv.get("sar_breaks", "")):
        score -= 0.1
    if "翻多" in str(adv.get("macd", "")):
        score += 0.08
    if "翻空" in str(adv.get("macd", "")):
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
    sig_label = _sig_label_from_rsi_t5(rsi_1m, t5)
    if score >= 0.45 and sig_label.startswith("偏多"):
        sig_label = "偏多（强）"
    elif score <= -0.45 and sig_label.startswith("偏空"):
        sig_label = "偏空（强）"
    elif score >= 0.45 and sig_label == "无":
        sig_label = "偏多（强）"
    elif score <= -0.45 and sig_label == "无":
        sig_label = "偏空（强）"
    return sig_label


def _experiment_km_for_backtest_bar(
    symbol: str,
    klines: List[Dict[str, Any]],
    closes: List[float],
    *,
    markov_tracker: RegimeMarkovTracker,
    markov_template: str,
    use_markov_threshold_template: bool = False,
) -> Dict[str, Any]:
    """构造实验轨 bar 快照（experiment_km_for_bar + Markov 内存 tracker，不写 logs）。

    入场是否通过由 :func:`live_trading._experiment_entry_filter` 按
    ``LONGXIA_EXPERIMENT_MODE``（legacy / kronos_light / …）判定，与线上一致；
    勿在此处假定始终使用 kronos_light 门槛。
    """
    rsi_1m = 50.0
    if len(closes) >= 15:
        s = rsi_series(pd.Series(closes), 14)
        rsi_1m = float(s.iloc[-1]) if pd.notna(s.iloc[-1]) else 50.0
    t5 = _tf_trend_word(closes, 5)
    t1h = _tf_trend_word(closes, 60)
    t4h = _tf_trend_word(closes, 240)
    ts_hi = 1 if t1h == "上涨" else (-1 if t1h == "下跌" else 0)
    ts_4h = 1 if t4h == "上涨" else (-1 if t4h == "下跌" else 0)
    trend_score = max(-1.0, min(1.0, (ts_hi + ts_4h) / 2))
    prob_up, prob_down = _calc_probs(rsi_1m, trend_score)
    adv = _ADV.compute(symbol, klines)
    score = 0.0
    st = adv.get("supertrend_pro", {}).get("dir", "")
    if st == "多头":
        score += 0.25
    elif st == "空头":
        score -= 0.25
    ema3 = adv.get("ema3_cross", "")
    if "多头" in str(ema3):
        score += 0.15
    if "空头" in str(ema3):
        score -= 0.15
    if "上破" in str(adv.get("sar_breaks", "")) or "偏多" in str(adv.get("sar_breaks", "")):
        score += 0.1
    if "下破" in str(adv.get("sar_breaks", "")) or "偏空" in str(adv.get("sar_breaks", "")):
        score -= 0.1
    if "翻多" in str(adv.get("macd", "")):
        score += 0.08
    if "翻空" in str(adv.get("macd", "")):
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
    sig_label = _sig_label_from_rsi_t5(rsi_1m, t5)
    if score >= 0.45 and sig_label.startswith("偏多"):
        sig_label = "偏多（强）"
    elif score <= -0.45 and sig_label.startswith("偏空"):
        sig_label = "偏空（强）"
    elif score >= 0.45 and sig_label == "无":
        sig_label = "偏多（强）"
    elif score <= -0.45 and sig_label == "无":
        sig_label = "偏空（强）"
    return experiment_km_for_bar(
        symbol,
        klines,
        closes,
        rsi_1m=rsi_1m,
        t5=t5,
        sig_label=sig_label,
        score=score,
        prob_up=prob_up,
        prob_down=prob_down,
        markov_tracker=markov_tracker,
        markov_template=markov_template,
        force_markov_threshold_template=use_markov_threshold_template,
    )


def first_exit_ohlc(
    direction: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
    o: float,
    h: float,
    l: float,
    c: float,
) -> Optional[Tuple[str, float, float]]:
    """
    单根 K 内按 SL→TP3→TP2→TP1 与 first_exit_tick 一致；用 high/low 保守触发价。
    """
    d = str(direction or "")
    if d == "模拟入场":
        d = "做多"
    e, s, a, b, t3p = float(entry), float(sl), float(tp1), float(tp2), float(tp3)
    if d == "做多":
        if l <= s:
            hit = first_exit_tick(d, e, s, a, b, t3p, s)
            return (hit[0], hit[1], s) if hit else None
        if h >= t3p:
            hit = first_exit_tick(d, e, s, a, b, t3p, t3p)
            return (hit[0], hit[1], t3p) if hit else None
        if h >= b:
            hit = first_exit_tick(d, e, s, a, b, t3p, b)
            return (hit[0], hit[1], b) if hit else None
        if h >= a:
            hit = first_exit_tick(d, e, s, a, b, t3p, a)
            return (hit[0], hit[1], a) if hit else None
    elif d == "做空":
        if h >= s:
            hit = first_exit_tick(d, e, s, a, b, t3p, s)
            return (hit[0], hit[1], s) if hit else None
        if l <= t3p:
            hit = first_exit_tick(d, e, s, a, b, t3p, t3p)
            return (hit[0], hit[1], t3p) if hit else None
        if l <= b:
            hit = first_exit_tick(d, e, s, a, b, t3p, b)
            return (hit[0], hit[1], b) if hit else None
        if l <= a:
            hit = first_exit_tick(d, e, s, a, b, t3p, a)
            return (hit[0], hit[1], a) if hit else None
    return None


def _direction_from_sig(sig: str) -> Optional[str]:
    if sig.startswith("偏多"):
        return "做多"
    if sig.startswith("偏空"):
        return "做空"
    return None


def run_backtest(args: argparse.Namespace) -> Tuple[Path, Path]:
    symbol = args.symbol.strip()
    rows = fetch_ohlcv(symbol, timeframe=args.timeframe, limit=int(args.limit))
    if len(rows) < 80:
        raise SystemExit("K 线过少，请增大 --limit")

    warmup = 60
    klines_full = _ohlcv_to_klines(rows)
    closes_full = [float(r[4]) for r in rows]

    pos: Optional[Dict[str, Any]] = None
    last_exit_i = -10**9
    trades: List[Dict[str, Any]] = []

    level_mode = args.level_mode.strip().lower()
    if level_mode not in ("main", "experiment"):
        raise SystemExit("--level-mode 须为 main 或 experiment")

    cooldown = int(args.entry_cooldown)
    max_hold = int(args.max_hold_bars)
    markov_tpl = str(getattr(args, "markov_template", "off") or "off").strip().lower()
    if markov_tpl not in ("off", "strict_chop", "balanced"):
        markov_tpl = "off"
    markov_tracker: Optional[RegimeMarkovTracker] = (
        RegimeMarkovTracker() if level_mode == "experiment" else None
    )
    use_tpl = bool(getattr(args, "use_markov_threshold_template", False))
    last_exp_entry_ms = 0
    # 与 get_v313_decision_snapshot 一致：legacy 等过滤依赖 bayes_posterior_winrate；仅用内存状态，不写 bayes_beta_state.json
    bayes_replay_st: Dict[str, Any] = {"alpha": 2.0, "beta": 2.0, "last_update_ts": -1e30}

    for i in range(warmup, len(rows)):
        ts, o, h, l, c, _v = rows[i]
        o, h, l, c = float(o), float(h), float(l), float(c)
        t_ms = int(ts)

        if pos is not None:
            entry_i = int(pos["entry_i"])
            held = i - entry_i
            direction = str(pos["direction"])
            sl = float(pos["sl"])
            tp1 = float(pos["tp1"])
            tp2 = float(pos["tp2"])
            tp3 = float(pos["tp3"])
            entry_px = float(pos["entry"])

            ex: Optional[Tuple[str, float, float]] = None
            if held >= max_hold:
                hit = first_exit_tick(direction, entry_px, sl, tp1, tp2, tp3, c)
                if hit:
                    ex = (hit[0], hit[1], c)
                else:
                    if direction == "做多":
                        pnl = round((c / entry_px - 1) * 100, 2)
                    else:
                        pnl = round((entry_px - c) / entry_px * 100, 2)
                    ex = ("timeout", pnl, c)
            else:
                ex = first_exit_ohlc(direction, entry_px, sl, tp1, tp2, tp3, o, h, l, c)

            if ex is not None:
                bracket, pnl, fill = ex[0], ex[1], ex[2]
                trades.append(
                    {
                        "entry_time_ms": pos["entry_time_ms"],
                        "exit_time_ms": t_ms,
                        "direction": direction,
                        "entry": entry_px,
                        "exit": float(fill),
                        "bracket": bracket,
                        "profit_pct": float(pnl),
                    }
                )
                pos = None
                last_exit_i = i
            continue

        if i - last_exit_i < cooldown:
            continue

        sub_k = klines_full[: i + 1]
        sub_c = closes_full[: i + 1]
        km_bar: Optional[Dict[str, Any]] = None
        if level_mode == "experiment":
            assert markov_tracker is not None
            km_bar = _experiment_km_for_backtest_bar(
                symbol,
                sub_k,
                sub_c,
                markov_tracker=markov_tracker,
                markov_template=markov_tpl,
                use_markov_threshold_template=use_tpl,
            )
            sc = float(km_bar.get("consistency_score") or 0.0)
            km_bar["bayes_posterior_winrate"] = beta_posterior_mean_for_replay_bar(
                sc, t_ms / 1000.0, bayes_replay_st
            )
            if not _experiment_entry_filter(km_bar):
                continue
            if km_bar.get("experiment_markov_template_enabled"):
                mf = float(km_bar.get("experiment_markov_max_frequency_sec") or 0.0)
                if mf > 0 and (t_ms - last_exp_entry_ms) < mf * 1000:
                    continue
            sig = str(km_bar.get("signal_label") or "")
            want = _direction_from_sig(sig)
            if want is None:
                continue
        else:
            sig = _compute_sig_label_like_v313(symbol, sub_k, sub_c)
            want = _direction_from_sig(sig)
            if want is None:
                continue

        if args.require_strong and ("（强）" not in sig):
            continue

        entry_px = c
        if level_mode == "experiment":
            sl, tp1, tp2, tp3 = _experiment_levels_for_direction(entry_px, want)
        else:
            sl, tp1, tp2, tp3 = _levels_for_direction(entry_px, want)

        pos = {
            "entry_i": i,
            "entry_time_ms": t_ms,
            "direction": want,
            "entry": entry_px,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "signal_label": sig,
        }
        if km_bar and km_bar.get("experiment_markov_template_enabled"):
            mf = float(km_bar.get("experiment_markov_max_frequency_sec") or 0.0)
            if mf > 0:
                last_exp_entry_ms = t_ms

    if pos is not None:
        ts, _o, _h, _l, c, _v = rows[-1]
        c = float(c)
        direction = str(pos["direction"])
        entry_px = float(pos["entry"])
        sl, tp1, tp2, tp3 = float(pos["sl"]), float(pos["tp1"]), float(pos["tp2"]), float(pos["tp3"])
        hit = first_exit_tick(direction, entry_px, sl, tp1, tp2, tp3, c)
        if hit:
            trades.append(
                {
                    "entry_time_ms": pos["entry_time_ms"],
                    "exit_time_ms": int(ts),
                    "direction": direction,
                    "entry": entry_px,
                    "exit": c,
                    "bracket": hit[0],
                    "profit_pct": float(hit[1]),
                }
            )

    prefix = args.out_prefix or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sym_safe = symbol.replace("/", "-")
    out_dir = (Path(args.out_dir) if Path(args.out_dir).is_absolute() else _REPO / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    mtag = "" if (level_mode != "experiment" or markov_tpl == "off") else f"_mt{markov_tpl}"
    mtpl = "_mtpl1" if (level_mode == "experiment" and use_tpl) else ""
    stem = f"{prefix}_{sym_safe}_{level_mode}_cd{cooldown}{mtag}{mtpl}"

    csv_path = out_dir / f"{stem}_trades.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "entry_time_ms",
                "exit_time_ms",
                "direction",
                "entry",
                "exit",
                "bracket",
                "profit_pct",
            ],
        )
        w.writeheader()
        for t in trades:
            w.writerow(t)

    total = len(trades)
    wins = len([x for x in trades if float(x["profit_pct"]) > 0])
    losses = total - wins
    wr = round(wins / total * 100, 2) if total else 0.0
    sum_pnl = round(sum(float(x["profit_pct"]) for x in trades), 4)
    brackets: Dict[str, int] = {}
    for t in trades:
        b = str(t.get("bracket") or "")
        brackets[b] = brackets.get(b, 0) + 1

    ext = _trade_stats_extended(trades)
    summary = {
        "symbol": symbol,
        "timeframe": args.timeframe,
        "limit": int(args.limit),
        "level_mode": level_mode,
        "experiment_mode": _experiment_mode_normalized()
        if level_mode == "experiment"
        else "n/a",
        "markov_template": markov_tpl if level_mode == "experiment" else "n/a",
        "use_markov_threshold_template": bool(use_tpl) if level_mode == "experiment" else False,
        "markov_optimized": "1" if (level_mode == "experiment" and use_tpl) else "0",
        "entry_cooldown_bars": cooldown,
        "max_hold_bars": max_hold,
        "require_strong": bool(args.require_strong),
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": wr,
        "sum_profit_pct": sum_pnl,
        "brackets": brackets,
        **ext,
    }
    try:
        summary["trades_csv"] = str(csv_path.relative_to(_REPO))
    except ValueError:
        summary["trades_csv"] = str(csv_path)
    json_path = out_dir / f"{stem}_summary.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return csv_path, json_path


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="阶段 A 同源规则 bar 回放回测")
    p.add_argument("--symbol", default="SOL/USDT")
    p.add_argument("--timeframe", default="1m")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--level-mode", choices=("main", "experiment"), default="experiment")
    p.add_argument("--entry-cooldown", type=int, default=3)
    p.add_argument("--max-hold-bars", type=int, default=120)
    p.add_argument(
        "--require-strong",
        action="store_true",
        help="仅当信号标签含「强」时开仓（更贴近 kronos_light 实验轨门槛）",
    )
    p.add_argument("--out-dir", default="outputs/backtest")
    p.add_argument("--out-prefix", default="", help="文件名前缀（默认 UTC 时间戳）")
    p.add_argument(
        "--markov-template",
        default="off",
        choices=("off", "strict_chop", "balanced"),
        help="实验轨 Markov 阈值模板（仅 level-mode=experiment；回测用内存转移，不写 logs）",
    )
    p.add_argument(
        "--use-markov-threshold-template",
        action="store_true",
        help="实验轨：按当前 chop/mid/trend 启用策略层阈值模板（与 LONGXIA_USE_MARKOV_THRESHOLD_TEMPLATE=1 对齐）",
    )
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    os.chdir(_REPO)
    run_backtest(args)


if __name__ == "__main__":
    main()
