#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日策略复盘（第一版，可 cron）：
- 读取最新 backtest 矩阵报告（outputs/**/*_matrix_report.json，取 mtime 最新）
- 汇总 trade_memory：主观察池（virtual_signal）/ 规则实验轨；今日·昨日·近 7 日（北京日历）
- 核心 6 类指标：交易数、净胜率%、平均净盈亏%、净盈亏合计%、最大回撤%、Sharpe（净、按笔）
- 异常预警 + 小步调参建议（文案级，不自动改环境变量）
- 输出：outputs/daily_strategy_review/latest_daily_review.{json,md}
- 可选：对比上一份日报（若存在）

环境（可选）：
  LONGXIA_DAILY_REVIEW_TELEGRAM — 若设置且已配置项目内 Telegram 发送逻辑，可扩展推送（本版仅占位不调用）。
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

_BJ = ZoneInfo("Asia/Shanghai")
_FEE_PCT = 0.16  # 与决策页 memos 一致：主观察池双边合计 %
_REPO = Path(__file__).resolve().parent.parent
_OUT = _REPO / "outputs" / "daily_strategy_review"
_TM = _REPO / "trade_memory.json"


def _parse_trade_memory(raw: Any) -> List[dict]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("trades"), list):
        return [x for x in raw["trades"] if isinstance(x, dict)]
    return []


def _load_trades() -> List[dict]:
    if not _TM.exists():
        return []
    try:
        raw = json.loads(_TM.read_text(encoding="utf-8"))
    except Exception:
        return []
    return _parse_trade_memory(raw)


def _day_bj(r: dict) -> Optional[str]:
    ds = str(r.get("date") or "").strip()
    if len(ds) >= 10:
        return ds[:10]
    et = str(r.get("entry_time") or "").strip()
    if not et:
        return None
    try:
        s = et.replace("Z", "+00:00") if et.endswith("Z") else et
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(_BJ).strftime("%Y-%m-%d")
    except Exception:
        return None


def _net_profit(r: dict) -> float:
    g = float(r.get("profit") or 0)
    if r.get("virtual_signal"):
        return g - _FEE_PCT
    return g


def _sort_by_close(rows: List[dict]) -> List[dict]:
    def _k(x: dict) -> str:
        return str(x.get("close_time") or x.get("entry_time") or "")

    return sorted(rows, key=_k)


def _max_drawdown_net_pct(returns: List[float]) -> float:
    """按时间顺序累加净盈亏（百分点），相对峰值的最大回撤（百分点）。"""
    if not returns:
        return 0.0
    peak = 0.0
    eq = 0.0
    mdd = 0.0
    for r in returns:
        eq += r
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    return round(mdd, 4)


def _sharpe_net(returns: List[float]) -> Optional[float]:
    if len(returns) < 2:
        return None
    try:
        m = statistics.mean(returns)
        s = statistics.stdev(returns)
        if s < 1e-12:
            return None
        return round(m / s, 4)
    except Exception:
        return None


def _metrics_for_closed(rows: List[dict]) -> Dict[str, Any]:
    if not rows:
        return {
            "n_trades": 0,
            "win_rate_net_pct": None,
            "avg_net_profit_pct": None,
            "sum_net_profit_pct": None,
            "max_drawdown_net_pct": None,
            "sharpe_net": None,
        }
    nets = [_net_profit(r) for r in rows]
    wins = len([x for x in nets if x > 0])
    wr = round(wins / len(nets) * 100, 4)
    avg = round(sum(nets) / len(nets), 4)
    ssum = round(sum(nets), 4)
    ordered = _sort_by_close(rows)
    rets = [_net_profit(r) for r in ordered]
    mdd = _max_drawdown_net_pct(rets)
    sh = _sharpe_net(rets)
    return {
        "n_trades": len(rows),
        "win_rate_net_pct": wr,
        "avg_net_profit_pct": avg,
        "sum_net_profit_pct": ssum,
        "max_drawdown_net_pct": mdd,
        "sharpe_net": sh,
    }


