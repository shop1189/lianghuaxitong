"""
Web / 服务入口：V3.17.0 全中文仪表盘 · /decision（V3.14 规则信号块第一版样式 + memos + 北京时间）。
对外引擎版本见 ENGINE_VERSION 与 GET /api/version。
"""
from __future__ import annotations

import html
import json
from typing import Any, List, Optional
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from data_fetcher import fetch_current_ticker_price, fetch_ticker, log_v317_engine_ready

log_v317_engine_ready()

# 与 Hermes / 监控对齐的对外版本号（仅标识，不改变交易逻辑）
ENGINE_VERSION = "V3.17.0"

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import uvicorn

from data.fetcher import build_indicator_snapshot
from data_upgrade import get_fear_greed
from beijing_time import utc_ms_to_bj_str
from live_trading import (
    _trade_memory_parse,
    get_v313_decision_snapshot,
    sync_experiment_track_from_snapshot,
    sync_virtual_memos_from_state,
)

SYMBOL_CHOICES = (
    "SOL/USDT",
    "BTC/USDT",
    "ETH/USDT",
    "DOGE/USDT",
    "XRP/USDT",
    "BNB/USDT",
)

MEMOS_BANNER = (
    "系统已开启全自动 memos 模拟记录与自我进化（开平仓与统计均由程序自动完成，您无需手动操作）"
)


def _pick_symbol(raw: str) -> str:
    s = (raw or "SOL/USDT").strip()
    return s if s in SYMBOL_CHOICES else "SOL/USDT"


def _top_entry_strip(active: str, symbol: str = "SOL/USDT") -> str:
    """子页面顶栏：返回决策页 / 样本 / 实盘（与第二次改版横幅内链接一致）。"""
    sym = _pick_symbol(symbol)
    qsym = quote(sym, safe="")

    def _a(href: str, label: str, key: str) -> str:
        cls = "top-entry top-entry-active" if active == key else "top-entry"
        return f'<a class="{cls}" href="{href}">{html.escape(label)}</a>'

    return f"""<div class="top-entry-strip">
{_a(f"/decision?symbol={qsym}", "决策看板", "decision")}
{_a("/memos_samples", "memos 原始样本", "memos")}
{_a("/live_state", "实盘状态", "live")}
</div>"""


_MEMOS_FEE_PCT = 0.16  # 展示用：双边手续费合计 %（与页面说明一致）
_BJ = ZoneInfo("Asia/Shanghai")


def _iso_to_bj_display(iso: object) -> str:
    """表格内：转为北京时间 YYYY-MM-DD HH:MM:SS（无时区后缀）。"""
    if iso is None:
        return "—"
    s = str(iso).strip()
    if not s or s == "—":
        return "—"
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_BJ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return s[:19] if len(s) >= 19 else s


def _fib_source_snippet(r: dict) -> str:
    ls = (r.get("levels_source") or "").strip()
    bits: list[str] = []
    if ls:
        bits.append(ls)
    for k, lab in (
        ("fib_0_618", "0.618"),
        ("fib_1_618_up", "1.618_up"),
        ("fib_1_618_down", "1.618_down"),
    ):
        v = r.get(k)
        if v is not None:
            try:
                bits.append(f"{lab}={float(v):.6g}")
            except Exception:
                bits.append(f"{lab}={v}")
    return " | ".join(bits) if bits else "—"


def _rr_gross_net_str(r: dict) -> str:
    """以 TP1 与 SL 相对入场距离估算 RR（毛/净），无数据时显示 —。"""
    try:
        e = float(r.get("entry", 0))
        sl = float(r.get("sl", 0))
        tp1 = float(r.get("tp1", 0))
        if e <= 0:
            return "—"
        risk = abs(e - sl) / e * 100
        rew = abs(tp1 - e) / e * 100
        if risk < 1e-9:
            return "—"
        g = rew / risk
        n = max(0.0, g - _MEMOS_FEE_PCT / max(risk, 1e-9))
        return f"{g:.2f}/{n:.2f}"
    except Exception:
        return "—"


def _infer_close_reason_from_levels(r: dict) -> str:
    """与 live_trading._virtual_hit_and_close 判定顺序一致（SL 优先于 TP3/TP2/TP1）。"""
    try:
        c = float(r.get("close"))
    except (TypeError, ValueError):
        return ""
    d = str(r.get("direction") or "做多")
    if d == "模拟入场":
        d = "做多"
    try:
        sl = float(r["sl"])
        tp1 = float(r["tp1"])
        tp2 = float(r["tp2"])
        tp3 = float(r["tp3"])
    except Exception:
        return ""
    if d == "做多":
        if c <= sl:
            return "SL"
        if c >= tp3:
            return "TP3"
        if c >= tp2:
            return "TP2"
        if c >= tp1:
            return "TP1"
    elif d == "做空":
        if c >= sl:
            return "SL"
        if c <= tp3:
            return "TP3"
        if c <= tp2:
            return "TP2"
        if c <= tp1:
            return "TP1"
    return ""


def _result_cn(r: dict) -> str:
    if r.get("profit") is None:
        return "未平"
    cr = str(r.get("close_reason") or "").strip()
    if cr not in ("TP1", "TP2", "TP3", "SL"):
        cr = _infer_close_reason_from_levels(r)
    try:
        pnl = float(r.get("profit") or 0)
    except (TypeError, ValueError):
        pnl = 0.0
    # 亏损单不应显示为止盈（推断价与字段偶发不一致时）
    if pnl < 0 and cr in ("TP1", "TP2", "TP3"):
        cr = "SL"
    if cr in ("TP1", "TP2", "TP3"):
        return f"止盈·{cr}"
    if cr == "SL":
        return "止损·SL"
    return "—"


def _fmt_pct(v: object, digits: int = 4) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):+.{digits}f}"
    except Exception:
        return "—"


def _load_trades_flat() -> list[dict]:
    p = Path(__file__).resolve().parent / "trade_memory.json"
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows, _ = _trade_memory_parse(raw)
    return [r for r in rows if isinstance(r, dict)]


def _reflection_experiment(exp_closed: list[dict]) -> str:
    if not exp_closed:
        return "【规则实验轨】样本不足，建议继续积累已平仓记录后再评估过拟合与门槛。"
    wins = len([r for r in exp_closed if float(r.get("profit") or 0) > 0])
    wr = round(wins / len(exp_closed) * 100, 2)
    if wr >= 55:
        return "【规则实验轨】总胜率偏高，注意过拟合；可适度收紧开仓条件或拉长冷却间隔。"
    if wr >= 45:
        return "【规则实验轨】胜率处于中性区间，建议继续积累 memos 样本，并观察多空分布与时段规律。"
    return "【规则实验轨】近期胜率偏低，建议结合大周期趋势与冷却节奏，避免在震荡区间反复试错。"


def _memos_reflect_bar_html() -> str:
    """首页靠前展示：换日说明 + 反思建议（与下方 memos 统计同源）。"""
    try:
        trades = _load_trades_flat()
        exp_closed = [
            r
            for r in trades
            if not r.get("virtual_signal") and r.get("profit") is not None
        ]
        text = _reflection_experiment(exp_closed)
    except Exception:
        text = "【规则实验轨】反思建议加载失败。"
    return f"""<div class="memos-day-meta">
<span>换日清空当日列表</span>
<span>约每 45 秒更新（随决策页加载刷新）</span>
</div>
<div class="reflect reflect-home">
<b>反思建议：</b>{html.escape(text)}
</div>"""


