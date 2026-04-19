#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EverOS 只读 PoC（Phase 1）：从 trade_memory.json 抽取近期已平仓样本，生成结构化 case / skill 草案。

- 只读 JSON，不写回 trade_memory、不接交易所、不参与下单与页面路由。
- 输出目录默认：仓库根下 outputs/everos_poc/（目录常被 .gitignore，适合本地/备份机落盘）。

用法：
  python3 scripts/everos_poc_memory_sync.py
  python3 scripts/everos_poc_memory_sync.py --days 14 --memory /path/to/trade_memory.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

_BJ = ZoneInfo("Asia/Shanghai")
_REPO = Path(__file__).resolve().parents[1]


def _parse_memory(raw: Any) -> Tuple[List[dict], Dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)], {}
    if isinstance(raw, dict) and isinstance(raw.get("trades"), list):
        env = {k: v for k, v in raw.items() if k != "trades"}
        return [x for x in raw["trades"] if isinstance(x, dict)], env
    return [], {}


def _parse_close_iso(s: object) -> Optional[datetime]:
    t = str(s or "").strip()
    if not t or t == "—":
        return None
    try:
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _pool_label(t: dict) -> str:
    """主观察池虚拟单带 virtual_signal=True；实验轨 evolution 落库通常不带或为 false。"""
    if t.get("virtual_signal") is True:
        return "main_virtual"
    return "experiment"


def _case_quality(profit: Optional[float]) -> int:
    if profit is None:
        return 0
    try:
        p = float(profit)
    except Exception:
        return 0
    if p > 0:
        return min(100, int(50 + min(3.0, p) * 16))
    if p < 0:
        return max(0, int(50 + max(-3.0, p) * 16))
    return 50


def _intent_text(t: dict) -> str:
    sym = str(t.get("symbol") or "—")
    d = str(t.get("direction") or "—")
    cr = str(t.get("close_reason") or "—")
    tpl = str(t.get("markov_template") or "").strip()
    tail = f" · 模板={tpl}" if tpl else ""
    return f"{sym} {d} 平仓原因={cr}{tail}"


def _failure_or_fix(t: dict) -> Tuple[str, str]:
    try:
        p = float(t.get("profit") or 0.0)
    except Exception:
        p = 0.0
    cr = str(t.get("close_reason") or "—")
    if p < 0:
        return "亏损平仓", f"关注触发价与{cr}；复盘当时波动与信号一致性"
    if cr in ("SL", "BE"):
        return "止损/保本离场", "若频繁触及，考虑放宽入场或收紧周期噪声"
    if cr.startswith("TP"):
        return "止盈路径兑现", "记录有利环境下的共性（标的/时段）"
    return "其他", "—"


def _build_cases(rows: List[dict], *, limit: int) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for i, t in enumerate(rows[:limit]):
        ft, fix = _failure_or_fix(t)
        cases.append(
            {
                "case_id": f"case_{i+1:04d}",
                "symbol": str(t.get("symbol") or "—"),
                "direction": str(t.get("direction") or "—"),
                "pool": _pool_label(t),
                "signal_track": str(t.get("signal_track") or "").strip() or None,
                "close_reason": str(t.get("close_reason") or "—"),
                "profit_pct": t.get("profit"),
                "intent_summary": _intent_text(t),
                "outcome_tag": ft,
                "suggested_followup": fix,
                "quality_score_0_100": _case_quality(
                    float(t["profit"]) if t.get("profit") is not None else None
                ),
                "entry_time": t.get("entry_time"),
                "close_time": t.get("close_time"),
            }
        )
    return cases


def _skill_key(symbol: str, close_reason: str) -> str:
    cr = close_reason or "—"
    return f"{symbol}|{cr}"


def _build_skills(rows: List[dict], *, top_n: int) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[float]] = {}
    for t in rows:
        sym = str(t.get("symbol") or "—")
        cr = str(t.get("close_reason") or "—")
        try:
            p = float(t.get("profit") or 0.0)
        except Exception:
            p = 0.0
        k = _skill_key(sym, cr)
        buckets.setdefault(k, []).append(p)

    skills: List[Dict[str, Any]] = []
    for k, profits in buckets.items():
        sym, cr = k.split("|", 1)
        n = len(profits)
        wins = sum(1 for x in profits if x > 0)
        avg = sum(profits) / n if n else 0.0
        maturity = min(100, int(n * 8 + wins / max(n, 1) * 40))
        skills.append(
            {
                "skill_id": f"sk_{k.replace('/', '_').replace('|', '_')}",
                "symbol": sym,
                "close_reason_bucket": cr,
                "sample_n": n,
                "win_rate_pct": round(wins / n * 100.0, 2) if n else 0.0,
                "avg_profit_pct": round(avg, 4),
                "sop_draft": f"在 {sym} 上 {cr} 结局样本 {n} 笔：胜率约 {wins}/{n}，均盈亏 {avg:.3f}%（仅统计，非交易指令）",
                "maturity_0_100": maturity,
            }
        )
    skills.sort(key=lambda x: (-x["sample_n"], -abs(x["avg_profit_pct"])))
    return skills[:top_n]