def _closed_subset(
    trades: List[dict],
    *,
    virtual: Optional[bool],
    day: Optional[str] = None,
) -> List[dict]:
    out: List[dict] = []
    for r in trades:
        if r.get("profit") is None:
            continue
        if virtual is True and not r.get("virtual_signal"):
            continue
        if virtual is False and r.get("virtual_signal"):
            continue
        d = _day_bj(r)
        if day is not None and d != day:
            continue
        out.append(r)
    return out


def _closed_in_range(
    trades: List[dict], virtual: Optional[bool], start_day: str, end_day: str
) -> List[dict]:
    """含端点；按 date/entry 北京日筛选。"""
    out: List[dict] = []
    for r in trades:
        if r.get("profit") is None:
            continue
        if virtual is True and not r.get("virtual_signal"):
            continue
        if virtual is False and r.get("virtual_signal"):
            continue
        d = _day_bj(r)
        if d is None or d < start_day or d > end_day:
            continue
        out.append(r)
    return out


def _find_latest_matrix_report() -> Optional[Path]:
    root = _REPO / "outputs"
    if not root.exists():
        return None
    cands = list(root.rglob("*_matrix_report.json"))
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def _slim_matrix_report(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e)}
    rel = str(path.resolve().relative_to(_REPO))
    return {
        "path": rel,
        "generated_at_utc": data.get("generated_at_utc"),
        "profile": data.get("profile"),
        "mode_summary": data.get("mode_summary"),
        "template_summary": data.get("template_summary"),
        "vs_previous": data.get("vs_previous"),
    }


def _experiment_by_template(rows: List[dict]) -> Dict[str, Any]:
    """实验轨已平仓：按 markov_template 粗分桶（无字段则为 unknown）。"""
    buckets: Dict[str, List[dict]] = {}
    for r in rows:
        k = str(r.get("markov_template") or "").strip() or "unknown"
        buckets.setdefault(k, []).append(r)
    return {k: _metrics_for_closed(v) for k, v in sorted(buckets.items())}


def _risk_hint() -> Dict[str, Any]:
    p = _REPO / "logs" / "experiment_risk_state.json"
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _build_alerts(
    main_today: Dict[str, Any],
    main_y: Dict[str, Any],
    main_7d: Dict[str, Any],
    exp_today: Dict[str, Any],
    matrix: Dict[str, Any],
    risk: Dict[str, Any],
    prev: Optional[Dict[str, Any]],
) -> List[str]:
    alerts: List[str] = []
    if main_today.get("n_trades"):
        s = main_today.get("sum_net_profit_pct")
        if s is not None and float(s) < 0:
            alerts.append("【主观察池·今日】净盈亏合计为负，建议对照矩阵与盘口噪音。")
    pause_u = float(risk.get("pause_until_unix") or 0)
    if pause_u > datetime.now().timestamp():
        alerts.append("【实验轨风控】当前处于连亏暂停窗口内（见 logs/experiment_risk_state.json）。")
    vp = matrix.get("vs_previous") or {}
    bm = (vp.get("by_mode") or {}).get("experiment") or {}
    dsum = bm.get("avg_sum_profit_pct_delta")
    try:
        if dsum is not None and float(dsum) < -0.5:
            alerts.append("【矩阵】实验轨相对上期「平均合计盈亏%」下降较多，谨慎追参。")
    except (TypeError, ValueError):
        pass
    if prev:
        pt = (prev.get("main_track") or {}).get("today") or {}
        pwr = pt.get("win_rate_net_pct")
        cwr = main_today.get("win_rate_net_pct")
        try:
            if (
                pwr is not None
                and cwr is not None
                and main_today.get("n_trades", 0) >= 3
                and float(cwr) < float(pwr) - 25
            ):
                alerts.append("【主观察池】今日净胜率较前一日快照显著走低（样本足够时）。")
        except (TypeError, ValueError):
            pass
    if exp_today.get("n_trades") == 0 and (main_today.get("n_trades") or 0) > 10:
        alerts.append("【实验轨】今日无已平仓样本，而主池有成交：可检查筛选是否过紧。")
    return alerts