def _memos_evolution_full_html(trades: list[dict], today_bj: str) -> str:
    """第二次改版：反思置顶 + 双轨指标 + 仅当日宽表 + 脚注（不附带原始 JSON 块）。"""
    exp = [r for r in trades if not r.get("virtual_signal")]
    vir = [r for r in trades if r.get("virtual_signal")]
    exp_closed = [r for r in exp if r.get("profit") is not None]
    vir_closed = [r for r in vir if r.get("profit") is not None]
    vir_open = [r for r in vir if r.get("profit") is None]

    exp_today = [r for r in exp if r.get("date") == today_bj]
    exp_today_closed = [r for r in exp_closed if r.get("date") == today_bj]
    vir_today = [r for r in vir if r.get("date") == today_bj]
    vir_today_closed = [r for r in vir_closed if r.get("date") == today_bj]
    vir_today_open = [r for r in vir_open if r.get("date") == today_bj]

    def _win_rate_pct(rows: list[dict]) -> str:
        if not rows:
            return "—"
        w = len([r for r in rows if float(r.get("profit") or 0) > 0])
        return f"{round(w / len(rows) * 100, 2)}%"

    def _long_short_wr(rows: list[dict]) -> tuple[str, str]:
        longs = [r for r in rows if str(r.get("direction", "")).startswith("做多")]
        shorts = [r for r in rows if str(r.get("direction", "")).startswith("做空")]
        lw = len([r for r in longs if float(r.get("profit") or 0) > 0])
        sw = len([r for r in shorts if float(r.get("profit") or 0) > 0])
        lwr = f"{round(lw / len(longs) * 100, 2)}%" if longs else "—"
        swr = f"{round(sw / len(shorts) * 100, 2)}%" if shorts else "—"
        return lwr, swr

    # —— 规则实验轨（非虚拟，已平仓）——
    e_wr = _win_rate_pct(exp_closed)
    el_wr, es_wr = _long_short_wr(exp_closed)
    et_wr = _win_rate_pct(exp_today_closed)
    et_lwr, et_swr = _long_short_wr(exp_today_closed)

    # —— 主观察池（虚拟）：毛 / 净 ——
    def _net_p(g: float) -> float:
        return g - _MEMOS_FEE_PCT

    v_gross_wr = _win_rate_pct(vir_closed)
    v_net_wr = (
        f"{round(len([r for r in vir_closed if _net_p(float(r.get('profit') or 0)) > 0]) / len(vir_closed) * 100, 2)}%"
        if vir_closed
        else "—"
    )
    vl_all_g, vs_all_g = _long_short_wr(vir_closed)
    vl_all_n = (
        f"{round(len([r for r in vir_closed if str(r.get('direction','')).startswith('做多') and _net_p(float(r.get('profit') or 0)) > 0]) / max(1,len([r for r in vir_closed if str(r.get('direction','')).startswith('做多')])) * 100, 2)}%"
        if any(str(r.get("direction", "")).startswith("做多") for r in vir_closed)
        else "—"
    )
    vs_all_n = (
        f"{round(len([r for r in vir_closed if str(r.get('direction','')).startswith('做空') and _net_p(float(r.get('profit') or 0)) > 0]) / max(1,len([r for r in vir_closed if str(r.get('direction','')).startswith('做空')])) * 100, 2)}%"
        if any(str(r.get("direction", "")).startswith("做空") for r in vir_closed)
        else "—"
    )

    vt_gross_wr = _win_rate_pct(vir_today_closed)
    vt_net_wr = (
        f"{round(len([r for r in vir_today_closed if _net_p(float(r.get('profit') or 0)) > 0]) / len(vir_today_closed) * 100, 2)}%"
        if vir_today_closed
        else "—"
    )

    sum_gross_today = sum(float(r.get("profit") or 0) for r in vir_today_closed)
    sum_net_today = sum(_net_p(float(r.get("profit") or 0)) for r in vir_today_closed)
    avg_g = sum_gross_today / len(vir_today_closed) if vir_today_closed else 0.0
    n_closed_today = len(vir_today_closed)

    # 平仓结构 & 分桶（主观察池·当日）
    buckets = {"TP1": [], "TP2": [], "TP3": [], "SL": []}
    for r in vir_today_closed:
        cr = str(r.get("close_reason") or "")
        if cr in buckets:
            buckets[cr].append(r)
        else:
            buckets.setdefault("其他", []).append(r)

    def _bucket_line(label: str, rows: list[dict]) -> str:
        if not rows:
            return f"<b>{label}</b>：0 笔（0.0%）均毛 —"
        pct = len(rows) / n_closed_today * 100 if n_closed_today else 0
        avg = sum(float(x.get("profit") or 0) for x in rows) / len(rows)
        return f"<b>{label}</b>：{len(rows)} 笔（{pct:.1f}%）均毛 {avg:+.4f}%"

    gross_bin1 = len([r for r in vir_today_closed if float(r.get("profit") or 0) <= 0])
    gross_bin2 = len(
        [r for r in vir_today_closed if 0 < float(r.get("profit") or 0) <= 0.16]
    )
    gross_bin3 = len(
        [
            r
            for r in vir_today_closed
            if 0.16 < float(r.get("profit") or 0) <= 0.25
        ]
    )
    gross_bin4 = len([r for r in vir_today_closed if float(r.get("profit") or 0) > 0.25])

    hint = ""
    if vir_today_closed and vt_gross_wr != vt_net_wr:
        hint = (
            "辨别提示（毛/净胜率）：若部分单子毛盈亏略高于 0 但低于双边手续费合计 "
            f"{_MEMOS_FEE_PCT}%，则净结果可能为亏，净胜率会低于毛胜率；详见下方「毛盈亏分桶」。"
        )

    sec1 = f"""
<table class="metrics">
<tr><td colspan="2"><strong>一、规则实验轨</strong>（virtual_signal 为假：本地 memos，用于大版本同步后的规则/门槛实验，与主观察池统计分列）</td></tr>
<tr><td>总交易（累计已平仓笔数）</td><td>{len(exp_closed)}</td></tr>
<tr><td>总赢 / 总亏</td><td>{len([r for r in exp_closed if float(r.get('profit') or 0) > 0])} / {len([r for r in exp_closed if float(r.get('profit') or 0) <= 0])}</td></tr>
<tr><td>总胜率</td><td>{e_wr}</td></tr>
<tr><td>做多胜率（累计·本轨）</td><td>{el_wr}</td></tr>
<tr><td>做空胜率（累计·本轨）</td><td>{es_wr}</td></tr>
<tr><td>今日已平仓</td><td>{len(exp_today_closed)}</td></tr>
<tr><td>今日胜率</td><td>{et_wr if exp_today_closed else '—（本轨今日无已平仓样本）'}</td></tr>
<tr><td>今日做多（已平笔数 / 胜率）</td><td>{len([r for r in exp_today_closed if str(r.get('direction','')).startswith('做多')])} 笔 · {et_lwr if exp_today_closed else '—'}</td></tr>
<tr><td>今日做空（已平笔数 / 胜率）</td><td>{len([r for r in exp_today_closed if str(r.get('direction','')).startswith('做空')])} 笔 · {et_swr if exp_today_closed else '—'}</td></tr>
</table>
"""

    sec2 = f"""
<table class="metrics" style="margin-top:12px">
<tr><td colspan="2"><strong>二、主观察池</strong>（<code>virtual_signal</code> 为真：与决策页信号对齐，大版本外以微调为主，统计独立）</td></tr>
<tr><td>总交易（累计已平仓笔数）</td><td>{len(vir_closed)}</td></tr>
<tr><td>总赢 / 总亏</td><td>{len([r for r in vir_closed if float(r.get('profit') or 0) > 0])} / {len([r for r in vir_closed if float(r.get('profit') or 0) <= 0])}</td></tr>
<tr><td>总胜率（毛）</td><td>{v_gross_wr}</td></tr>
<tr><td>总胜率（净·已扣双边手续费）</td><td>{v_net_wr}</td></tr>
<tr><td>累计做多（已平笔数 / 毛 · 净）</td><td>{len([r for r in vir_closed if str(r.get('direction','')).startswith('做多')])} 笔 · 毛 {vl_all_g} · 净 {vl_all_n}</td></tr>
<tr><td>累计做空（已平笔数 / 毛 · 净）</td><td>{len([r for r in vir_closed if str(r.get('direction','')).startswith('做空')])} 笔 · 毛 {vs_all_g} · 净 {vs_all_n}</td></tr>
<tr><td>今日条数（含未平）</td><td>{len(vir_today)}</td></tr>
<tr><td>今日未平仓</td><td>{len(vir_today_open)}</td></tr>
<tr><td>今日已平仓</td><td>{len(vir_today_closed)}</td></tr>
<tr><td>今日赢 / 亏（毛·仅价差%）</td><td>{len([r for r in vir_today_closed if float(r.get('profit') or 0) > 0])} / {len([r for r in vir_today_closed if float(r.get('profit') or 0) <= 0])}</td></tr>
<tr><td>今日胜率（毛）</td><td>{vt_gross_wr if vir_today_closed else '—'}</td></tr>
<tr><td>今日赢 / 亏（净·已扣双边手续费）</td><td>{len([r for r in vir_today_closed if _net_p(float(r.get('profit') or 0)) > 0])} / {len([r for r in vir_today_closed if _net_p(float(r.get('profit') or 0)) <= 0])}</td></tr>
<tr><td>今日胜率（净）</td><td>{vt_net_wr if vir_today_closed else '—'}</td></tr>
<tr><td>辨别提示（毛/净胜率）</td><td>{html.escape(hint) if hint else '—'}</td></tr>
<tr><td>今日总盈亏%（平均单笔 · 合计百分点）</td><td>平均单笔 {avg_g:.4f}% · 合计百分点 {sum_gross_today:.4f}%（每笔已扣双边合计 {_MEMOS_FEE_PCT}%）</td></tr>
<tr><td>今日·平仓结构（笔数 / 占比 / 均毛%）</td><td>{_bucket_line('TP1', buckets['TP1'])}；{_bucket_line('TP2', buckets['TP2'])}；{_bucket_line('TP3', buckets['TP3'])}；{_bucket_line('SL', buckets['SL'])}</td></tr>
<tr><td>今日·毛盈亏分桶（占已平%）</td><td>
毛≤0%：{gross_bin1} 笔（{gross_bin1/n_closed_today*100 if n_closed_today else 0:.1f}%）；
0&lt;毛≤0.16%：{gross_bin2} 笔；
0.16%&lt;毛≤0.25%：{gross_bin3} 笔；
毛&gt;0.25%：{gross_bin4} 笔
</td></tr>
<tr><td>今日做多（已平笔数 / 毛 · 净）</td><td>{len([r for r in vir_today_closed if str(r.get('direction','')).startswith('做多')])} 笔 · {_win_rate_pct([r for r in vir_today_closed if str(r.get('direction','')).startswith('做多')])} · 净胜率见上表</td></tr>
<tr><td>今日做空（已平笔数 / 毛 · 净）</td><td>{len([r for r in vir_today_closed if str(r.get('direction','')).startswith('做空')])} 笔 · {_win_rate_pct([r for r in vir_today_closed if str(r.get('direction','')).startswith('做空')])} · 净胜率见上表</td></tr>
</table>
"""

    def _sort_entries(rows: list[dict]) -> list[dict]:
        def _k(r: dict) -> str:
            return str(r.get("entry_time") or "")

        return sorted(rows, key=_k)

    # 当日宽表：时间升序，最多 20 / 10 条（多则保留时间最晚的 N 条）
    main_rows = _sort_entries(vir_today)
    if len(main_rows) > 20:
        main_rows = main_rows[-20:]
    exp_rows = _sort_entries(exp_today)
    if len(exp_rows) > 10:
        exp_rows = exp_rows[-10:]

    def _wide_row(i: int, r: dict, track: str) -> str:
        g = r.get("profit")
        gross = float(g) if g is not None else None
        if r.get("virtual_signal"):
            fee = f"{_MEMOS_FEE_PCT:.2f}"
            net = _net_p(gross) if gross is not None else None
        else:
            fee = "—"
            net = gross
        net_s = _fmt_pct(net) if net is not None else "—"
        gross_s = _fmt_pct(gross) if gross is not None else "—"
        sym = html.escape(str(r.get("symbol") or ""))
        dire = html.escape(str(r.get("direction") or ""))
        pair = f"{dire} {sym}".strip()
        src = html.escape(_fib_source_snippet(r)[:220])
        rr = html.escape(_rr_gross_net_str(r))
        return (
            f"<tr><td>{i}</td><td>{html.escape(track)}</td>"
            f"<td>{html.escape(_iso_to_bj_display(r.get('entry_time')))}</td>"
            f"<td>{html.escape(_iso_to_bj_display(r.get('close_time')))}</td>"
            f"<td>{pair}</td>"
            f"<td>{html.escape(str(r.get('entry','')))}</td>"
            f"<td>{html.escape(str(r.get('sl','')))}</td>"
            f"<td>{html.escape(str(r.get('tp1','')))}</td>"
            f"<td>{html.escape(str(r.get('tp2','')))}</td>"
            f"<td>{html.escape(str(r.get('tp3','')))}</td>"
            f"<td class=\"src-cell\">{src}</td>"
            f"<td>{rr}</td>"
            f"<td>{html.escape(str(r.get('close') if r.get('close') is not None else '—'))}</td>"
            f"<td>{gross_s}</td><td>{fee}</td><td>{net_s}</td>"
            f"<td>{html.escape(_result_cn(r))}</td></tr>"
        )

    mh = "".join(_wide_row(i + 1, r, "主观察池") for i, r in enumerate(main_rows))
    eh = "".join(_wide_row(i + 1, r, "规则实验轨") for i, r in enumerate(exp_rows))

    tbl_main = f"""
<p style="margin-top:14px"><b>主观察池（仅当日 · 最多 20 条）</b></p>
<p class="muted" style="margin:4px 0 8px 0">北京时间当日已平/未平；时间升序，最新在底部；北京 0 点后换日累计。</p>
<table class="data-table dense">
<thead><tr>
<th>序号</th><th>轨道</th><th>入场时间（北京）</th><th>平仓时间（北京）</th><th>方向·标的</th>
<th>入场价</th><th>SL</th><th>TP1</th><th>TP2</th><th>TP3</th><th>价位来源</th><th>RR（毛/净）</th>
<th>平仓价</th><th>毛盈亏（%）</th><th>手续费（%）</th><th>净盈亏（%）</th><th>结果</th>
</tr></thead>
<tbody>{mh or '<tr><td colspan="17">本日暂无记录</td></tr>'}</tbody>
</table>
"""

    tbl_exp = f"""
<p style="margin-top:14px"><b>规则实验轨（仅当日 · 最多 10 条）</b></p>
<table class="data-table dense">
<thead><tr>
<th>序号</th><th>轨道</th><th>入场时间（北京）</th><th>平仓时间（北京）</th><th>方向·标的</th>
<th>入场价</th><th>SL</th><th>TP1</th><th>TP2</th><th>TP3</th><th>价位来源</th><th>RR（毛/净）</th>
<th>平仓价</th><th>毛盈亏（%）</th><th>手续费（%）</th><th>净盈亏（%）</th><th>结果</th>
</tr></thead>
<tbody>{eh or '<tr><td colspan="17">本日暂无记录</td></tr>'}</tbody>
</table>
"""

    foot = """
<p class="muted" style="margin-top:14px;font-size:0.86rem;line-height:1.55">
说明：以下为本地 <code>trade_memory.json</code> 中的 memos 记录（两轨均为模拟记账，非交易所成交回报）。
手续费按展示口径双边合计 0.16% 估算净盈亏；统计以记录内 <code>date</code>（北京日历日）为准。
「规则实验轨」若长期笔数很少或为空，通常因当前服务主路径未接入该轨写入链路，属设计分叉而非页面故障；详见仓库 <code>docs/trade_memory_two_tracks.md</code>。
</p>
"""
    return sec1 + sec2 + tbl_main + tbl_exp + foot


