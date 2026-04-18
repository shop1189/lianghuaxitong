#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段 A 回测矩阵：批量调用仓库根目录 backtest.py，汇总 summary.json，
并生成 matrix_summary.csv/json 与 matrix_report.json（供前端 memos 区块展示）。
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parent.parent


def _run_one(
    *,
    symbol: str,
    timeframe: str,
    limit: int,
    level_mode: str,
    entry_cooldown: int,
    max_hold_bars: int,
    require_strong: bool,
    out_dir: Path,
    prefix: str,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(_REPO / "backtest.py"),
        "--symbol",
        symbol,
        "--timeframe",
        timeframe,
        "--limit",
        str(limit),
        "--level-mode",
        level_mode,
        "--entry-cooldown",
        str(entry_cooldown),
        "--max-hold-bars",
        str(max_hold_bars),
        "--out-dir",
        str(out_dir),
        "--out-prefix",
        prefix,
    ]
    if require_strong:
        cmd.append("--require-strong")
    subprocess.run(cmd, cwd=str(_REPO), check=True)
    stem = f"{prefix}_{symbol.replace('/', '-')}_{level_mode}_cd{entry_cooldown}"
    return out_dir / f"{stem}_summary.json"


def _load_summary(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _build_report(rows: List[Dict[str, Any]], min_trades: int) -> Dict[str, Any]:
    by_mode: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        m = str(r.get("level_mode") or "")
        if m:
            by_mode[m].append(r)

    def _avg_mode(mode: str, key: str) -> float:
        xs = by_mode.get(mode) or []
        if not xs:
            return 0.0
        return sum(float(x.get(key) or 0) for x in xs) / len(xs)

    mode_summary: Dict[str, Any] = {}
    for mode in ("experiment", "main"):
        xs = by_mode.get(mode) or []
        mode_summary[mode] = {
            "runs": len(xs),
            "avg_total_trades": round(_avg_mode(mode, "total_trades"), 4),
            "avg_win_rate_pct": round(_avg_mode(mode, "win_rate_pct"), 4),
            "avg_sum_profit_pct": round(_avg_mode(mode, "sum_profit_pct"), 4),
        }

    best_by_symbol: Dict[str, Any] = {}
    by_sym: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if int(r.get("total_trades") or 0) < min_trades:
            continue
        by_sym[str(r.get("symbol") or "")].append(r)

    for sym, xs in by_sym.items():
        if not sym:
            continue
        best = max(
            xs,
            key=lambda x: (
                float(x.get("win_rate_pct") or 0),
                float(x.get("total_trades") or 0),
                float(x.get("sum_profit_pct") or 0),
            ),
        )
        best_by_symbol[sym] = best

    exp_vs_main: List[Dict[str, Any]] = []
    groups: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for r in rows:
        if int(r.get("total_trades") or 0) < min_trades:
            continue
        key = (
            r.get("symbol"),
            r.get("timeframe"),
            r.get("limit"),
            r.get("entry_cooldown_bars"),
            r.get("max_hold_bars"),
            r.get("require_strong"),
        )
        g = groups.setdefault(key, {})
        g[str(r.get("level_mode"))] = r

    for key, g in groups.items():
        if "experiment" in g and "main" in g:
            e, m = g["experiment"], g["main"]
            exp_vs_main.append(
                {
                    "symbol": key[0],
                    "timeframe": key[1],
                    "limit": key[2],
                    "entry_cooldown_bars": key[3],
                    "max_hold_bars": key[4],
                    "require_strong": key[5],
                    "exp_trades": e.get("total_trades"),
                    "main_trades": m.get("total_trades"),
                    "trade_delta": int(e.get("total_trades") or 0)
                    - int(m.get("total_trades") or 0),
                    "exp_win_rate": e.get("win_rate_pct"),
                    "main_win_rate": m.get("win_rate_pct"),
                    "win_rate_delta": round(
                        float(e.get("win_rate_pct") or 0)
                        - float(m.get("win_rate_pct") or 0),
                        4,
                    ),
                    "exp_sum_pnl": e.get("sum_profit_pct"),
                    "main_sum_pnl": m.get("sum_profit_pct"),
                }
            )

    def _score(x: Dict[str, Any]) -> float:
        tr = int(x.get("total_trades") or 0)
        wr = float(x.get("win_rate_pct") or 0)
        return wr * (1.0 + min(50, tr) ** 0.5)

    top_candidates = sorted(
        [r for r in rows if int(r.get("total_trades") or 0) >= min_trades],
        key=_score,
        reverse=True,
    )[:24]

    return {
        "mode_summary": mode_summary,
        "best_by_symbol": best_by_symbol,
        "exp_vs_main_same_setting": exp_vs_main,
        "top_candidates": top_candidates,
    }


def _vs_previous_in_dir(out_dir: Path, current_report_path: Path) -> Optional[Dict[str, Any]]:
    """与同一 out_dir 内上一份 matrix_report 对比（用于看单量/胜率/合计是否突变）。"""
    reports = sorted(
        out_dir.glob("*_matrix_report.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if len(reports) < 2:
        return None
    if reports[0].resolve() != current_report_path.resolve():
        return None
    prev_path = reports[1]
    try:
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
        cur = json.loads(current_report_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    prev_ms = prev.get("mode_summary") or {}
    cur_ms = cur.get("mode_summary") or {}
    by_mode: Dict[str, Any] = {}
    for mode in ("experiment", "main"):
        p = prev_ms.get(mode) or {}
        c = cur_ms.get(mode) or {}
        by_mode[mode] = {
            "avg_total_trades_delta": round(
                float(c.get("avg_total_trades") or 0)
                - float(p.get("avg_total_trades") or 0),
                4,
            ),
            "avg_win_rate_pct_delta": round(
                float(c.get("avg_win_rate_pct") or 0)
                - float(p.get("avg_win_rate_pct") or 0),
                4,
            ),
            "avg_sum_profit_pct_delta": round(
                float(c.get("avg_sum_profit_pct") or 0)
                - float(p.get("avg_sum_profit_pct") or 0),
                4,
            ),
        }
    return {
        "previous_report": prev_path.name,
        "previous_generated_at_utc": prev.get("generated_at_utc"),
        "by_mode": by_mode,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--symbols",
        default="SOL/USDT,BTC/USDT",
        help="逗号分隔",
    )
    p.add_argument("--timeframes", default="1m")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--level-modes", default="experiment,main")
    p.add_argument("--entry-cooldowns", default="3,8")
    p.add_argument("--max-hold-bars", type=int, default=120)
    p.add_argument(
        "--require-strong",
        action="store_true",
        help="传给 backtest.py（全矩阵统一）",
    )
    p.add_argument("--out-dir", default="outputs/backtest_matrix")
    p.add_argument("--min-trades-report", type=int, default=3)
    args = p.parse_args()

    prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = (_REPO / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    tfs = [s.strip() for s in args.timeframes.split(",") if s.strip()]
    modes = [s.strip() for s in args.level_modes.split(",") if s.strip()]
    cds = [int(s.strip()) for s in args.entry_cooldowns.split(",") if s.strip()]

    summaries: List[Path] = []
    for sym in symbols:
        for tf in tfs:
            for lm in modes:
                for cd in cds:
                    summaries.append(
                        _run_one(
                            symbol=sym,
                            timeframe=tf,
                            limit=args.limit,
                            level_mode=lm,
                            entry_cooldown=cd,
                            max_hold_bars=args.max_hold_bars,
                            require_strong=args.require_strong,
                            out_dir=out_dir,
                            prefix=prefix,
                        )
                    )

    rows = [_load_summary(x) for x in summaries]
    csv_path = out_dir / f"{prefix}_matrix_summary.csv"
    if rows:
        keys = list(rows[0].keys())
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow(r)

    json_path = out_dir / f"{prefix}_matrix_summary.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    report_core = _build_report(rows, min_trades=args.min_trades_report)
    report = {
        "generated_at_utc": prefix,
        "min_trades_report": args.min_trades_report,
        "matrix_summary_json": str(json_path.relative_to(_REPO)),
        "profile": "lite" if "lite" in str(out_dir) else ("full" if "full" in str(out_dir) else ""),
        **report_core,
    }
    report_path = out_dir / f"{prefix}_matrix_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    delta = _vs_previous_in_dir(out_dir, report_path)
    if delta:
        report["vs_previous"] = delta
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"matrix_summary": str(json_path), "matrix_report": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()