def _build_suggestions(
    main_7d: Dict[str, Any],
    exp_7d: Dict[str, Any],
    by_tpl: Dict[str, Any],
) -> List[str]:
    sug: List[str] = []
    mdd = main_7d.get("max_drawdown_net_pct")
    try:
        if mdd is not None and float(mdd) > 3.0:
            sug.append(
                "近 7 日主观察池净回撤（累计曲线）偏大：可考虑小幅收紧开仓频率或略放宽止损距离（二选一，勿同时大改）。"
            )
    except (TypeError, ValueError):
        pass
    sharpe = main_7d.get("sharpe_net")
    try:
        if sharpe is not None and float(sharpe) < 0:
            sug.append(
                "近 7 日净 Sharpe 为负：优先复盘时段/币种，再考虑微调 LONGXIA_KRONOS_MIN_PROB_EDGE（±10% 步长）。"
            )
    except (TypeError, ValueError):
        pass
    # 模板桶：找最差 sum_net
    worst = None
    for tpl, m in by_tpl.items():
        if tpl == "unknown":
            continue
        sm = m.get("sum_net_profit_pct")
        if sm is None:
            continue
        if worst is None or sm < worst[0]:
            worst = (sm, tpl)
    if worst and worst[0] < -1.0:
        sug.append(
            f"实验轨模板「{worst[1]}」近 7 日净合计偏弱：可单独收紧该模板阈值或减小该态仓位（小步）。"
        )
    if not exp_7d.get("n_trades"):
        sug.append("实验轨近 7 日无已平仓样本：维持观察或略放宽实验轨门槛以恢复统计效力。")
    sug.append(
        "调参铁律：一次只改 1～2 个参数；改动幅度约 10%～20%；至少观察 24h 再判；恶化则回滚。"
    )
    return sug


def _diff_line(prev_full: Optional[Dict[str, Any]], cur: Dict[str, Any], label: str) -> str:
    if not prev_full:
        return f"- {label}：首次生成基准。"
    pt = (prev_full.get("main_track") or {}).get("today") or {}
    keys = ("sum_net_profit_pct", "win_rate_net_pct", "n_trades")
    parts = []
    for k in keys:
        a, b = pt.get(k), cur.get(k)
        if a is not None and b is not None:
            try:
                parts.append(f"{k}: {float(a):.4f} → {float(b):.4f}")
            except (TypeError, ValueError):
                parts.append(f"{k}: {a} → {b}")
    return f"- {label}（主池·今日）" + ("：" + "；".join(parts) if parts else "：—")