def _md_report(
    meta: Dict[str, Any], cases: List[dict], skills: List[dict]
) -> str:
    lines = [
        "# EverOS PoC 记忆同步（只读）",
        "",
        f"- 生成时间（北京）：{meta.get('generated_at_bj')}",
        f"- 源文件：{meta.get('source_file')}",
        f"- 窗口：近 {meta.get('days')} 天 · 已平仓 {meta.get('n_closed_in_window')} 笔",
        "",
        "## Cases（摘录）",
        "",
    ]
    for c in cases[:30]:
        lines.append(
            f"- **{c['case_id']}** [{c['pool']}] {c['symbol']} {c['direction']} "
            f"p={c['profit_pct']}% · {c['close_reason']} · Q={c['quality_score_0_100']}"
        )
        lines.append(f"  - 意图：{c['intent_summary']}")
        lines.append(f"  - 跟进：{c['suggested_followup']}")
    lines.extend(["", "## Skills（按 标的+平仓原因 聚合，草案）", ""])
    for s in skills[:25]:
        lines.append(
            f"- **{s['symbol']} / {s['close_reason_bucket']}**：n={s['sample_n']} "
            f"win%={s['win_rate_pct']} avg={s['avg_profit_pct']}% · {s['sop_draft'][:120]}…"
        )
    lines.extend(
        [
            "",
            "---",
            "*本文件由脚本自动生成，仅供研究归档；不构成交易建议。*",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="EverOS PoC：trade_memory → 结构化 JSON/MD")
    ap.add_argument(
        "--memory",
        type=Path,
        default=_REPO / "trade_memory.json",
        help="trade_memory.json 路径",
    )
    ap.add_argument("--days", type=int, default=7, help="近 N 天（按 UTC 日切 close_time）")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_REPO / "outputs" / "everos_poc",
        help="输出目录",
    )
    ap.add_argument("--case-limit", type=int, default=200, help="最多导出 case 条数")
    ap.add_argument("--skill-top", type=int, default=40, help="skill 草案最多条数")
    args = ap.parse_args()

    mem_path: Path = args.memory
    if not mem_path.is_file():
        print(f"[everos_poc] 跳过：未找到 {mem_path}")
        return

    raw = json.loads(mem_path.read_text(encoding="utf-8"))
    trades, env = _parse_memory(raw)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(1, int(args.days)))

    closed: List[dict] = []
    for t in trades:
        if t.get("profit") is None:
            continue
        ct = _parse_close_iso(t.get("close_time"))
        if ct is None:
            continue
        if ct < cutoff:
            continue
        closed.append(t)

    closed.sort(key=lambda x: _parse_close_iso(x.get("close_time")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    cases = _build_cases(closed, limit=int(args.case_limit))
    skills = _build_skills(closed, top_n=int(args.skill_top))

    generated_bj = datetime.now(_BJ).strftime("%Y-%m-%d %H:%M:%S %Z")
    meta = {
        "generated_at_bj": generated_bj,
        "source_file": str(mem_path.resolve()),
        "days": int(args.days),
        "n_total_trades": len(trades),
        "n_closed_in_window": len(closed),
        "schema": "everos_poc_memory_v1",
    }

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "meta": meta,
        "cases": cases,
        "skills": skills,
        "envelope_note": {k: env[k] for k in sorted(env.keys())[:20]} if env else {},
    }

    jp = out_dir / "latest_everos_poc_memory.json"
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    mp = out_dir / "latest_everos_poc_memory.md"
    mp.write_text(_md_report(meta, cases, skills), encoding="utf-8")

    print(
        f"[everos_poc] 已写入 {jp} / {mp} · 窗口内已平仓 {len(closed)} 笔 · cases={len(cases)} skills={len(skills)}"
    )


if __name__ == "__main__":
    main()
