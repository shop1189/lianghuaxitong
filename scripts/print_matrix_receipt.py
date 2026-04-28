#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 *_matrix_summary.json 生成云端「最短回执」正文（stdout）。"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
from pathlib import Path
from typing import Any, List


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _pick_summary_json(out_dir: Path) -> Path:
    pats = sorted(out_dir.glob("*matrix_summary.json"))
    if not pats:
        raise SystemExit(f"no *matrix_summary.json under {out_dir}")
    return pats[-1]


def _git_sha(repo: Path) -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                text=True,
            ).strip()
        )
    except Exception:
        return os.environ.get("BACKTEST_GIT_SHA", "unknown")


def _aggregate_main(rows: List[dict[str, Any]]) -> dict[str, Any]:
    mains = [r for r in rows if str(r.get("level_mode") or "") == "main"]
    n = sum(int(r.get("total_trades") or 0) for r in mains)
    sum_net = sum(float(r.get("sum_net_profit_pct") or 0) for r in mains)
    tw = 0
    wsum = 0.0
    for r in mains:
        t = int(r.get("total_trades") or 0)
        if not t:
            continue
        v = r.get("net_win_rate")
        if v is None:
            v = r.get("win_rate_net_pct")
        tw += t
        wsum += t * float(v or 0)
    wnr = wsum / tw if tw else 0.0
    mdd = max((float(r.get("max_drawdown_net_pct") or 0) for r in mains), default=0.0)
    return {
        "main_cells": len(mains),
        "total_trades": n,
        "trade_weighted_net_win_rate_pct": round(wnr, 4),
        "sum_net_profit_pct": round(sum_net, 2),
        "max_drawdown_net_pct": round(mdd, 2),
    }


def _coinglass_notes_scan(rows: List[dict[str, Any]]) -> list[str]:
    bad: list[str] = []
    for r in rows:
        cg = r.get("coinglass_score_nudge") or {}
        notes = cg.get("notes") or []
        if not isinstance(notes, list):
            continue
        for n in notes:
            s = str(n)
            if "ImportError" in s or "import error" in s.lower():
                bad.append(s)
    return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, help="矩阵输出目录（取其中最新 *matrix_summary.json）")
    ap.add_argument("--matrix-json", type=Path, help="直接指定 matrix_summary.json")
    ap.add_argument(
        "--matrix-dir-relative",
        type=str,
        default="",
        help="写入回执中的 matrix_dir（默认用 out-dir 相对仓库根）",
    )
    args = ap.parse_args()
    repo = _repo_root()
    if args.matrix_json:
        jpath = args.matrix_json.resolve()
    elif args.out_dir:
        jpath = _pick_summary_json(args.out_dir.resolve())
    else:
        ap.error("需要 --out-dir 或 --matrix-json")

    rows = json.loads(jpath.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise SystemExit("matrix_summary 为空或格式错误")

    agg = _aggregate_main(rows)
    rel_dir = args.matrix_dir_relative.strip()
    if not rel_dir:
        try:
            rel_dir = str(jpath.parent.relative_to(repo))
        except ValueError:
            rel_dir = str(jpath.parent)

    sha = _git_sha(repo)
    cg_bad = _coinglass_notes_scan(rows)
    notes = []
    if agg["total_trades"] <= 0:
        notes.append("main total_trades 为 0，请检查数据/参数。")
    if cg_bad:
        notes.append("coinglass_score_nudge 含 ImportError 类说明，请检查依赖/导入。")
    if not notes:
        notes.append("matrix ok; coinglass nudge notes 无 ImportError。")

    print(f"git_sha: {sha}")
    print(f"matrix_dir: {rel_dir}")
    print("level_mode: main")
    print("symbols: SOL,BTC,ETH,DOGE,XRP,BNB")
    print("cooldowns: cd3,cd6")
    print("param_profile: B (EDGE=3, MIN_SCORE=0.35, REQUIRE_STRONG=0)")
    print(f"sum_net_profit_pct (main cells sum): {agg['sum_net_profit_pct']}")
    print(f"trade_weighted net_win_rate: {agg['trade_weighted_net_win_rate_pct']}")
    print(f"max_drawdown_net_pct (worst main cell): {agg['max_drawdown_net_pct']}")
    print(f"main_sample_trades (sum total_trades): {agg['total_trades']}")
    print(f"matrix_summary_json: {jpath.name}")
    print(f"notes: {'; '.join(notes)}")


if __name__ == "__main__":
    main()