def main() -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    hist = _OUT / "history"
    hist.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(ZoneInfo("UTC"))
    bj_today = now_utc.astimezone(_BJ).strftime("%Y-%m-%d")
    bj_yesterday = (now_utc.astimezone(_BJ) - timedelta(days=1)).strftime("%Y-%m-%d")
    bj_7_start = (now_utc.astimezone(_BJ) - timedelta(days=6)).strftime("%Y-%m-%d")

    prev_path = _OUT / "latest_daily_review.json"
    prev: Optional[Dict[str, Any]] = None
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text(encoding="utf-8"))
        except Exception:
            prev = None

    trades = _load_trades()

    main_today = _metrics_for_closed(_closed_subset(trades, virtual=True, day=bj_today))
    main_y = _metrics_for_closed(_closed_subset(trades, virtual=True, day=bj_yesterday))
    main_7d = _metrics_for_closed(
        _closed_in_range(trades, True, bj_7_start, bj_today)
    )

    exp_today = _metrics_for_closed(_closed_subset(trades, virtual=False, day=bj_today))
    exp_y = _metrics_for_closed(_closed_subset(trades, virtual=False, day=bj_yesterday))
    exp_7d = _metrics_for_closed(
        _closed_in_range(trades, False, bj_7_start, bj_today)
    )
    exp_7d_rows = _closed_in_range(trades, False, bj_7_start, bj_today)
    by_tpl = _experiment_by_template(exp_7d_rows)

    mpath = _find_latest_matrix_report()
    matrix = _slim_matrix_report(mpath) if mpath else {"path": None, "note": "未找到矩阵报告"}
    risk = _risk_hint()

    alerts = _build_alerts(
        main_today, main_y, main_7d, exp_today, matrix, risk, prev
    )
    suggestions = _build_suggestions(main_7d, exp_7d, by_tpl)

    payload: Dict[str, Any] = {
        "generated_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bj_calendar_date": bj_today,
        "trade_memory_path": str(_TM.relative_to(_REPO)) if _TM.exists() else None,
        "matrix_report": matrix,
        "experiment_risk_state": {
            "pause_until_unix": risk.get("pause_until_unix"),
            "day_pnl_pct": risk.get("day_pnl_pct"),
        },
        "main_track": {
            "today": main_today,
            "yesterday": main_y,
            "last_7d": main_7d,
        },
        "experiment_track": {
            "today": exp_today,
            "yesterday": exp_y,
            "last_7d": exp_7d,
            "last_7d_by_markov_template": by_tpl,
        },
        "alerts": alerts,
        "suggestions": suggestions,
        "vs_previous_snapshot": _diff_line(prev, main_today, "相对上一日报")
        if prev
        else None,
        "audit": {
            "note": "本报告为只读建议；参数变更请人工改环境变量并重启进程，并自行留痕。",
        },
    }

    latest_j = _OUT / "latest_daily_review.json"
    latest_j.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    hist_f = hist / f"review_{bj_today}.json"
    hist_f.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        f"# 每日策略复盘 · {bj_today}（北京日期）",
        "",
        f"- 生成（UTC）：`{payload['generated_at_utc']}`",
        f"- 矩阵报告：`{matrix.get('path') or '—'}`",
        "",
        f"## 一、主观察池（virtual · 净口径含双边 {_FEE_PCT}%）",
        "",
        "### 今日",
        f"| 指标 | 值 |",
        f"| --- | --- |",
        f"| 交易数 | {main_today.get('n_trades')} |",
        f"| 净胜率% | {main_today.get('win_rate_net_pct')} |",
        f"| 平均净盈亏% | {main_today.get('avg_net_profit_pct')} |",
        f"| 净盈亏合计% | {main_today.get('sum_net_profit_pct')} |",
        f"| 最大回撤%（净累计曲线） | {main_today.get('max_drawdown_net_pct')} |",
        f"| Sharpe（净·按笔） | {main_today.get('sharpe_net')} |",
        "",
        "### 昨日",
        f"| 交易数 | {main_y.get('n_trades')} | 净胜率% | {main_y.get('win_rate_net_pct')} | 净合计% | {main_y.get('sum_net_profit_pct')} |",
        "",
        "### 近 7 日",
        f"| 交易数 | {main_7d.get('n_trades')} | 净胜率% | {main_7d.get('win_rate_net_pct')} | 净合计% | {main_7d.get('sum_net_profit_pct')} | 回撤% | {main_7d.get('max_drawdown_net_pct')} | Sharpe | {main_7d.get('sharpe_net')} |",
        "",
        "## 二、规则实验轨（非 virtual · 净=记录 profit%）",
        "",
        f"- 今日：笔数 {exp_today.get('n_trades')} · 净胜率% {exp_today.get('win_rate_net_pct')} · 净合计% {exp_today.get('sum_net_profit_pct')}",
        f"- 近 7 日：笔数 {exp_7d.get('n_trades')} · 净胜率% {exp_7d.get('win_rate_net_pct')} · 净合计% {exp_7d.get('sum_net_profit_pct')}",
        "",
        "## 三、异常预警",
        "",
    ]
    if alerts:
        for a in alerts:
            md_lines.append(f"- {a}")
    else:
        md_lines.append("- （暂无规则命中）")
    md_lines.extend(
        [
            "",
            "## 四、小步调参建议（只读）",
            "",
        ]
    )
    for s in suggestions:
        md_lines.append(f"- {s}")
    md_lines.extend(["", "---", "*由 scripts/daily_strategy_review.py 自动生成*"])

    latest_md = _OUT / "latest_daily_review.md"
    latest_md.write_text("\n".join(md_lines), encoding="utf-8")

    print(json.dumps({"ok": True, "json": str(latest_j), "md": str(latest_md)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