def _memos_banner_html() -> str:
    """第二次改版：紫色横幅内黄字 + 两条下划线链接（原始样本 / 实盘状态）。"""
    return f"""<div class="memos-banner">
<strong>{html.escape(MEMOS_BANNER)}</strong>
<p class="memos-banner-links">
<a href="/memos_samples">memos 原始样本记录页（JSON，核销）</a>
<span class="banner-dot">·</span>
<a href="/live_state">实盘状态文件（live_trading_state.json，只读）</a>
</p>
<p class="memos-banner-meta muted">换日请至当日列表 · 约每 45 秒更新（随决策页加载刷新）</p>
</div>"""


def _meta_source_zh(raw: object) -> str:
    """数据源展示名（与底层字段对应，仅用于页面中文）。"""
    s = str(raw or "").strip()
    if s == "gateio_ccxt_v316":
        return "Gate.io · CCXT（数据层 V3.17.0）"
    return s


_STATE_JSON_KEY_ZH = {
    "last_signal_bar_iso": "上一根信号 K 线时间（ISO）",
    "last_counted_signal_iso": "上次已计数的信号时间（ISO）",
    "signals_today": "今日信号计数",
    "signals_date": "信号所属日期",
    "last_sig": "上次信号方向（数值）",
}


def _zh_state_keys_for_display(d: dict) -> dict:
    """仅用于页面展示：常见字段名中文化，未知键保持原文。"""
    return {_STATE_JSON_KEY_ZH.get(k, k): v for k, v in d.items()}


def _utc_ms_bj_plus8(ms: object) -> str:
    """最新柱：北京时间，带 +08:00 后缀（与 V3.14 第一版展示一致）。"""
    if ms is None:
        return "—"
    try:
        m = int(ms)
    except Exception:
        return "—"
    if m <= 0:
        return "—"
    dt = datetime.fromtimestamp(m / 1000.0, tz=timezone.utc).astimezone(_BJ)
    return dt.strftime("%Y-%m-%d %H:%M:%S +08:00")


def _bars_since_last_signal_1m(last_k_ms: int, last_iso: object) -> int:
    """距上次信号已 N 根 1m（与 live_trading 冷却逻辑同一时间轴）。"""
    if not last_iso or not last_k_ms:
        return 0
    try:
        sig_t = datetime.fromisoformat(str(last_iso).replace("Z", "+00:00"))
        last_bar_t = datetime.fromtimestamp(last_k_ms / 1000.0, tz=timezone.utc)
        return max(0, int((last_bar_t - sig_t).total_seconds() // 60))
    except Exception:
        return 0


def _fmt_backtest_price(v: object) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.4f}"
    except Exception:
        return "—"


def _ticker_ms_plausible(ms: int) -> bool:
    """过滤误把价格等字段当成时间戳（否则会显示 1970 年附近）。"""
    if ms <= 0:
        return False
    # 约 2001-09～2100（毫秒）；低于 1e12 的多为秒级误乘或价格
    return 1_000_000_000_000 <= ms <= 4_102_444_800_000


def _normalize_ticker_ts_to_ms(raw: object) -> Optional[int]:
    """CCXT ticker.timestamp 多为毫秒；秒级则乘 1000。"""
    if raw is None:
        return None
    try:
        v = int(float(raw))
        if v <= 0:
            return None
        if v < 10**11:
            v *= 1000
        return v if _ticker_ms_plausible(v) else None
    except Exception:
        return None


def _extract_ccxt_ticker_time_bj(tinfo: object, snap: dict) -> str:
    """Gate/CCXT 部分行情不返回 ticker 时间戳；尽量多字段解析，否则用 K 线拉取时刻作参考。"""
    if not isinstance(snap, dict):
        snap = {}
    if not isinstance(tinfo, dict):
        tinfo = {}
    ts_ms: Optional[int] = None
    ts_ms = _normalize_ticker_ts_to_ms(tinfo.get("timestamp"))
    if ts_ms is None and tinfo.get("datetime") is not None:
        ts_ms = _normalize_ticker_ts_to_ms(tinfo.get("datetime"))
    info = tinfo.get("info")
    if ts_ms is None and isinstance(info, dict):
        # 勿用 "last"：在 Gate 等交易所常为最新价，误解析会得到 1970 年。
        for k in ("update_time", "timestamp", "time", "ts", "t"):
            v = info.get(k)
            if v is None:
                continue
            try:
                cand = int(float(v))
                if cand <= 0:
                    continue
                if cand < 10**11:
                    cand *= 1000
                if _ticker_ms_plausible(cand):
                    ts_ms = cand
                    break
            except Exception:
                continue
    if ts_ms is not None and _ticker_ms_plausible(ts_ms):
        return utc_ms_to_bj_str(ts_ms)
    ref = snap.get("fetched_at_ms")
    if ref is not None:
        try:
            rms = int(ref)
            if _ticker_ms_plausible(rms):
                return (
                    "参考：本页 K 线拉取时刻 "
                    f"{utc_ms_to_bj_str(rms)}"
                    "；交易所 ticker 未返回报价时间戳"
                )
        except Exception:
            pass
    klines = snap.get("klines") or []
    last_k = klines[-1] if klines else {}
    last_ms = int(last_k.get("time") or 0)
    if _ticker_ms_plausible(last_ms):
        return (
            "参考：本页 K 线拉取时刻 "
            f"{utc_ms_to_bj_str(last_ms)}"
            "（以最后一根 K 线时间近似；交易所 ticker 未返回报价时间戳）"
        )
    return (
        f"本决策计算时间 {datetime.now(_BJ).strftime('%Y-%m-%d %H:%M:%S')} "
        "（ticker 与 K 线均无可用时间戳）"
    )


def _fmt_klines_impl_line(snap: dict, meta: dict) -> str:
    """将内部模式名转为可读中文，并保留内部版本号便于排查。"""
    m = {**(meta or {}), **(snap or {})}
    mode = str(m.get("klines_fetch_mode") or "").strip()
    build = str(m.get("klines_fetch_build") or "").strip()
    src = str(m.get("source") or "—")
    cnt = m.get("count")
    n_str = str(cnt) if cnt is not None else "—"
    if mode == "fetch_ohlcv_recent" and build == "ccxt_fetch_ohlcv_limit_v2":
        return (
            f"单次拉取最近 {n_str} 根 1m K 线（单次上限 1000 根）"
            f" · 内部版本 {build} · 数据源 {src}"
        )
    if mode == "synthetic":
        return f"合成兜底 K 线（演示用）· {build} · 根数 {n_str}"
    parts: list[str] = []
    if mode:
        parts.append(f"模式 {mode}")
    if build:
        parts.append(f"内部版本 {build}")
    if parts:
        return f"{' · '.join(parts)} · 根数 {n_str} · 数据源 {src}"
    return f"单次拉取最近 {n_str} 根 · 数据源 {src}"


def _hft_brain_row(km: dict) -> str:
    """Hermes 技能库节选入脑状态（仅展示，不下单）。"""
    try:
        n = int(km.get("hft_skill_brain_line_count") or 0)
    except Exception:
        n = 0
    sha = str(km.get("hft_skill_brain_sha256") or "").strip()
    prev = str(km.get("hft_skill_brain_preview") or "").strip()
    ing = str(km.get("hft_skill_brain_ingested_at") or "").strip()
    if n <= 0:
        return "尚未入脑：请先运行 scripts/hft_skill_auto_ingest.py（或配置每日 cron）"
    short_sha = f"{sha[:12]}…" if len(sha) >= 12 else (sha or "—")
    pv = (prev[:160] + "…") if len(prev) > 160 else prev
    return f"节选 {n} 条 · sha256 {short_sha} · 入脑时间 {ing or '—'} · 预览：{pv or '—'}"


def _build_v314_signal_block(
    sym: str,
    km: dict,
    snap: dict,
    meta: dict,
    klines: list,
    last_k: dict,
    state: dict,
) -> str:
    """V3.14 第一版：规则信号与执行价位整块 HTML（顺序与文案按规格固定）。"""
    sig_label = str(km.get("signal_label", "")).strip()
    try:
        raw = int(state.get("last_sig", 0) or 0)
    except Exception:
        raw = 0
    try:
        sig_n = int(state.get("signals_today", 0) or 0)
    except Exception:
        sig_n = 0

    if sig_label == "无":
        sug = "开仓建议：观望（无趋势突破信号）"
    elif sig_label.startswith("偏多"):
        sug = "开仓建议：参考偏多（轻）"
    else:
        sug = "开仓建议：参考偏空（轻）"

    last_ms = int(last_k.get("time") or 0)
    kcount = int(meta.get("count") or len(klines) or 0)
    bt_price = _fmt_backtest_price(snap.get("last_close"))
    latest_col = _utc_ms_bj_plus8(last_ms)
    cd_rem = str(km.get("cooldown_left", "0")).strip()
    if cd_rem in ("", "—"):
        cd_rem = "0"
    bars_since = _bars_since_last_signal_1m(last_ms, state.get("last_signal_bar_iso"))

    entry = km.get("entry_price")
    sl = km.get("sl_price")
    tp1 = km.get("tp1_price")
    tp2 = km.get("tp2_price")
    if sig_label == "无":
        ln_open = "开仓点位：等待信号出现"
        ln_sl = "止损点位：等待信号出现"
        ln_tp1 = "第一止盈点：等待信号出现（平50%）"
        ln_tp2 = "第二止盈点：等待信号出现(runner:全平)"
    else:
        ln_open = f"开仓点位：{html.escape(fmt_price(entry))} USDT"
        ln_sl = f"止损点位：{html.escape(fmt_price(sl))} USDT"
        ln_tp1 = f"第一止盈点：{html.escape(fmt_price(tp1))} USDT（平50%）"
        ln_tp2 = f"第二止盈点：{html.escape(fmt_price(tp2))} USDT(runner:全平)"

    ts_footer = datetime.now(_BJ).strftime("%Y-%m-%d %H:%M:%S +08:00")

    h2 = html.escape(f"V3.14 {sym} 纯规则·实时信号")
    cur_sig = html.escape(f"当前信号：{sig_label} (raw={raw})")
    sug_e = html.escape(sug)

    body = f"""<h2>{h2}</h2>
<div class="v314-signal">
<p>{cur_sig}</p>
<p>{sug_e}</p>
<p>回测价（用于信号）：{html.escape(bt_price)} USDT</p>
<p>·K线根数{kcount}</p>
<p>·最新柱{html.escape(latest_col)}</p>
<p>cooldown:3根1m</p>
<p>·距上次信号已{bars_since}根</p>
<p>·剩余{html.escape(cd_rem)}根</p>
<p>参数：手续费0.080%单边 ·凯利cap0.22 ·半凯利仓位比例~0.2125</p>
<p>执行（与回测一致）：+0.12%平50% ·runner TP±0.45% ·SL≈0.023%(ATR/0.3%合成)</p>
<p><b>交易执行点位（手动跟单专用）</b></p>
<p>{ln_open}</p>
<p>{ln_sl}</p>
<p>{ln_tp1}</p>
<p>{ln_tp2}</p>
<p>今日规则信号次数：{sig_n}（按新出现的信号K线去重累计）</p>
<p>弱量过滤：已关闭（弱量比阈值=0，与回测一致）</p>
<p class="v314-ts">{html.escape(ts_footer)}</p>
</div>"""
    return body


def _zh_decision_copy(text: object) -> str:
    """将决策文案中的周期缩写改为中文，便于阅读（不改变数值与 RSI 等术语）。"""
    s = str(text or "")
    if not s:
        return s
    s = s.replace("1H+4H", "1小时+4小时")
    for a, b in (
        ("5m=", "5分钟="),
        ("15m=", "15分钟="),
        ("1H=", "1小时="),
        ("4H=", "4小时="),
    ):
        s = s.replace(a, b)
    s = s.replace(" | ", " · ")
    s = s.replace("RSI(1m)", "RSI（1分钟）")
    return s


def _evolution_block() -> str:
    """直接读取 trade_memory.json 渲染第二次改版样式（不依赖 ai_evo 简化报表）。"""
    try:
        from live_trading import _reload_evolution_memory_from_disk

        _reload_evolution_memory_from_disk()
    except Exception:
        pass
    try:
        trades = _load_trades_flat()
    except Exception as e:
        return f'<p class="muted">读取 trade_memory 失败：{html.escape(str(e))}</p>'
    today_bj = datetime.now(_BJ).strftime("%Y-%m-%d")
    if not trades:
        return '<p class="muted">暂无 trade_memory 记录；待积累后自动刷新。</p>'
    try:
        return _memos_evolution_full_html(trades, today_bj)
    except Exception as e:
        return f'<p class="muted">memos 区块渲染失败：{html.escape(str(e))}</p>'


def _find_latest_matrix_report_path() -> Optional[Path]:
    root = Path(__file__).resolve().parent / "outputs"
    if not root.exists():
        return None
    candidates = list(root.rglob("*_matrix_report.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _html_table_from_rows(
    title: str,
    headers: List[str],
    rows: List[List[Any]],
) -> str:
    th = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = ""
    for r in rows:
        tds = "".join(f"<td>{html.escape(str(c))}</td>" for c in r)
        body += f"<tr>{tds}</tr>"
    return f"""<p style="margin-top:14px"><b>{html.escape(title)}</b></p>
<table class="data-table dense"><thead><tr>{th}</tr></thead><tbody>{body or '<tr><td colspan="99">无数据</td></tr>'}</tbody></table>"""


def _backtest_matrix_report_block() -> str:
    """阶段 A 回测矩阵：读取 outputs 下最新的 *_matrix_report.json（由 scripts/backtest_matrix.py 生成）。"""
    p = _find_latest_matrix_report_path()
    if not p:
        return '<p class="muted" style="margin-top:12px">阶段A回测矩阵报告：尚未生成。运行 <code>python3 scripts/backtest_matrix.py</code> 后刷新本页。</p>'
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return f'<p class="muted">读取矩阵报告失败：{html.escape(str(e))}</p>'

    rel = p.resolve().relative_to(Path(__file__).resolve().parent)
    head = f'<p class="muted" style="margin:12px 0 8px 0">阶段A回测矩阵报告（最新：<code>{html.escape(str(rel))}</code> · UTC {html.escape(str(data.get("generated_at_utc") or ""))}）</p>'
    chunks: List[str] = [head]

    ms = data.get("mode_summary") or {}
    rows_ms: List[List[Any]] = []
    for mode in ("experiment", "main"):
        m = ms.get(mode) or {}
        rows_ms.append(
            [
                mode,
                m.get("runs"),
                m.get("avg_total_trades"),
                m.get("avg_win_rate_pct"),
                m.get("avg_sum_profit_pct"),
            ]
        )
    chunks.append(
        _html_table_from_rows(
            "一、模式汇总（矩阵内全部 run 的简单平均）",
            ["模式", "run 数", "平均单量", "平均胜率%", "平均合计盈亏%"],
            rows_ms,
        )
    )

    vp = data.get("vs_previous")
    if isinstance(vp, dict):
        rows_vp: List[List[Any]] = []
        bm = vp.get("by_mode") or {}
        for mode in ("experiment", "main"):
            d = bm.get(mode) or {}
            rows_vp.append(
                [
                    mode,
                    d.get("avg_total_trades_delta"),
                    d.get("avg_win_rate_pct_delta"),
                    d.get("avg_sum_profit_pct_delta"),
                ]
            )
        chunks.append(
            f'<p class="muted" style="margin:8px 0 4px 0">相对上期：{html.escape(str(vp.get("previous_report") or ""))} '
            f'（UTC {html.escape(str(vp.get("previous_generated_at_utc") or ""))}）</p>'
        )
        chunks.append(
            _html_table_from_rows(
                "一（续）相对上期变化（同一输出目录内上一份报告；lite 与 full 各自对比）",
                ["模式", "Δ平均单量", "Δ平均胜率%点", "Δ平均合计盈亏%"],
                rows_vp,
            )
        )

    best = data.get("best_by_symbol") or {}
    rows_b: List[List[Any]] = []
    for sym in sorted(best.keys()):
        r = best[sym]
        if not isinstance(r, dict):
            continue
        rows_b.append(
            [
                sym,
                r.get("level_mode"),
                r.get("entry_cooldown_bars"),
                r.get("total_trades"),
                r.get("win_rate_pct"),
                r.get("sum_profit_pct"),
            ]
        )
    chunks.append(
        _html_table_from_rows(
            "二、各币种最优候选（按胜率为主，需满足 min_trades_report）",
            ["标的", "模式", "冷却(根)", "单量", "胜率%", "合计盈亏%"],
            rows_b,
        )
    )

    evm = data.get("exp_vs_main_same_setting") or []
    rows_e: List[List[Any]] = []
    for r in evm:
        if not isinstance(r, dict):
            continue
        rows_e.append(
            [
                r.get("symbol"),
                r.get("entry_cooldown_bars"),
                r.get("exp_trades"),
                r.get("main_trades"),
                r.get("trade_delta"),
                r.get("exp_win_rate"),
                r.get("main_win_rate"),
                r.get("win_rate_delta"),
            ]
        )
    chunks.append(
        _html_table_from_rows(
            "三、同设置下 实验轨 − 主观察（单量/胜率差）",
            [
                "标的",
                "冷却",
                "实验单量",
                "主池单量",
                "单量差",
                "实验胜率",
                "主池胜率",
                "胜率差",
            ],
            rows_e,
        )
    )

    top = data.get("top_candidates") or []
    rows_t: List[List[Any]] = []
    for r in top:
        if not isinstance(r, dict):
            continue
        rows_t.append(
            [
                r.get("symbol"),
                r.get("level_mode"),
                r.get("entry_cooldown_bars"),
                r.get("total_trades"),
                r.get("win_rate_pct"),
                r.get("sum_profit_pct"),
            ]
        )
    chunks.append(
        _html_table_from_rows(
            "四、全局候选 Top（启发式排序：胜率 × √(单量)）",
            ["标的", "模式", "冷却(根)", "单量", "胜率%", "合计盈亏%"],
            rows_t,
        )
    )

    return "\n".join(chunks)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from live_trading import start_live_bot_background

        start_live_bot_background()
    except Exception as e:
        print(f"[warn] start_live_bot_background: {e}")
    yield


app = FastAPI(title="longxia_system", lifespan=lifespan)


@app.get("/api/version")
def api_engine_version():
    """对外版本锚点（监控 curl 用）；与页面「数据层」文案一致。"""
    return JSONResponse(
        {"engine": ENGINE_VERSION, "app": "longxia_system", "data_layer": ENGINE_VERSION}
    )


@app.get("/")
def root():
    """浏览器访问站点根路径时直接进入决策看板（与 /dashboard 行为一致）。"""
    return RedirectResponse(
        url=f"/decision?symbol={quote('SOL/USDT', safe='')}", status_code=302
    )


@app.get("/dashboard")
def dashboard_redirect(symbol: str = Query("SOL/USDT")):
    sym = _pick_symbol(symbol)
    return RedirectResponse(
        url=f"/decision?symbol={quote(sym, safe='')}", status_code=302
    )


_REPO = Path(__file__).resolve().parent


@app.get("/memos_samples", response_class=HTMLResponse)
def page_memos_samples():
    """只读展示 trade_memory 末尾样本（支持顶层数组或 schema 包装）。"""
    p = _REPO / "trade_memory.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        body = f"<pre>读取失败：{html.escape(str(e))}</pre>"
    else:
        if isinstance(raw, dict) and "trades" in raw and not isinstance(raw.get("trades"), list):
            body = "<p>格式异常（trades 须为数组）</p>"
        else:
            trades, _ = _trade_memory_parse(raw)
            tail = trades[-80:]
            body = f"<p>共 {len(trades)} 条，展示末尾 {len(tail)} 条（只读）</p><pre>{html.escape(json.dumps(tail, ensure_ascii=False, indent=2))}</pre>"
    strip = _top_entry_strip("memos")
    return HTMLResponse(
        f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/><title>样本统计 · trade_memory</title>
<style>
body{{background:#0f1419;color:#e8eef7;font-family:system-ui;padding:20px;}}
a{{color:#5c7cfa;}}
.top-entry-strip {{
  display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;
  margin-bottom:18px;padding:12px 16px;background:rgba(0,0,0,.28);
  border-radius:12px;border:1px solid rgba(255,255,255,.1);
}}
.top-entry{{color:#a5b4fc;text-decoration:none;font-size:0.95rem;padding:6px 14px;border-radius:10px;border:1px solid transparent;}}
.top-entry:hover{{background:rgba(255,255,255,.07);color:#fff;}}
.top-entry-active{{color:#51cf66!important;font-weight:700;border-color:rgba(81,207,102,.45);background:rgba(81,207,102,.08);}}
</style></head><body>
{strip}
<h1>trade_memory.json 样本</h1>
{body}
</body></html>"""
    )


@app.get("/live_state", response_class=HTMLResponse)
def page_live_state():
    """实盘状态 JSON 单独页（与决策页摘要同源）。"""
    p = _REPO / "live_trading_state.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        text = json.dumps(raw, ensure_ascii=False, indent=2)
    except Exception as e:
        text = str(e)
    strip = _top_entry_strip("live")
    return HTMLResponse(
        f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/><title>实盘状态</title>
<style>
body{{background:#0f1419;color:#e8eef7;font-family:system-ui;padding:20px;}}
pre{{white-space:pre-wrap;font-size:0.88rem;}}
.top-entry-strip {{
  display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;
  margin-bottom:18px;padding:12px 16px;background:rgba(0,0,0,.28);
  border-radius:12px;border:1px solid rgba(255,255,255,.1);
}}
.top-entry{{color:#a5b4fc;text-decoration:none;font-size:0.95rem;padding:6px 14px;border-radius:10px;border:1px solid transparent;}}
.top-entry:hover{{background:rgba(255,255,255,.07);color:#fff;}}
.top-entry-active{{color:#51cf66!important;font-weight:700;border-color:rgba(81,207,102,.45);background:rgba(81,207,102,.08);}}
</style></head><body>
{strip}
<h1>live_trading_state.json（只读）</h1>
<pre>{html.escape(text)}</pre>
</body></html>"""
    )


@app.get("/decision", response_class=HTMLResponse)
async def page_decision(symbol: str = Query("SOL/USDT")):
    sym = _pick_symbol(symbol)
    snap = build_indicator_snapshot(sym, 500)
    km = get_v313_decision_snapshot(force_refresh=True, symbol=sym)
    fg = get_fear_greed()
    last_close = snap.get("last_close")
    try:
        live_ticker = await fetch_current_ticker_price(sym)
    except Exception:
        live_ticker = None
    tinfo: dict = {}
    try:
        tinfo = fetch_ticker(sym)
    except Exception:
        tinfo = {}
    ticker_quote_bj = _extract_ccxt_ticker_time_bj(tinfo, snap)
    px_for_memos = live_ticker if live_ticker is not None else last_close
    try:
        if px_for_memos is not None:
            pxf = float(px_for_memos)
            sync_virtual_memos_from_state(sym, pxf)
            sync_experiment_track_from_snapshot(sym, pxf, km)
    except Exception:
        pass
    klines = snap.get("klines") or []
    last_k = klines[-1] if klines else {}
    state = km.get("live_trading_state") or {}

    nav_links = []
    for s in SYMBOL_CHOICES:
        active = "nav-active" if s == sym else ""
        nav_links.append(
            f'<a class="nav-link {active}" href="/decision?symbol={quote(s, safe="")}">{html.escape(s)}</a>'
        )
    nav_html = "\n".join(nav_links)
    qsym = quote(sym, safe="")
    meta = km.get("indicator_snapshot_meta") or {}
    klines_impl_line = _fmt_klines_impl_line(snap, meta)
    evo_html = _evolution_block()
    matrix_report_html = _backtest_matrix_report_block()
    v314_signal_html = _build_v314_signal_block(
        sym, km, snap, meta, klines, last_k, state
    )
    live_line = fmt_price(live_ticker if live_ticker is not None else last_close)
    _sp = str(km.get("spot_ticker_price_str") or "").strip() or live_line
    _fallback_ticker = (
        f"实时成交价(CCXT ticker,Gate现货)：{_sp} USDT"
    )
    if live_ticker is None:
        ticker_raw = _fallback_ticker
    else:
        ticker_raw = km.get("ticker_display_lines") or _fallback_ticker
    ticker_html = html.escape(ticker_raw).replace("\n", "<br>")

    body = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>多币种指标看板 · {html.escape(sym)}</title>
<style>
:root {{
  --bg: #0f1419;
  --panel: #1a2332;
  --text: #e8eef7;
  --muted: #8b9bb4;
  --accent: #5c7cfa;
  --orange: #fd7e14;
  --green: #51cf66;
  --banner: linear-gradient(135deg, #2b2149 0%, #1a3d52 50%, #143d2e 100%);
  --card-shadow: 0 4px 24px rgba(0,0,0,.35);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 0;
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  background: var(--bg); color: var(--text); min-height: 100vh;
}}
.page-wrap {{ max-width: 1040px; margin: 0 auto; padding: 20px 18px 48px; }}
.top-entry-strip {{
  display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center;
  margin-bottom: 14px; padding: 12px 16px; background: rgba(0,0,0,.28);
  border-radius: 12px; border: 1px solid rgba(255,255,255,.1);
}}
.top-entry {{
  color: #a5b4fc; text-decoration: none; font-size: 0.95rem;
  padding: 6px 14px; border-radius: 10px; border: 1px solid transparent;
}}
.top-entry:hover {{ background: rgba(255,255,255,.07); color: #fff; }}
.top-entry-active {{
  color: var(--green) !important; font-weight: 700;
  border-color: rgba(81, 207, 102, .45); background: rgba(81, 207, 102, .08);
}}
.memos-banner {{
  background: var(--banner);
  border: 1px solid rgba(124, 92, 255, .35);
  border-radius: 14px;
  padding: 16px 20px;
  margin-bottom: 18px;
  font-size: 1.02rem;
  line-height: 1.65;
  text-align: center;
  color: #f0f4ff;
  box-shadow: var(--card-shadow);
}}
.memos-banner strong {{ color: #ffe066; font-weight: 600; }}
.memos-banner-links {{ margin-top: 12px; line-height: 1.55; }}
.memos-banner-links a {{ color: #a5d8ff; text-decoration: underline; }}
.banner-dot {{ margin: 0 8px; color: var(--muted); }}
.memos-banner-meta {{ margin-top: 6px; font-size: 0.82rem; color: var(--muted); }}
.data-table.dense {{ font-size: 0.72rem; }}
.data-table.dense th, .data-table.dense td {{ padding: 4px 5px; vertical-align: top; }}
.src-cell {{ max-width: 12rem; word-break: break-word; font-size: 0.68rem; }}
.v316-tag {{
  display: inline-block; margin-left: 8px; padding: 2px 10px;
  font-size: 0.78rem; font-weight: 600;
  color: #a5d8ff; background: rgba(92, 124, 250, .2);
  border-radius: 999px; vertical-align: middle;
}}
.nav-strip {{
  display: flex; flex-wrap: wrap; gap: 8px 12px; margin-bottom: 16px;
  padding: 12px 14px; background: var(--panel); border-radius: 12px;
  border: 1px solid rgba(255,255,255,.06);
}}
.nav-link {{
  color: #a5b4fc; text-decoration: none; font-size: 0.92rem;
  padding: 4px 8px; border-radius: 8px;
}}
.nav-link:hover {{ background: rgba(255,255,255,.06); color: #fff; }}
.nav-active {{ color: var(--green) !important; font-weight: 700; }}
h1 {{
  font-size: 1.35rem; font-weight: 700; margin: 8px 0 14px;
  letter-spacing: 0.02em;
}}
.subline {{ color: var(--muted); font-size: 0.88rem; margin-bottom: 18px; }}
.card {{
  background: var(--panel); border-radius: 14px; padding: 18px 20px; margin: 14px 0;
  border: 1px solid rgba(255,255,255,.07);
  box-shadow: var(--card-shadow);
}}
.card h2 {{
  margin: 0 0 12px 0; font-size: 1.05rem; font-weight: 600;
  color: #fff; border-bottom: 1px solid rgba(255,255,255,.08); padding-bottom: 8px;
}}
.card.orange {{ border-left: 4px solid var(--orange); }}
.card.green {{ border-left: 4px solid var(--green); }}
.card.memos-evolution {{ border-left: 4px solid var(--accent); }}
.metrics {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
.metrics td {{ padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,.06); }}
.metrics td:first-child {{ color: var(--muted); width: 38%; }}
.data-table {{
  width: 100%; border-collapse: collapse; font-size: 0.82rem; margin-top: 10px;
}}
.data-table th, .data-table td {{
  border: 1px solid rgba(255,255,255,.1); padding: 6px 8px; text-align: left;
}}
.data-table th {{ background: rgba(0,0,0,.25); color: #c5d4e8; }}
.data-table pre {{ margin: 0; white-space: pre-wrap; word-break: break-all; font-size: 0.75rem; }}
.muted {{ color: var(--muted); font-size: 0.88rem; }}
.reflect {{ margin-top: 14px; padding: 12px; background: rgba(0,0,0,.2); border-radius: 10px; line-height: 1.55; }}
.memos-day-meta {{
  display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px 16px;
  font-size: 0.82rem; color: var(--muted); margin-bottom: 10px; padding: 0 4px;
}}
.reflect-home {{
  margin: 0 0 16px 0; padding: 12px 14px; background: rgba(0,0,0,.22);
  border-radius: 12px; border: 1px solid rgba(255,255,255,.08); line-height: 1.6;
}}
.refresh-hint {{
  position: fixed; bottom: 12px; right: 14px; font-size: 0.75rem; color: var(--muted);
  background: rgba(0,0,0,.5); padding: 6px 12px; border-radius: 8px; z-index: 10;
}}
code {{ color: #a5d8ff; font-size: 0.85em; }}
.wait-big {{
  font-size: 1.35rem; font-weight: 800; color: #ffe066; text-align: center;
  padding: 22px 16px; background: rgba(0,0,0,.35); border-radius: 12px;
  border: 1px solid rgba(255, 224, 102, .35);
}}
.v314-signal {{ font-size: 0.92rem; line-height: 1.82; }}
.v314-signal p {{ margin: 0.2em 0; }}
.v314-signal .v314-ts {{ color: var(--muted); font-size: 0.88rem; margin-top: 0.65em; }}
</style></head><body>
<div class="page-wrap">
{_memos_banner_html()}

<div class="nav-strip">{nav_html}</div>

{_memos_reflect_bar_html()}

<h1>多币种指标看板<span class="v316-tag">· Gate.io CCXT（数据层 V3.17.0）</span></h1>
<p class="subline">当前交易对：<b>{html.escape(sym)}</b>
&nbsp;·&nbsp; 数据源 <code>{html.escape(_meta_source_zh(meta.get("source")))}</code>
&nbsp;·&nbsp; 1 分钟 K 线根数 <b>{html.escape(str(meta.get("count", "")))}</b></p>

<div class="card orange">
<h2>关键指标（下一根 5 分钟 / 概率 / 大周期）</h2>
<table class="metrics">
<tr><td>预测周期</td><td>{html.escape(str(km.get("prediction_cycle", "")))}</td></tr>
<tr><td>最新 K 线时间（北京时间）</td><td>{html.escape(str(km.get("latest_bar_time", "")))}</td></tr>
<tr><td>涨跌概率（5 分钟）</td><td>上涨 {km.get("prob_up_5m")}%　下跌 {km.get("prob_down_5m")}%</td></tr>
<tr><td>大周期趋势</td><td>{html.escape(_zh_decision_copy(km.get("big_trend")))}</td></tr>
<tr><td>决策说明 · 周期</td><td>{html.escape(_zh_decision_copy(km.get("cycle_judgment")))}</td></tr>
<tr><td>决策说明 · 技术</td><td>{html.escape(_zh_decision_copy(km.get("technical_indicators")))}</td></tr>
<tr><td>决策说明 · 概率</td><td>{html.escape(_zh_decision_copy(km.get("prob_model_line")))}</td></tr>
<tr><td>能力引擎 · 一致性评分</td><td>{html.escape(str(km.get("consistency_score", "—")))}</td></tr>
<tr><td>能力引擎 · 贝叶斯后验胜率</td><td>{html.escape(str(km.get("bayes_posterior_winrate", "—")))}</td></tr>
<tr><td>能力引擎 · RSI(1m)</td><td>{html.escape(str(km.get("rsi_1m", "—")))}</td></tr>
<tr><td>能力引擎 · 形态识别（条数）</td><td>{html.escape(str(len(km.get("pattern_list") or [])))} 条</td></tr>
<tr><td>能力引擎 · 形态识别（明细）</td><td>{html.escape("、".join([str(x) for x in (km.get("pattern_list") or [])]) or "—")}</td></tr>
<tr><td>能力引擎 · 斐波关键位</td><td>{html.escape(json_dumps_safe(km.get("fib_levels") or {}))}</td></tr>
<tr><td>能力引擎 · 高级指标引擎</td><td>{html.escape(json_dumps_safe(km.get("advanced_indicators") or {}))}</td></tr>
<tr><td>决策依据 · 5m K线快照</td><td>{html.escape(json_dumps_safe(km.get("candle_5m") or {}))}</td></tr>
<tr><td>书本提示（五书节选 + Hermes · 参考）</td><td>{html.escape(_zh_decision_copy(km.get("theory_book_hints_text")))}</td></tr>
<tr><td>Hermes 技能库（已入脑节选 · 参考）</td><td>{html.escape(_hft_brain_row(km))}</td></tr>
<tr><td>趋势状态</td><td>{html.escape(_zh_decision_copy(km.get("trend_status")))}</td></tr>
<tr><td>执行状态 · 信号转单同步</td><td>{html.escape(str(km.get("virtual_order_status", "—")))}</td></tr>
<tr><td>数据新鲜度 · Gate 现货 ticker 报价时间（北京）</td><td>{html.escape(ticker_quote_bj)}</td></tr>
<tr><td>K 线拉取实现</td><td>{html.escape(klines_impl_line)}</td></tr>
</table></div>

<div class="card green">
{v314_signal_html}
</div>

<div class="card">
<h2>CCXT 1 分钟行情快照</h2>
<p><span style="font-size:1.15em">{ticker_html}</span>
&nbsp; | 恐惧与贪婪指数：<b>{html.escape(str(fg))}</b></p>
<p class="muted">1 分钟 K 线最后一根收盘价（已收盘，用于指标与信号计算）：{html.escape(fmt_price(last_close))} USDT
&nbsp;·&nbsp; 该根时间（北京时间）：{html.escape(utc_ms_to_bj_str(last_k.get("time")))} &nbsp;|&nbsp; 交易所时间戳（毫秒）：{html.escape(str(last_k.get("time", "")))}</p>
<p>最后一根 K 线（北京时间 {html.escape(utc_ms_to_bj_str(last_k.get("time")))})：
开 {html.escape(fmt_price(last_k.get("open")))}　高 {html.escape(fmt_price(last_k.get("high")))}
　低 {html.escape(fmt_price(last_k.get("low")))}　收 {html.escape(fmt_price(last_k.get("close")))}
　量 {html.escape(fmt_vol(last_k.get("volume")))}</p>
<p class="muted">K 线由程序缓存接口拉取（<code>get_pair_klines_1m_cached</code> / <code>fetch_ohlcv_long_history</code>）；顶部「实时成交价」来自 <code>fetch_current_ticker_price</code>（即 <code>fetch_ticker</code> 的 last），与 Gate 网页现价一致。</p>
</div>

<div class="card memos-evolution">
<h2>memos 自动进化：样本统计与模拟记录</h2>
{evo_html}
{matrix_report_html}
</div>

<div class="card">
<h2>实盘状态文件（live_trading_state.json，只读）</h2>
<p class="muted">与样本记录相同：不在此展开全文。请使用页面顶部横幅中的「实盘状态文件」链接查看完整 JSON（键名中文化，键字母排序）。</p>
</div>

<div class="refresh-hint">每 45 秒自动刷新本页 · 保留当前所选交易对</div>
</div>
<script>
setTimeout(function() {{
  window.location.href = "/decision?symbol={qsym}";
}}, 45000);
</script>
</body></html>"""
    return HTMLResponse(content=body)


def fmt_price(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.6f}".rstrip("0").rstrip(".")
    except Exception:
        return "—"


def fmt_vol(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.4f}"
    except Exception:
        return "—"


def json_dumps_safe(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
