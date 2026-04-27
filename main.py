"""
Web / 服务入口：V3.18.0 全中文仪表盘 · /decision（V3.14 规则信号块第一版样式 + memos + 北京时间）。
对外引擎版本见 ENGINE_VERSION 与 GET /api/version。
"""
from __future__ import annotations

from pathlib import Path


def _load_main_dotenv() -> None:
    """直接运行 ``python3 main.py`` 时加载仓库根目录 ``.env`` → ``ENV_FILE``（默认 ``.env.dev``），与 systemd 环境变量并存。"""
    try:
        import os

        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent
    base = root / ".env"
    if base.is_file():
        load_dotenv(base, override=False)
    env_name = os.environ.get("ENV_FILE", ".env.dev")
    sec = root / env_name if not env_name.startswith("/") else Path(env_name)
    if sec.is_file():
        # 进程已显式传入的端口（如 systemd / nohup env）不应被 .env.dev 覆盖
        _port_preserve = {
            k: os.environ.get(k)
            for k in ("PORT", "LONGXIA_HTTP_PORT")
            if os.environ.get(k, "").strip()
        }
        load_dotenv(sec, override=True)
        for _k, _v in _port_preserve.items():
            if _v:
                os.environ[_k] = _v


_load_main_dotenv()

import os
import html
import json
from collections import defaultdict
from typing import Any, List, Optional
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

from data_fetcher import fetch_current_ticker_price, fetch_ticker, log_v317_engine_ready

log_v317_engine_ready()

# 与 Hermes / 监控对齐的对外版本号（仅标识，不改变交易逻辑）
ENGINE_VERSION = "V3.18.0"

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
from utils.exit_feature_flags import dynamic_levels_enabled, scaled_exit_enabled
from utils.teacher_track_constants import SIGNAL_TRACK_BOOST, SIGNAL_TRACK_COMBAT

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

# 部署自检：curl -s 'http://127.0.0.1:18080/copytrade' | grep longxia-ui
# 若无输出，说明当前 HTTP 进程不是本仓库这份 main.py（未拉代码 / 工作目录不对 / 反代到旧实例）。
_HTML_BUILD_MARKER = "<!-- longxia-ui:nav-teacher-v2 -->"
_HTML_NO_CACHE_HEADERS = {"Cache-Control": "no-store, max-age=0"}


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
{_a(f"/copytrade?symbol={qsym}", "跟单简版", "copytrade")}
{_a(f"/pullback_watch?symbol={qsym}", "回调观察台", "pullback")}
{_a("/daily_review", "每日复盘", "daily_review")}
{_a("/memos_samples", "memos 原始样本", "memos")}
{_a("/live_state", "实盘状态", "live")}
{_a("/teacher_boost", "带单老师·起号", "teacher_boost")}
{_a("/teacher_combat", "带单老师·实操", "teacher_combat")}
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
    mt = str(r.get("markov_template") or "").strip()
    if mt:
        bits.append(f"模板:{mt}")
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
    """以 TP1 与 SL 相对入场距离估算 RR（毛/净），做多/做空对称；净 RR 扣双边手续费口径。"""
    try:
        e = float(r.get("entry", 0))
        sl = float(r.get("sl", 0))
        tp1 = float(r.get("tp1", 0))
        d = str(r.get("direction") or "")
        if e <= 0:
            return "—"
        if d == "做空":
            risk = abs(sl - e) / e * 100
            rew = abs(e - tp1) / e * 100
        else:
            risk = abs(e - sl) / e * 100
            rew = abs(tp1 - e) / e * 100
        if risk < 1e-9:
            return "—"
        g = rew / risk
        n = max(0.0, g - _MEMOS_FEE_PCT / max(risk, 1e-9))
        return f"{g:.2f}/{n:.2f}"
    except Exception:
        return "—"


def _normalize_bracket_cr(raw: object) -> str:
    """落库 close_reason 大小写不一（sl / SL）时统一为 TP1…/SL。"""
    s = str(raw or "").strip().upper()
    if s in ("SL", "TP1", "TP2", "TP3", "BE"):
        return s
    return ""


def _exit_direction_for_levels(r: dict) -> str:
    """与 first_exit_tick / 虚拟平仓一致：模拟入场按做多判价位。"""
    d = str(r.get("direction") or "做多")
    if d == "模拟入场":
        return "做多"
    return d


def _infer_close_reason_from_levels(r: dict) -> str:
    """与 live_trading / first_exit_tick 判定顺序一致（SL 优先于 TP3/TP2/TP1）。"""
    try:
        c = float(r.get("close"))
    except (TypeError, ValueError):
        return ""
    d = _exit_direction_for_levels(r)
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


def _infer_close_reason_tp_only(r: dict) -> str:
    """只根据 TP 档位与平仓价推断止盈档（不判 SL），用于毛盈亏为正但与止损推断冲突时。"""
    try:
        c = float(r.get("close"))
    except (TypeError, ValueError):
        return ""
    d = _exit_direction_for_levels(r)
    try:
        tp1 = float(r["tp1"])
        tp2 = float(r["tp2"])
        tp3 = float(r["tp3"])
    except Exception:
        return ""
    if d == "做多":
        if c >= tp3:
            return "TP3"
        if c >= tp2:
            return "TP2"
        if c >= tp1:
            return "TP1"
    elif d == "做空":
        if c <= tp3:
            return "TP3"
        if c <= tp2:
            return "TP2"
        if c <= tp1:
            return "TP1"
    return ""


def _resolved_close_bracket(r: dict) -> str:
    """统一解析平仓档位：规范化字段、按价位推断，并与毛盈亏符号对齐（结果列与分桶统计共用）。"""
    if r.get("profit") is None:
        return ""
    cr = _normalize_bracket_cr(r.get("close_reason"))
    if not cr:
        cr = _infer_close_reason_from_levels(r)
    try:
        pnl = float(r.get("profit") or 0)
    except (TypeError, ValueError):
        pnl = 0.0
    if pnl < 0 and cr in ("TP1", "TP2", "TP3"):
        cr = "SL"
    if pnl > 0 and cr == "SL":
        tp = _infer_close_reason_tp_only(r)
        cr = tp if tp else "TP1"
    return cr


def _result_cn(r: dict) -> str:
    if r.get("profit") is None:
        return "未平"
    cr = _resolved_close_bracket(r)
    raw_cr = str(r.get("close_reason") or "").strip().lower()
    if cr in ("TP1", "TP2", "TP3"):
        return f"止盈·{cr}"
    if cr == "BE":
        return "保本·BE"
    if cr == "SL":
        return "止损·SL"
    # 结构风控提前离场（close_reason 常见为 structure_exit:...）
    if raw_cr.startswith("structure_exit"):
        return "提前离场·结构"
    return "—"


def _tp1_be_status_cn(r: dict) -> str:
    """展示用：TP1/BE 状态（重点用于识别“未平但已TP1并抬到BE”）。"""
    if r.get("tp1_hit") is True:
        if r.get("profit") is None:
            return "TP1已触发·持仓中"
        return "TP1已触发"
    if r.get("experiment_tp1_done") is True:
        if r.get("profit") is None:
            return "TP1已触发·BE保护中"
        return "TP1已触发"
    cr = _resolved_close_bracket(r)
    if cr == "BE":
        return "已保本平仓·BE"
    # 兜底推断：做多 SL 上移到 >= entry / 做空 SL 下移到 <= entry，视为已进入 BE 保护
    if r.get("profit") is None:
        try:
            d = str(r.get("direction") or "")
            e = float(r.get("entry"))
            s = float(r.get("sl"))
            if (d.startswith("做多") and s >= e) or (d.startswith("做空") and s <= e):
                return "疑似TP1后·BE保护中"
        except Exception:
            pass
    return "—"


def _tp1_be_time_cn(r: dict) -> str:
    """展示用：TP1/BE关键时间（优先 TP1 命中时间，其次 BE 平仓时间）。"""
    tp1_time = r.get("tp1_hit_time") or r.get("experiment_tp1_time")
    if tp1_time:
        return _iso_to_bj_display(tp1_time)
    cr = _resolved_close_bracket(r)
    if cr == "BE" and r.get("close_time"):
        return _iso_to_bj_display(r.get("close_time"))
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


def _main_pool_regime_close_symbol_pivot_html(limit: int = 45) -> str:
    """主观察池已平仓样本：regime × close_reason × symbol 透视（只读，不改交易逻辑）。"""
    rows = _load_trades_flat()
    closed: list[dict] = []
    for r in rows:
        if r.get("virtual_signal") is not True:
            continue
        if r.get("profit") is None:
            continue
        ct = str(r.get("close_time") or "")
        if not ct or ct == "—":
            continue
        closed.append(r)
    if not closed:
        return '<p class="muted">暂无已平仓主观察池样本。</p>'
    agg: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {"n": 0.0, "sum": 0.0}
    )
    for r in closed:
        reg = str(r.get("regime") or "unknown").strip() or "unknown"
        cr = str(r.get("close_reason") or "UNKNOWN").strip() or "UNKNOWN"
        sym = str(r.get("symbol") or "UNKNOWN").strip() or "UNKNOWN"
        try:
            p = float(r.get("profit"))
        except Exception:
            continue
        key = (reg, cr, sym)
        agg[key]["n"] += 1.0
        agg[key]["sum"] += p
    ranked: list[tuple[float, float, str, str, str]] = []
    for (reg, cr, sym), v in agg.items():
        ranked.append((float(v["sum"]), float(v["n"]), reg, cr, sym))
    ranked.sort(key=lambda x: x[0])
    ranked = ranked[:limit]
    lines: list[str] = []
    for sm, n, reg, cr, sym in ranked:
        lines.append(
            "<tr>"
            f"<td>{html.escape(reg)}</td>"
            f"<td>{html.escape(cr)}</td>"
            f"<td>{html.escape(sym)}</td>"
            f"<td>{int(n)}</td>"
            f"<td>{_fmt_pct(sm, 2)}</td>"
            "</tr>"
        )
    cmd = (
        "python3 - <<'PY'\n"
        "import json\nfrom pathlib import Path\nfrom collections import defaultdict\n"
        "obj=json.loads(Path('trade_memory.json').read_text(encoding='utf-8'))\n"
        "rows=obj.get('trades', obj) if isinstance(obj, dict) else obj\n"
        "agg=defaultdict(lambda:{'n':0,'s':0.0})\n"
        "for r in rows:\n"
        "    if not isinstance(r, dict) or r.get('virtual_signal') is not True:\n"
        "        continue\n"
        "    if r.get('profit') is None:\n"
        "        continue\n"
        "    ct=str(r.get('close_time') or '')\n"
        "    if not ct or ct=='—':\n"
        "        continue\n"
        "    k=(str(r.get('regime') or 'unknown'), str(r.get('close_reason') or 'UNKNOWN'), str(r.get('symbol') or 'UNKNOWN'))\n"
        "    agg[k]['n']+=1\n"
        "    agg[k]['s']+=float(r['profit'])\n"
        "for (reg, cr, sym), v in sorted(agg.items(), key=lambda kv: kv[1]['s'])[:40]:\n"
        "    print(reg, cr, sym, v['n'], round(v['s'], 4))\n"
        "PY"
    )
    meta = (
        f'<p class="muted">已平仓主观察池：<b>{len(closed)}</b>；透视组合数：<b>{len(agg)}</b>；'
        f"表内展示 <b>净合计%</b> 最差前 <b>{len(ranked)}</b> 组（<code>regime × close_reason × symbol</code>）。"
        " 历史无细分 regime 的样本为 <code>unknown</code>；<b>重启服务后</b>新开/新平仓会逐步写入真实 <code>regime</code>。</p>"
    )
    table = (
        '<table class="data-table dense"><thead><tr>'
        "<th>regime</th><th>平仓原因</th><th>symbol</th><th>笔数</th><th>净合计%</th>"
        f'</tr></thead><tbody>{"".join(lines)}</tbody></table>'
    )
    tmpl = f'<pre class="muted" style="font-size:0.7rem;line-height:1.35">{html.escape(cmd)}</pre>'
    return meta + table + tmpl


def _experiment_open_rows_today(today_bj: str) -> list[dict]:
    """规则实验轨未平仓单 → 与 trade_memory 同形宽表行，便于首页与已落库单并列展示。"""
    try:
        from evolution_core import ai_evo
    except Exception:
        return []
    import time as _time

    out: list[dict] = []
    for ot in ai_evo.memory.open_trades:
        sym = str(ot.get("symbol") or "").strip()
        rp = 6 if sym else 2
        try:
            et_ts = float(ot.get("entry_time") or _time.time())
        except Exception:
            et_ts = _time.time()
        et = datetime.fromtimestamp(et_ts, tz=timezone.utc)
        if et.astimezone(_BJ).strftime("%Y-%m-%d") != today_bj:
            continue
        def _rnd(x: object) -> object:
            try:
                return round(float(x), rp)
            except Exception:
                return x

        row = {
            "date": today_bj,
            "entry_time": et.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "close_time": "—",
            "direction": ot.get("direction"),
            "entry": _rnd(ot.get("entry")),
            "sl": _rnd(ot.get("sl")),
            "tp1": _rnd(ot.get("tp1")),
            "tp2": _rnd(ot.get("tp2")),
            "tp3": _rnd(ot.get("tp3")),
            "close": None,
            "profit": None,
            "virtual_signal": False,
            "symbol": sym,
            "levels_source": ot.get("levels_source"),
            "experiment_tp1_done": ot.get("experiment_tp1_done"),
            "experiment_partial_ratio": ot.get("experiment_partial_ratio"),
            "experiment_tp1_time": ot.get("experiment_tp1_time"),
            "markov_template": ot.get("markov_template"),
            "experiment_markov_template_enabled": ot.get(
                "experiment_markov_template_enabled"
            ),
            "fib_0_618": ot.get("fib_0_618"),
            "fib_1_618_up": ot.get("fib_1_618_up"),
            "fib_1_618_down": ot.get("fib_1_618_down"),
        }
        out.append(row)
    return out


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


def _memo_cal_day_bj(r: dict) -> Optional[str]:
    """trade_memory 单行对应的北京日历日（优先 `date`，否则从 `entry_time` 解析）。"""
    ds = str(r.get("date") or "").strip()
    if len(ds) >= 10:
        return ds[:10]
    et = str(r.get("entry_time") or "").strip()
    if not et:
        return None
    try:
        dt = datetime.fromisoformat(et.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_BJ).strftime("%Y-%m-%d")
    except Exception:
        return None


def _memos_reflect_bar_html() -> str:
    """首页靠前展示：换日说明 + 反思建议（与下方 memos 统计同源）。"""
    def _is_experiment_row(r: dict) -> bool:
        if not isinstance(r, dict):
            return False
        # 历史数据存在“实验轨也被写成 virtual_signal=True”的遗留口径；
        # 通过结构化平仓原因兜底识别实验轨，避免前台长期显示样本不足。
        cr = str(r.get("close_reason") or "").lower()
        if "structure_exit:" in cr:
            return True
        if r.get("virtual_signal") is False:
            return True
        return False

    try:
        trades = _load_trades_flat()
        exp_closed = [r for r in trades if _is_experiment_row(r) and r.get("profit") is not None]
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
    def _is_experiment_row(r: dict) -> bool:
        if not isinstance(r, dict):
            return False
        cr = str(r.get("close_reason") or "").lower()
        if "structure_exit:" in cr:
            return True
        if r.get("virtual_signal") is False:
            return True
        return False

    exp = [r for r in trades if _is_experiment_row(r)]
    vir = [r for r in trades if not _is_experiment_row(r)]
    exp_closed = [r for r in exp if r.get("profit") is not None]
    vir_closed = [r for r in vir if r.get("profit") is not None]
    vir_open = [r for r in vir if r.get("profit") is None]

    exp_today = [r for r in exp if r.get("date") == today_bj]
    exp_open_ui = _experiment_open_rows_today(today_bj)
    _seen: set[tuple[Any, Any]] = {
        (str(r.get("symbol") or ""), str(r.get("entry_time") or "")) for r in exp_today
    }
    for r in exp_open_ui:
        k = (str(r.get("symbol") or ""), str(r.get("entry_time") or ""))
        if k not in _seen:
            exp_today.append(r)
            _seen.add(k)
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

    def _net_p(g: float) -> float:
        return g - _MEMOS_FEE_PCT

    exp_hist_closed_n = len(
        [
            r
            for r in exp_closed
            if _memo_cal_day_bj(r) not in (None, today_bj)
        ]
    )
    vir_hist_closed_n = len(
        [
            r
            for r in vir_closed
            if _memo_cal_day_bj(r) not in (None, today_bj)
        ]
    )
    vir_date_unknown_n = len([r for r in vir_closed if _memo_cal_day_bj(r) is None])
    exp_date_unknown_n = len([r for r in exp_closed if _memo_cal_day_bj(r) is None])

    # —— 规则实验轨（非虚拟）：与主观察池同构指标（净胜率按同一 0.16% 双边估算，便于对比）——
    el_all_g, es_all_g = _long_short_wr(exp_closed)
    e_gross_wr = _win_rate_pct(exp_closed)
    e_net_wr = (
        f"{round(len([r for r in exp_closed if _net_p(float(r.get('profit') or 0)) > 0]) / len(exp_closed) * 100, 2)}%"
        if exp_closed
        else "—"
    )
    el_all_n = (
        f"{round(len([r for r in exp_closed if str(r.get('direction','')).startswith('做多') and _net_p(float(r.get('profit') or 0)) > 0]) / max(1, len([r for r in exp_closed if str(r.get('direction','')).startswith('做多')])) * 100, 2)}%"
        if any(str(r.get("direction", "")).startswith("做多") for r in exp_closed)
        else "—"
    )
    es_all_n = (
        f"{round(len([r for r in exp_closed if str(r.get('direction','')).startswith('做空') and _net_p(float(r.get('profit') or 0)) > 0]) / max(1, len([r for r in exp_closed if str(r.get('direction','')).startswith('做空')])) * 100, 2)}%"
        if any(str(r.get("direction", "")).startswith("做空") for r in exp_closed)
        else "—"
    )
    et_gross_wr = _win_rate_pct(exp_today_closed)
    et_net_wr = (
        f"{round(len([r for r in exp_today_closed if _net_p(float(r.get('profit') or 0)) > 0]) / len(exp_today_closed) * 100, 2)}%"
        if exp_today_closed
        else "—"
    )
    exp_today_open = [r for r in exp_today if r.get("profit") is None]

    # —— 主观察池（虚拟）：毛 / 净 ——
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

    sum_net_today = sum(_net_p(float(r.get("profit") or 0)) for r in vir_today_closed)
    avg_net_today = sum_net_today / len(vir_today_closed) if vir_today_closed else 0.0
    n_closed_today = len(vir_today_closed)

    # 平仓结构 & 分桶（主观察池·当日，与宽表「结果」列同一套档位解析）
    buckets = {"TP1": [], "TP2": [], "TP3": [], "SL": []}
    for r in vir_today_closed:
        cr = _resolved_close_bracket(r)
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

    n_exp_closed_today = len(exp_today_closed)
    sum_exp_net_today = sum(_net_p(float(r.get("profit") or 0)) for r in exp_today_closed)
    avg_exp_net_today = sum_exp_net_today / n_exp_closed_today if n_exp_closed_today else 0.0

    ebuckets: dict[str, list[dict]] = {"TP1": [], "TP2": [], "TP3": [], "SL": []}
    for r in exp_today_closed:
        cr = _resolved_close_bracket(r)
        if cr in ebuckets:
            ebuckets[cr].append(r)
        else:
            ebuckets.setdefault("其他", []).append(r)

    def _ebucket_line(label: str, rows: list[dict]) -> str:
        if not rows:
            return f"<b>{label}</b>：0 笔（0.0%）均毛 —"
        pct = len(rows) / n_exp_closed_today * 100 if n_exp_closed_today else 0
        avg = sum(float(x.get("profit") or 0) for x in rows) / len(rows)
        return f"<b>{label}</b>：{len(rows)} 笔（{pct:.1f}%）均毛 {avg:+.4f}%"

    egross_bin1 = len([r for r in exp_today_closed if float(r.get("profit") or 0) <= 0])
    egross_bin2 = len(
        [r for r in exp_today_closed if 0 < float(r.get("profit") or 0) <= 0.16]
    )
    egross_bin3 = len(
        [
            r
            for r in exp_today_closed
            if 0.16 < float(r.get("profit") or 0) <= 0.25
        ]
    )
    egross_bin4 = len([r for r in exp_today_closed if float(r.get("profit") or 0) > 0.25])

    ehint = ""
    if exp_today_closed and et_gross_wr != et_net_wr:
        ehint = (
            "辨别提示（毛/净胜率）：若部分单子毛盈亏略高于 0 但低于双边手续费合计 "
            f"{_MEMOS_FEE_PCT}%，则净结果可能为亏，净胜率会低于毛胜率；详见下方「毛盈亏分桶」。"
        )

    sec1 = f"""
<table class="metrics">
<tr><td colspan="2"><strong>一、规则实验轨</strong>（<code>virtual_signal</code> 为假：本地 memos，用于大版本同步后的规则/门槛实验，与主观察池统计分列）</td></tr>
<tr><td>总交易（累计已平仓笔数）</td><td>{len(exp_closed)}</td></tr>
<tr><td>其中·历史已平仓（早于今日）</td><td>{exp_hist_closed_n}</td></tr>
<tr><td>总赢 / 总亏</td><td>{len([r for r in exp_closed if float(r.get('profit') or 0) > 0])} / {len([r for r in exp_closed if float(r.get('profit') or 0) <= 0])}</td></tr>
<tr><td>总胜率（毛）</td><td>{e_gross_wr}</td></tr>
<tr><td>总胜率（净·已扣双边手续费）</td><td>{e_net_wr}</td></tr>
<tr><td>累计做多（已平笔数 / 毛 · 净）</td><td>{len([r for r in exp_closed if str(r.get('direction','')).startswith('做多')])} 笔 · 毛 {el_all_g} · 净 {el_all_n}</td></tr>
<tr><td>累计做空（已平笔数 / 毛 · 净）</td><td>{len([r for r in exp_closed if str(r.get('direction','')).startswith('做空')])} 笔 · 毛 {es_all_g} · 净 {es_all_n}</td></tr>
<tr><td>今日条数（含未平）</td><td>{len(exp_today)}</td></tr>
<tr><td>今日未平仓</td><td>{len(exp_today_open)}</td></tr>
<tr><td>今日已平仓</td><td>{len(exp_today_closed)}</td></tr>
<tr><td>今日赢 / 亏（毛·仅价差%）</td><td>{len([r for r in exp_today_closed if float(r.get('profit') or 0) > 0])} / {len([r for r in exp_today_closed if float(r.get('profit') or 0) <= 0])}</td></tr>
<tr><td>今日胜率（毛）</td><td>{et_gross_wr if exp_today_closed else '—'}</td></tr>
<tr><td>今日赢 / 亏（净·已扣双边手续费）</td><td>{len([r for r in exp_today_closed if _net_p(float(r.get('profit') or 0)) > 0])} / {len([r for r in exp_today_closed if _net_p(float(r.get('profit') or 0)) <= 0])}</td></tr>
<tr><td>今日胜率（净）</td><td>{et_net_wr if exp_today_closed else '—'}</td></tr>
<tr><td>辨别提示（毛/净胜率）</td><td>{html.escape(ehint) if ehint else '—'}</td></tr>
<tr><td>今日总盈亏%（平均单笔 · 合计百分点）</td><td>平均单笔 {avg_exp_net_today:.4f}% · 合计百分点 {sum_exp_net_today:.4f}%（每笔已扣双边合计 {_MEMOS_FEE_PCT}%）</td></tr>
<tr><td>今日·平仓结构（笔数 / 占比 / 均毛%）</td><td>{_ebucket_line('TP1', ebuckets['TP1'])}；{_ebucket_line('TP2', ebuckets['TP2'])}；{_ebucket_line('TP3', ebuckets['TP3'])}；{_ebucket_line('SL', ebuckets['SL'])}</td></tr>
<tr><td>今日·毛盈亏分桶（占已平%）</td><td>
毛≤0%：{egross_bin1} 笔（{egross_bin1/n_exp_closed_today*100 if n_exp_closed_today else 0:.1f}%）；
0&lt;毛≤0.16%：{egross_bin2} 笔；
0.16%&lt;毛≤0.25%：{egross_bin3} 笔；
毛&gt;0.25%：{egross_bin4} 笔
</td></tr>
<tr><td>今日做多（已平笔数 / 毛 · 净）</td><td>{len([r for r in exp_today_closed if str(r.get('direction','')).startswith('做多')])} 笔 · {_win_rate_pct([r for r in exp_today_closed if str(r.get('direction','')).startswith('做多')])} · 净胜率见上表</td></tr>
<tr><td>今日做空（已平笔数 / 毛 · 净）</td><td>{len([r for r in exp_today_closed if str(r.get('direction','')).startswith('做空')])} 笔 · {_win_rate_pct([r for r in exp_today_closed if str(r.get('direction','')).startswith('做空')])} · 净胜率见上表</td></tr>
</table>
"""

    sec2 = f"""
<table class="metrics" style="margin-top:12px">
<tr><td colspan="2"><strong>二、主观察池</strong>（<code>virtual_signal</code> 为真：与决策页信号对齐，大版本外以微调为主，统计独立）</td></tr>
<tr><td>总交易（累计已平仓笔数）</td><td>{len(vir_closed)}</td></tr>
<tr><td>其中·历史已平仓（早于今日）</td><td>{vir_hist_closed_n}</td></tr>
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
<tr><td>今日总盈亏%（平均单笔 · 合计百分点）</td><td>平均单笔 {avg_net_today:.4f}% · 合计百分点 {sum_net_today:.4f}%（每笔已扣双边合计 {_MEMOS_FEE_PCT}%）</td></tr>
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

    # 当日宽表：时间升序，最多各 20 条（多则保留时间最晚的 N 条）
    main_rows = _sort_entries(vir_today)
    if len(main_rows) > 20:
        main_rows = main_rows[-20:]
    exp_rows = _sort_entries(exp_today)
    if len(exp_rows) > 20:
        exp_rows = exp_rows[-20:]

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
        tp1_be = html.escape(_tp1_be_status_cn(r))
        tp1_be_time = html.escape(_tp1_be_time_cn(r))
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
            f"<td>{tp1_be}</td><td>{tp1_be_time}</td>"
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
<th>平仓价</th><th>毛盈亏（%）</th><th>手续费（%）</th><th>净盈亏（%）</th><th>TP1/BE状态</th><th>TP1/BE时间</th><th>结果</th>
</tr></thead>
<tbody>{mh or '<tr><td colspan="19">本日暂无记录</td></tr>'}</tbody>
</table>
"""

    tbl_exp = f"""
<p style="margin-top:14px"><b>规则实验轨（仅当日 · 最多 20 条）</b></p>
<p class="muted" style="margin:4px 0 8px 0">北京时间当日已平/未平；时间升序，最新在底部；北京 0 点后换日累计。</p>
<table class="data-table dense">
<thead><tr>
<th>序号</th><th>轨道</th><th>入场时间（北京）</th><th>平仓时间（北京）</th><th>方向·标的</th>
<th>入场价</th><th>SL</th><th>TP1</th><th>TP2</th><th>TP3</th><th>价位来源</th><th>RR（毛/净）</th>
<th>平仓价</th><th>毛盈亏（%）</th><th>手续费（%）</th><th>净盈亏（%）</th><th>TP1/BE状态</th><th>TP1/BE时间</th><th>结果</th>
</tr></thead>
<tbody>{eh or '<tr><td colspan="19">本日暂无记录</td></tr>'}</tbody>
</table>
"""

    _unk_parts: list[str] = []
    if vir_date_unknown_n:
        _unk_parts.append(
            f"另有 {vir_date_unknown_n} 笔主观察池已平仓缺少可解析日期，未计入「历史/今日」拆行。"
        )
    if exp_date_unknown_n:
        _unk_parts.append(
            f"另有 {exp_date_unknown_n} 笔规则实验轨已平仓缺少可解析日期，未计入「历史/今日」拆行。"
        )
    unk_note = " ".join(_unk_parts)
    hist_same_note = ""
    if vir_closed and vir_hist_closed_n == 0 and len(vir_today_closed) > 0:
        hist_same_note = (
            "「累计已平仓」与「今日已平仓」笔数一致且「历史已平仓」为 0 时，表示当前 trade_memory.json "
            "中没有更早日历日的已平仓主观察池样本（常见于更换或清空文件）。"
            "若今日曾出现同秒刷屏异常单，累计与今日也会被抬高；可从备份恢复或删除重复行后再看统计。"
        )
    _foot_extra = " ".join(x for x in (unk_note, hist_same_note) if x)
    _foot_extra_html = f"<br/>{html.escape(_foot_extra)}" if _foot_extra else ""

    foot = f"""
<p class="muted" style="margin-top:14px;font-size:0.86rem;line-height:1.55">
说明：以下为本地 <code>trade_memory.json</code> 中的 memos 记录（两轨均为模拟记账，非交易所成交回报）。
手续费按展示口径双边合计 0.16% 估算净盈亏；「历史/今日」拆行优先用记录 <code>date</code>，缺省时用 <code>entry_time</code> 转北京时间。
「累计已平仓」= 全文件内该轨全部已平仓笔数（不限日期）；「其中·历史已平仓」为 0 且今日有大量已平时，多为文件内无更早样本或今日含异常刷屏单。
{_foot_extra_html}
「主观察池」虚拟平仓按各标的 <code>symbol</code> 独立用现价撮合；若历史记录曾在多币种并存时出现盈亏与止损/止盈不一致，多为旧版错误地用单一价格去扫全表所致，已修复。
「规则实验轨」若长期笔数很少或为空，通常因当前服务主路径未接入该轨写入链路，属设计分叉而非页面故障；详见仓库 <code>docs/trade_memory_two_tracks.md</code>。
</p>
"""
    return sec1 + sec2 + tbl_main + tbl_exp + foot


def _memos_banner_html() -> str:
    """紫色横幅：系统说明 + 元信息；导航链接已移至顶栏 _top_entry_strip，避免重复。"""
    return f"""<div class="memos-banner">
<strong>{html.escape(MEMOS_BANNER)}</strong>
<p class="memos-banner-meta muted">换日请至当日列表 · 约每 45 秒更新（随决策页加载刷新）</p>
</div>"""


def _meta_source_zh(raw: object) -> str:
    """数据源展示名（与底层字段对应，仅用于页面中文）。"""
    s = str(raw or "").strip()
    if s == "gateio_ccxt_v316":
        return f"Gate.io · CCXT（数据层 {ENGINE_VERSION}）"
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
    from pathlib import Path

    def _fmt_utc(ts: float) -> str:
        try:
            if ts <= 0:
                return "—"
            return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return "—"

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
    src_meta = Path(__file__).resolve().parent / "hermes_outbox" / "hft_strategy_skill_library.meta.json"
    src_md = Path(__file__).resolve().parent / "hermes_outbox" / "hft_strategy_skill_library.md"
    src_meta_ts = _fmt_utc(src_meta.stat().st_mtime) if src_meta.exists() else "—"
    src_md_ts = _fmt_utc(src_md.stat().st_mtime) if src_md.exists() else "—"
    source_hint = f"源meta更新 {src_meta_ts} · 源md更新 {src_md_ts}"
    if ing and src_meta.exists():
        try:
            ing_dt = datetime.strptime(ing, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if src_meta.stat().st_mtime <= ing_dt.timestamp() + 1:
                source_hint += " · 源未变化（无需重入脑）"
            else:
                source_hint += " · 检测到源更新（建议重跑入脑）"
        except Exception:
            pass
    return (
        f"节选 {n} 条 · sha256 {short_sha} · 入脑时间 {ing or '—'} · {source_hint} · 预览：{pv or '—'}"
    )


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


def _risk_advisory_html(km: dict, profile: str = "main") -> str:
    bundle = km.get("risk_advisory_bundle") if isinstance(km, dict) else {}
    adv = bundle.get(profile) if isinstance(bundle, dict) else None
    if not isinstance(adv, dict):
        adv = km.get("risk_advisory") if isinstance(km, dict) else {}
    if not isinstance(adv, dict) or not adv:
        return '<p class="muted">风险真理层：暂无可用建议。</p>'
    warnings = adv.get("warnings") or []
    wtxt = "、".join(str(x) for x in warnings) if warnings else "无"
    return (
        "<table class=\"metrics\">"
        f"<tr><td>模式</td><td>{html.escape(str(adv.get('mode', 'observe')))}</td></tr>"
        f"<tr><td>板块画像</td><td>{html.escape(profile)}</td></tr>"
        f"<tr><td>建议风险金</td><td>{html.escape(str(round(float(adv.get('risk_usdt', 0.0) or 0.0), 4)))} USDT</td></tr>"
        f"<tr><td>建议名义仓位</td><td>{html.escape(str(round(float(adv.get('suggested_notional_usdt', 0.0) or 0.0), 4)))} USDT</td></tr>"
        f"<tr><td>建议杠杆 / 上限</td><td>{html.escape(str(adv.get('recommended_leverage', '—')))} / {html.escape(str(adv.get('max_allowed_leverage', '—')))}</td></tr>"
        f"<tr><td>有效止损比例</td><td>{html.escape(str(round(float(adv.get('effective_stop_pct', 0.0) or 0.0) * 100.0, 4)))}%</td></tr>"
        f"<tr><td>风险提示</td><td>{html.escape(wtxt)}</td></tr>"
        "</table>"
    )


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


def _daily_strategy_review_block() -> str:
    """读取 scripts/daily_strategy_review.py 产物：异常预警 + 小步建议摘要（只读）。"""
    root = Path(__file__).resolve().parent
    p = root / "outputs" / "daily_strategy_review" / "latest_daily_review.json"
    if not p.exists():
        return (
            '<p class="muted" style="margin-top:12px"><b>每日策略复盘</b>：尚未生成。'
            "服务器执行 <code>bash scripts/run_daily_review.sh</code> 后刷新本页；"
            '详见 <a href="/daily_review">完整报告页</a>。</p>'
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return f'<p class="muted">每日复盘读取失败：{html.escape(str(e))}</p>'
    mt = data.get("main_track") or {}
    today = mt.get("today") or {}
    alerts = data.get("alerts") or []
    gen = html.escape(str(data.get("generated_at_utc") or "—"))
    bjd = html.escape(str(data.get("bj_calendar_date") or "—"))
    rows = [
        ["交易数", today.get("n_trades")],
        ["净胜率%", today.get("win_rate_net_pct")],
        ["平均净盈亏%", today.get("avg_net_profit_pct")],
        ["净盈亏合计%", today.get("sum_net_profit_pct")],
        ["最大回撤%（净累计）", today.get("max_drawdown_net_pct")],
        ["Sharpe（净·按笔）", today.get("sharpe_net")],
    ]
    tb = "".join(
        f"<tr><td>{html.escape(str(a))}</td><td>{html.escape(str(b))}</td></tr>"
        for a, b in rows
    )
    al_lines = (
        "<br/>".join(html.escape(a) for a in alerts[:4])
        if alerts
        else '<span class="muted">（暂无规则命中）</span>'
    )
    more = (
        f'<br/><span class="muted">…共 {len(alerts)} 条预警</span>'
        if len(alerts) > 4
        else ""
    )
    vs = data.get("vs_previous_snapshot")
    vs_html = (
        f'<p class="muted" style="margin:8px 0 4px 0">{html.escape(str(vs))}</p>'
        if vs
        else ""
    )
    return f"""<p style="margin-top:14px"><b>每日策略复盘</b>（北京日 {bjd} · 生成 UTC {gen}）
&nbsp;·&nbsp;<a href="/daily_review">完整 Markdown 报告</a></p>
{vs_html}
<table class="data-table dense"><thead><tr><th>核心指标（主观察池·今日·净）</th><th>值</th></tr></thead><tbody>{tb}</tbody></table>
<p style="margin-top:10px"><b>异常预警（摘录）</b></p><p style="line-height:1.6">{al_lines}{more}</p>
<p class="muted" style="font-size:0.86rem;margin-top:8px">说明：与 memos 一致主池扣双边 0.16%；建议为文案级，不自动改参数。</p>"""


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

    tsu = data.get("template_summary") or {}
    if isinstance(tsu, dict) and tsu:
        rows_tpl: List[List[Any]] = []
        for tpl in sorted(tsu.keys(), key=lambda s: str(s)):
            m = tsu.get(tpl) or {}
            if not isinstance(m, dict):
                continue
            rows_tpl.append(
                [
                    tpl,
                    m.get("runs"),
                    m.get("avg_total_trades"),
                    m.get("avg_win_rate_pct"),
                    m.get("avg_sum_profit_pct"),
                ]
            )
        chunks.append(
            _html_table_from_rows(
                "一（附）实验轨 Markov 模板汇总（仅 experiment 行）",
                ["模板", "run 数", "平均单量", "平均胜率%", "平均合计盈亏%"],
                rows_tpl,
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
                r.get("markov_template"),
                r.get("entry_cooldown_bars"),
                r.get("total_trades"),
                r.get("win_rate_pct"),
                r.get("sum_profit_pct"),
            ]
        )
    chunks.append(
        _html_table_from_rows(
            "二、各币种最优候选（按胜率为主，需满足 min_trades_report）",
            ["标的", "模式", "Markov模板", "冷却(根)", "单量", "胜率%", "合计盈亏%"],
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
                r.get("markov_template"),
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
                "Markov模板",
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
                r.get("markov_template"),
                r.get("entry_cooldown_bars"),
                r.get("total_trades"),
                r.get("win_rate_pct"),
                r.get("sum_profit_pct"),
            ]
        )
    chunks.append(
        _html_table_from_rows(
            "四、全局候选 Top（启发式排序：胜率 × √(单量)）",
            ["标的", "模式", "Markov模板", "冷却(根)", "单量", "胜率%", "合计盈亏%"],
            rows_t,
        )
    )

    moc = str(data.get("markov_optimized_compare_text") or "")
    if moc:
        chunks.append(
            '<p class="muted" style="margin:12px 0 4px 0">五、策略层 Markov 阈值模板关/开对比（矩阵需 <code>--also-threshold-template-compare</code>）</p>'
            f'<p class="muted" style="margin:0 0 8px 0;line-height:1.55">{html.escape(moc)}</p>'
        )

    return "\n".join(chunks)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    try:
        from live_trading import start_live_bot_background

        start_live_bot_background()
    except Exception as e:
        print(f"[warn] start_live_bot_background: {e}")
    bn_task = None
    try:
        from data.binance_reference import refresh_binance_reference_cache

        async def _binance_refresh_loop() -> None:
            while True:
                try:
                    await asyncio.to_thread(refresh_binance_reference_cache)
                except Exception as e:
                    print(f"[warn] binance_reference refresh: {e}")
                await asyncio.sleep(45)

        bn_task = asyncio.create_task(_binance_refresh_loop())
    except Exception as e:
        print(f"[warn] binance_reference background: {e}")
    yield
    if bn_task is not None:
        bn_task.cancel()
        try:
            await bn_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="longxia_system", lifespan=lifespan)


@app.get("/api/version")
def api_engine_version():
    """对外版本锚点（监控 curl 用）；与页面「数据层」文案一致。"""
    return JSONResponse(
        {
            "engine": ENGINE_VERSION,
            "app": "longxia_system",
            "data_layer": ENGINE_VERSION,
            # 部署自检：旧进程无此字段或 ui_build 不同，即未加载含带单老师页的本版 main.py
            "ui_build": "nav-teacher-v2",
            "teacher_paths": ["/teacher_boost", "/tb", "/teacher_combat", "/tc"],
        }
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


@app.get("/teacher_comba", include_in_schema=False)
def redirect_teacher_comba_typo():
    """常见拼写错误：comba → combat（不重定向会 404）。"""
    return RedirectResponse(url="/teacher_combat", status_code=307)


_REPO = Path(__file__).resolve().parent


def _teacher_track_closed_rows(signal_track: str) -> list[dict]:
    """仅统计带业务轨标记且已平仓的 memos（signal_track 与主池/实验轨并列）。"""
    p = _REPO / "trade_memory.json"
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        rows, _ = _trade_memory_parse(raw)
    except Exception:
        return []
    st = str(signal_track).strip()
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if str(r.get("signal_track") or "").strip() != st:
            continue
        if r.get("profit") is None:
            continue
        out.append(r)
    return out


def _teacher_metrics_bundle(signal_track: str, today_bj: str) -> dict[str, Any]:
    closed = _teacher_track_closed_rows(signal_track)
    today = [r for r in closed if str(r.get("date") or "")[:10] == today_bj]
    n, nt = len(closed), len(today)
    if not closed:
        return {
            "n_closed": 0,
            "n_today": 0,
            "win_rate": "—",
            "avg_pnl": "—",
            "today_win_rate": "—",
        }
    wins = len([r for r in closed if float(r.get("profit") or 0) > 0])
    wt = len([r for r in today if float(r.get("profit") or 0) > 0])
    wr = f"{round(wins / n * 100, 2)}%"
    twr = f"{round(wt / nt * 100, 2)}%" if nt else "—"
    ap = sum(float(r.get("profit") or 0) for r in closed) / n
    return {
        "n_closed": n,
        "n_today": nt,
        "win_rate": wr,
        "avg_pnl": f"{ap:.4f}%",
        "today_win_rate": twr,
    }


def _teacher_recent_rows_html(signal_track: str, limit: int = 20) -> str:
    rows = _teacher_track_closed_rows(signal_track)

    def _k(r: dict) -> str:
        return str(r.get("close_time") or r.get("entry_time") or "")

    rows.sort(key=_k)
    tail = rows[-limit:]
    if not tail:
        return f'<tr><td colspan="7" class="muted">暂无已平仓样本。后续接入写入后需 <code>signal_track={html.escape(signal_track)}</code>。</td></tr>'
    lines: list[str] = []
    for r in tail:
        sym = html.escape(str(r.get("symbol") or "—"))
        dire = html.escape(str(r.get("direction") or "—"))
        pr = html.escape(str(r.get("profit") or "—"))
        cr = html.escape(str(r.get("close_reason") or "—"))
        dt = html.escape(str(r.get("date") or "—"))
        et = html.escape(str(r.get("entry_time") or "—")[:19])
        ct = html.escape(str(r.get("close_time") or "—")[:19])
        lines.append(
            f"<tr><td>{dt}</td><td>{sym}</td><td>{dire}</td><td>{pr}</td>"
            f"<td>{cr}</td><td>{et}</td><td>{ct}</td></tr>"
        )
    return "\n".join(lines)


def _html_teacher_track_page(
    *,
    active_strip: str,
    title: str,
    signal_track: str,
    intro: str,
    kpi_note: str,
) -> HTMLResponse:
    today_bj = datetime.now(_BJ).strftime("%Y-%m-%d")
    m = _teacher_metrics_bundle(signal_track, today_bj)
    strip = _top_entry_strip(active_strip)
    recent = _teacher_recent_rows_html(signal_track, 20)
    try:
        km = get_v313_decision_snapshot(force_refresh=True, symbol="SOL/USDT")
    except Exception:
        km = {}
    risk_profile = "teacher_boost" if signal_track == SIGNAL_TRACK_BOOST else "teacher_combat"
    risk_html = _risk_advisory_html(km, risk_profile)
    body = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>
body{{background:#0f1419;color:#e8eef7;font-family:system-ui;padding:20px;max-width:960px;margin:0 auto;}}
a{{color:#5c7cfa;}}
.top-entry-strip {{
  display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;
  margin-bottom:18px;padding:12px 16px;background:rgba(0,0,0,.28);
  border-radius:12px;border:1px solid rgba(255,255,255,.1);
}}
.top-entry{{color:#a5b4fc;text-decoration:none;font-size:0.95rem;padding:6px 14px;border-radius:10px;border:1px solid transparent;}}
.top-entry:hover{{background:rgba(255,255,255,.07);color:#fff;}}
.top-entry-active{{color:#51cf66!important;font-weight:700;border-color:rgba(81,207,102,.45);background:rgba(81,207,102,.08);}}
.muted{{color:#8b9bb4;font-size:0.92rem;line-height:1.6;}}
.card{{background:#1a2332;border-radius:12px;padding:16px 18px;margin:14px 0;border:1px solid rgba(255,255,255,.08);}}
.card h2{{margin:0 0 10px;font-size:1.05rem;}}
table.data{{width:100%;border-collapse:collapse;font-size:0.88rem;}}
table.data th,table.data td{{border:1px solid rgba(255,255,255,.12);padding:8px;text-align:left;}}
table.data th{{background:rgba(0,0,0,.25);}}
code{{color:#a5d8ff;font-size:0.85em;}}
</style></head><body>
{_HTML_BUILD_MARKER}
{strip}
<h1>{html.escape(title)}</h1>
<p class="muted">{html.escape(intro)}</p>
<div class="card">
<h2>汇总（按 <code>signal_track={html.escape(signal_track)}</code>）</h2>
<table class="data">
<tr><th>累计已平仓笔数</th><td>{m["n_closed"]}</td></tr>
<tr><th>今日已平仓（北京日）</th><td>{m["n_today"]}</td></tr>
<tr><th>累计胜率（毛）</th><td>{m["win_rate"]}</td></tr>
<tr><th>今日胜率（毛）</th><td>{m["today_win_rate"]}</td></tr>
<tr><th>累计均盈亏%</th><td>{m["avg_pnl"]}</td></tr>
<tr><th>{html.escape(kpi_note)}</th><td class="muted">待接入日收益序列 / 持仓时长后显示</td></tr>
</table>
</div>
<div class="card">
<h2>近期已平仓（最多 20 条 · 时间升序）</h2>
<table class="data">
<thead><tr><th>date</th><th>标的</th><th>方向</th><th>盈亏%</th><th>原因</th><th>入场</th><th>平仓</th></tr></thead>
<tbody>{recent}</tbody>
</table>
</div>
<div class="card">
<h2>资金/仓位/杠杆基础层（observe）</h2>
{risk_html}
</div>
<p class="muted">说明：本页为<strong>内部业务统计</strong>，与交易所对外展示无关；默认需开启写入开关并落库 <code>signal_track</code> 后才有样本。环境变量见 <code>live_trading.py</code> 顶部 <code>LONGXIA_TEACHER_*</code>。</p>
<p><a href="/decision?symbol=SOL/USDT">返回决策看板</a></p>
</body></html>"""
    return HTMLResponse(content=body, headers=_HTML_NO_CACHE_HEADERS)


@app.get("/daily_review", response_class=HTMLResponse)
def page_daily_review():
    """每日策略复盘 Markdown + JSON 路径提示（与 scripts/daily_strategy_review.py 同源）。"""
    p = _REPO / "outputs" / "daily_strategy_review" / "latest_daily_review.md"
    jp = _REPO / "outputs" / "daily_strategy_review" / "latest_daily_review.json"
    if not p.exists():
        body = (
            "<p>尚未生成。请在仓库根目录执行：</p>"
            "<pre style=\"background:#111;padding:12px;border-radius:8px\">bash scripts/run_daily_review.sh</pre>"
        )
    else:
        try:
            text = p.read_text(encoding="utf-8")
        except Exception as e:
            text = str(e)
        body = f"<pre style=\"white-space:pre-wrap;font-size:0.88rem;line-height:1.65\">{html.escape(text)}</pre>"
    jnote = (
        f'<p class="muted">JSON：<code>{html.escape(str(jp))}</code>（与页面同源）</p>'
        if jp.exists()
        else f'<p class="muted">JSON 尚未生成：<code>{html.escape(str(jp))}</code></p>'
    )
    strip = _top_entry_strip("daily_review")
    return HTMLResponse(
        f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/><title>每日策略复盘</title>
<style>
body{{background:#0f1419;color:#e8eef7;font-family:system-ui;padding:20px;max-width:920px;margin:0 auto;}}
a{{color:#5c7cfa;}}
.top-entry-strip {{
  display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;
  margin-bottom:18px;padding:12px 16px;background:rgba(0,0,0,.28);
  border-radius:12px;border:1px solid rgba(255,255,255,.1);
}}
.top-entry{{color:#a5b4fc;text-decoration:none;font-size:0.95rem;padding:6px 14px;border-radius:10px;border:1px solid transparent;}}
.top-entry:hover{{background:rgba(255,255,255,.07);color:#fff;}}
.top-entry-active{{color:#51cf66!important;font-weight:700;border-color:rgba(81,207,102,.45);background:rgba(81,207,102,.08);}}
.muted{{color:#8b9bb4;font-size:0.9rem;}}
</style></head><body>
{strip}
<h1>每日策略复盘</h1>
{jnote}
{body}
</body></html>"""
    )


@app.get("/pullback_watch", response_class=HTMLResponse)
@app.get("/pw", response_class=HTMLResponse)
def page_pullback_watch(symbol: str = Query("SOL/USDT")):
    """回调观察台：只读展示主观察池防护层与周期上下文，不下单、不额外写 memos（仅快照内既有平仓撮合）。"""
    sym = _pick_symbol(symbol)
    km = get_v313_decision_snapshot(force_refresh=True, symbol=sym)
    strip = _top_entry_strip("pullback", sym)
    nav_links: List[str] = []
    for s in SYMBOL_CHOICES:
        active = "font-weight:700;color:#ffe082;" if s == sym else "color:#9ecbff;"
        nav_links.append(
            f'<a style="{active}" href="/pullback_watch?symbol={quote(s, safe="")}">{html.escape(s)}</a>'
        )
    nav_html = "\n".join(
        f'<span style="margin-right:10px">{x}</span>' for x in nav_links
    )
    adv = km.get("advanced_indicators") if isinstance(km.get("advanced_indicators"), dict) else {}
    ema3 = adv.get("ema3_cross", "—") if isinstance(adv, dict) else "—"
    pairs: List[tuple[str, object]] = [
        ("当前标的", sym),
        ("信号标签（防护后）", km.get("signal_label")),
        ("信号标签（防护前）", km.get("signal_label_before_main_guard")),
        ("大周期趋势", km.get("big_trend")),
        ("周期判断", km.get("cycle_judgment")),
        ("RSI(1m)", km.get("rsi_1m")),
        ("一致性评分", km.get("consistency_score")),
        ("三均线 EMA13/21/60（引擎文案）", ema3),
        ("回调防护 active", km.get("main_pullback_active")),
        ("回调防护 deep", km.get("main_pullback_deep")),
        ("回调防护 direction", km.get("main_pullback_direction")),
        ("回调防护 reason", km.get("main_pullback_reason")),
        ("机械触发 mode", km.get("main_breakout_mode")),
        ("机械触发 direction", km.get("main_breakout_direction")),
        ("机械触发 reason", km.get("main_breakout_reason")),
        ("机械触发 区间高 / 低", f"{km.get('main_breakout_range_high')} / {km.get('main_breakout_range_low')}"),
        ("机械触发 上/下突破线", f"{km.get('main_breakout_up_threshold')} / {km.get('main_breakout_down_threshold')}"),
        ("机械触发 判定价 / 来源", f"{km.get('main_breakout_eval_price')} / {km.get('main_breakout_price_basis')}"),
        ("EMA 追价拦截", km.get("main_ema_chase_block")),
        ("EMA 追价说明", km.get("main_ema_chase_reason")),
        ("BTC 锚定 active", km.get("main_btc_anchor_active")),
        ("BTC 禁多 / 禁空", f"{km.get('main_btc_risk_off_long')} / {km.get('main_btc_risk_off_short')}"),
        ("BTC 高点回撤%", km.get("main_btc_drop_from_high_pct")),
        ("BTC 低点反抽%", km.get("main_btc_bounce_from_low_pct")),
        ("BTC 锚定说明", km.get("main_btc_anchor_reason")),
        ("风险真理层画像", "main"),
        ("风险建议（observe）", km.get("risk_advisory")),
    ]
    rows_html = []
    for lab, val in pairs:
        v = "—" if val is None else str(val)
        rows_html.append(
            f"<tr><td>{html.escape(lab)}</td>"
            f'<td style="word-break:break-word;line-height:1.5">{html.escape(v)}</td></tr>'
        )
    tbody = "\n".join(rows_html)
    intro = (
        "<p class=\"muted\" style=\"line-height:1.65;margin:0 0 16px 0\">"
        "本页仅汇总决策快照中与「回调 / 追单防护」相关的字段，便于观察；"
        "<b>不产生吃回调开仓单</b>。开启防护请设环境变量 "
        "<code>LONGXIA_MAIN_PULLBACK_GUARD</code>、"
        "<code>LONGXIA_MAIN_BTC_ANCHOR_GUARD</code>、"
        "<code>LONGXIA_MAIN_EMA_CHASE_GUARD</code> 等（详见 live_trading 顶部说明）。"
        "</p>"
    )
    return HTMLResponse(
        f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/><title>回调观察台 · {html.escape(sym)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
body{{background:#0f1419;color:#e8eef7;font-family:system-ui,sans-serif;padding:18px;max-width:960px;margin:0 auto;}}
a{{color:#5c7cfa;}}
h1{{font-size:1.25rem;margin:0 0 12px 0;}}
.nav-strip{{display:flex;flex-wrap:wrap;gap:6px 8px;margin-bottom:14px;padding:10px 12px;background:#1a2332;border-radius:10px;border:1px solid rgba(255,255,255,.08);}}
.muted{{color:#8b9bb4;font-size:0.92rem;}}
table.data{{width:100%;border-collapse:collapse;font-size:0.9rem;margin-top:8px;}}
table.data th, table.data td{{border:1px solid rgba(255,255,255,.12);padding:8px 10px;text-align:left;vertical-align:top;}}
table.data th{{background:rgba(0,0,0,.25);color:#c5d4e8;width:32%;}}
.top-entry-strip {{
  display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;
  margin-bottom:18px;padding:12px 16px;background:rgba(0,0,0,.28);
  border-radius:12px;border:1px solid rgba(255,255,255,.1);
}}
.top-entry{{color:#a5b4fc;text-decoration:none;font-size:0.95rem;padding:6px 14px;border-radius:10px;border:1px solid transparent;}}
.top-entry:hover{{background:rgba(255,255,255,.07);color:#fff;}}
.top-entry-active{{color:#51cf66!important;font-weight:700;border-color:rgba(81,207,102,.45);background:rgba(81,207,102,.08);}}
code{{color:#a5d8ff;font-size:0.85em;}}
</style></head><body>
{strip}
<h1>回调观察台（只读）</h1>
<div class="nav-strip">{nav_html}</div>
{intro}
<table class="data"><thead><tr><th>字段</th><th>当前值</th></tr></thead><tbody>{tbody}</tbody></table>
<p class="muted" style="margin-top:16px">短链：<a href="/pw?symbol={quote(sym, safe="")}">/pw</a> 与本页相同。</p>
</body></html>"""
    )


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


@app.get("/risk_truth_layer", response_class=HTMLResponse)
@app.get("/risk_phase1", response_class=HTMLResponse)
def page_risk_truth_layer_preview(symbol: str = Query("SOL/USDT")):
    """Phase-1 风险真理层（observe-only）预览页：用于灰度前人工确认 Web 展示。

    说明：
    - 不影响现有 `/decision` 主路径；仅新增路由便于验收对齐。
    - 数据与 `/decision` 同源：`get_v313_decision_snapshot`。
    """
    sym = _pick_symbol(symbol)
    qsym = quote(sym, safe="")
    km = get_v313_decision_snapshot(force_refresh=True, symbol=sym)

    nav_links: List[str] = []
    for s in SYMBOL_CHOICES:
        active = "font-weight:700;color:#ffe082;" if s == sym else "color:#9ecbff;"
        nav_links.append(
            f'<a style="{active}" href="/risk_truth_layer?symbol={quote(s, safe="")}">{html.escape(s)}</a>'
        )
    nav_html = "\n".join(
        f'<span style="margin-right:10px">{x}</span>' for x in nav_links
    )

    bundle = km.get("risk_advisory_bundle") if isinstance(km, dict) else {}
    bundle_json = json.dumps(bundle, ensure_ascii=False, indent=2) if isinstance(bundle, dict) else "{}"
    adv_json = json.dumps(km.get("risk_advisory") or {}, ensure_ascii=False, indent=2)

    strip = _top_entry_strip("decision", sym)
    body = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>风险真理层 Phase-1 预览 · {html.escape(sym)}</title>
<style>
body{{background:#0f1419;color:#e8eef7;font-family:system-ui,sans-serif;padding:18px;max-width:980px;margin:0 auto;}}
a{{color:#5c7cfa;}}
h1{{font-size:1.25rem;margin:0 0 12px;}}
.muted{{color:#8b9bb4;font-size:0.92rem;line-height:1.65;}}
.nav-strip{{display:flex;flex-wrap:wrap;gap:6px 8px;margin-bottom:14px;padding:10px 12px;background:#1a2332;border-radius:10px;border:1px solid rgba(255,255,255,.08);}}
.card{{background:#1a2332;border-radius:14px;padding:16px 18px;margin:14px 0;border:1px solid rgba(255,255,255,.08);}}
.card h2{{margin:0 0 10px;font-size:1.02rem;color:#a5d8ff;}}
.metrics{{width:100%;border-collapse:collapse;font-size:0.92rem;}}
.metrics td{{padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.06);}}
.metrics td:first-child{{color:#8b9bb4;width:38%;}}
pre{{white-space:pre-wrap;word-break:break-word;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.10);
  border-radius:12px;padding:12px;font-size:0.82rem;line-height:1.55;}}
code{{color:#a5d8ff;font-size:0.85em;}}
.top-entry-strip {{
  display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;
  margin-bottom:18px;padding:12px 16px;background:rgba(0,0,0,.28);
  border-radius:12px;border:1px solid rgba(255,255,255,.1);
}}
.top-entry{{color:#a5b4fc;text-decoration:none;font-size:0.95rem;padding:6px 14px;border-radius:10px;border:1px solid transparent;}}
.top-entry:hover{{background:rgba(255,255,255,.07);color:#fff;}}
.top-entry-active{{color:#51cf66!important;font-weight:700;border-color:rgba(81,207,102,.45);background:rgba(81,207,102,.08);}}
</style></head><body>
{_HTML_BUILD_MARKER}
{strip}
<h1>风险真理层 Phase-1（observe-only）Web 预览</h1>
<p class="muted">本页用于灰度前确认展示与字段；默认不进入主导航。数据与 <code>/decision</code> 同源。</p>
<p class="muted" style="margin-top:-6px">短链别名：<code>/risk_phase1</code>（与 <code>/risk_truth_layer</code> 相同）</p>

<div class="nav-strip">{nav_html}</div>

<div class="card">
<h2>主画像（main）</h2>
{_risk_advisory_html(km, "main")}
</div>

<div class="card">
<h2>实验轨画像（experiment）</h2>
{_risk_advisory_html(km, "experiment")}
</div>

<div class="card">
<h2>老师轨画像（teacher_boost / teacher_combat）</h2>
<p class="muted" style="margin-top:0">两轨若数值相同，表示 Phase-1 仍共用同一套资金真值输入（文件源）；后续若要分账再单独立项。</p>
{_risk_advisory_html(km, "teacher_boost")}
{_risk_advisory_html(km, "teacher_combat")}
</div>

<div class="card">
<h2>原始 JSON（便于你对照工单字段）</h2>
<p class="muted"><code>risk_advisory</code></p>
<pre>{html.escape(adv_json)}</pre>
<p class="muted" style="margin-top:10px"><code>risk_advisory_bundle</code></p>
<pre>{html.escape(bundle_json)}</pre>
</div>

<p class="muted">对照页：<a href="/decision?symbol={qsym}">打开正式决策页</a> · <a href="/api/version">/api/version</a></p>
</body></html>"""
    return HTMLResponse(content=body, headers=_HTML_NO_CACHE_HEADERS)


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
            sync_virtual_memos_from_state(sym, pxf, decision=km)
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
    daily_review_html = _daily_strategy_review_block()
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

    _dyn_on = dynamic_levels_enabled()
    _scaled_on = scaled_exit_enabled()
    memos_dyn_hint = (
        "已开启（LONGXIA_DYNAMIC_LEVELS）：新开虚拟单与本页参考 SL/TP 会按近期波动微调。"
        if _dyn_on
        else "未开启（默认）：固定比例档位。平仓判定顺序仍为 SL→TP3→TP2→TP1；做空路径上价格常先触及较近 TP1，故统计里多见「止盈·TP1」，属正常。"
    )
    memos_scaled_hint = (
        "已开启（LONGXIA_SCALED_EXIT）：虚拟单可能分笔止盈。"
        if _scaled_on
        else "未开启（默认）：虚拟单整笔平仓（first_exit_tick）。"
    )
    pivot_main_pool_html = _main_pool_regime_close_symbol_pivot_html()
    try:
        from data.binance_reference import binance_metrics_html_rows

        binance_metrics_rows = binance_metrics_html_rows(sym)
    except Exception:
        binance_metrics_rows = ""
    try:
        from data.third_party_reference import third_party_metrics_html_rows

        third_party_metrics_rows = third_party_metrics_html_rows(sym)
    except Exception:
        third_party_metrics_rows = ""
    confidence_text = _data_confidence_line(km)
    signal_card_text = _operator_signal_card_line(km, "live")

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
{_HTML_BUILD_MARKER}
<div class="page-wrap">
{_top_entry_strip("decision", sym)}
{_memos_banner_html()}

<div class="nav-strip">{nav_html}</div>

{_memos_reflect_bar_html()}

<h1>多币种指标看板<span class="v316-tag">· Gate.io CCXT（数据层 {html.escape(ENGINE_VERSION)}）</span></h1>
<p class="subline">当前交易对：<b>{html.escape(sym)}</b>
&nbsp;·&nbsp; 数据源 <code>{html.escape(_meta_source_zh(meta.get("source")))}</code>
&nbsp;·&nbsp; 1 分钟 K 线根数 <b>{html.escape(str(meta.get("count", "")))}</b></p>
<p class="subline" style="margin-top:-10px"><a class="nav-link" href="/ct?symbol={qsym}">短链 /ct</a>
&nbsp;·&nbsp; <span class="muted">专业数据仍在下方橙框/绿框；简版仅保留方向与价位。</span></p>

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
<tr><td>指标可信度分级</td><td>{html.escape(confidence_text)}</td></tr>
<tr><td>实操信号卡（模式）</td><td>{html.escape(signal_card_text)}</td></tr>
<tr><td>能力引擎 · 币安永续微调（已并入一致性分）</td><td>{html.escape(json_dumps_safe(km.get("binance_score_nudge") or {}))}</td></tr>
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
<tr><td>行情状态（Markov）</td><td>{html.escape(_zh_decision_copy(km.get("markov_regime_line") or "—"))}</td></tr>
<tr><td>主观察池·回调防护</td><td>active={html.escape(str(km.get("main_pullback_active", "—")))} · deep={html.escape(str(km.get("main_pullback_deep", "—")))} · dir={html.escape(str(km.get("main_pullback_direction", "—")))} · {html.escape(_zh_decision_copy(km.get("main_pullback_reason") or "—"))}</td></tr>
<tr><td>主观察池·机械触发（观察）</td><td>mode={html.escape(str(km.get("main_breakout_mode", "—")))} · dir={html.escape(str(km.get("main_breakout_direction", "—")))} · {html.escape(_zh_decision_copy(km.get("main_breakout_reason") or "—"))}</td></tr>
<tr><td>主观察池·机械触发·区间/突破线</td><td>区间高 {html.escape(str(km.get("main_breakout_range_high", "—")))} · 区间低 {html.escape(str(km.get("main_breakout_range_low", "—")))} · 上突破线 {html.escape(str(km.get("main_breakout_up_threshold", "—")))} · 下突破线 {html.escape(str(km.get("main_breakout_down_threshold", "—")))} · 判定价 {html.escape(str(km.get("main_breakout_eval_price", "—")))}（{html.escape(str(km.get("main_breakout_price_basis", "—")))}）（<span class="muted">回看 <code>LONGXIA_MAIN_BREAKOUT_*</code> · <code>LONGXIA_MAIN_BREAKOUT_SIGNAL_FILTER</code>，仅快照、不触发下单</span>）</td></tr>
<tr><td>主观察池·BTC 锚定 / EMA 追价</td><td>BTC锚={html.escape(str(km.get("main_btc_anchor_active", "—")))} 禁多={html.escape(str(km.get("main_btc_risk_off_long", "—")))} 禁空={html.escape(str(km.get("main_btc_risk_off_short", "—")))} · EMA追价拦截={html.escape(str(km.get("main_ema_chase_block", "—")))} · {html.escape(_zh_decision_copy(km.get("main_btc_anchor_reason") or km.get("main_ema_chase_reason") or "—"))}</td></tr>
<tr><td>信号标签（防护前）</td><td>{html.escape(str(km.get("signal_label_before_main_guard") or "—"))}</td></tr>
<tr><td>当前策略模板（Markov）</td><td>{html.escape(_zh_decision_copy(km.get("experiment_markov_template_line") or "—"))}</td></tr>
<tr><td>执行状态 · 信号转单同步</td><td>{html.escape(str(km.get("virtual_order_status", "—")))}</td></tr>
<tr><td>主观察池 · 动态价位</td><td>{html.escape(memos_dyn_hint)}</td></tr>
<tr><td>主观察池 · 分批止盈</td><td>{html.escape(memos_scaled_hint)}</td></tr>
<tr><td>数据新鲜度 · Gate 现货 ticker 报价时间（北京）</td><td>{html.escape(ticker_quote_bj)}</td></tr>
<tr><td>K 线拉取实现</td><td>{html.escape(klines_impl_line)}</td></tr>
{binance_metrics_rows}
{third_party_metrics_rows}
</table></div>

<div class="card green">
{v314_signal_html}
</div>

<div class="card">
<h2>资金/仓位/杠杆基础层（observe）</h2>
{_risk_advisory_html(km, "main")}
</div>

<div class="card">
<h2>主观察池样本透视（regime × 平仓原因 × 币）</h2>
{pivot_main_pool_html}
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
{daily_review_html}
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
    return HTMLResponse(content=body, headers=_HTML_NO_CACHE_HEADERS)


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


def _copytrade_side(km: dict) -> str:
    sig = str(km.get("signal_label") or "")
    if sig.startswith("偏空"):
        return "做空"
    if sig.startswith("偏多"):
        return "做多"
    return "—"


def _copytrade_advice_title(km: dict) -> str:
    sig = str(km.get("signal_label") or "无")
    if "（强）" in sig:
        return "信号较强 · 可参考方向挂单（控制仓位）"
    if sig.startswith("偏多") or sig.startswith("偏空"):
        return "信号较轻 · 建议轻仓或观望"
    return "无明确强信号 · 建议观望"


def _copytrade_rr_gross_one_line(entry: float, sl: float, tp1: float, side: str) -> str:
    try:
        e, s, t = float(entry), float(sl), float(tp1)
    except Exception:
        return "—"
    if e <= 0:
        return "—"
    if side == "做空":
        risk = abs(s - e) / e * 100
        rew = abs(e - t) / e * 100
    else:
        risk = abs(e - s) / e * 100
        rew = abs(t - e) / e * 100
    if risk < 1e-9:
        return "—"
    return f"{rew / risk:.2f}（毛，以 TP1/SL 粗算）"


def _copytrade_position_mgmt_html(km: dict, px: Optional[float]) -> str:
    """简版页：当前价相对 SL/TP 的距离%、分批建议（文案）；side 与快照价位一致。"""
    side = _copytrade_side(km)
    if side == "—" or px is None or float(px) <= 0:
        return "<p class=\"muted\">暂无有效信号或现价时，不做仓位管理数值展示；请刷新或换币种。</p>"
    try:
        e = float(km.get("entry_price") or 0)
        sl = float(km.get("sl_price") or 0)
        t1 = float(km.get("tp1_price") or 0)
        t2 = float(km.get("tp2_price") or 0)
    except Exception:
        return "<p class=\"muted\">价位数据不完整。</p>"
    if e <= 0 or sl <= 0:
        return "<p class=\"muted\">价位数据不完整。</p>"
    p = float(px)
    lines: List[str] = []
    if side == "做多":
        d_sl = (p - sl) / p * 100.0
        d_tp1 = (t1 - p) / p * 100.0 if t1 > p else None
        d_tp2 = (t2 - p) / p * 100.0 if t2 > p else None
        lamp_sl = "🔴" if d_sl < 0.12 else ("🟡" if d_sl < 0.35 else "⚪")
        lamp_tp = "🟢" if (d_tp1 is not None and 0 < d_tp1 < 0.12) else "⚪"
        lines.append(
            f"{lamp_sl} 当前价距止损 SL：约 <b>{d_sl:+.3f}%</b>（向下触及 SL 所需大致比例；负值表示已在 SL 下方）"
        )
        if d_tp1 is not None:
            lines.append(
                f"{lamp_tp} 距止盈 TP1：约 <b>{d_tp1:+.3f}%</b>（向上到 TP1 所需大致比例）"
            )
        if t2 > 0 and d_tp2 is not None:
            lines.append(f"⚪ 距 TP2：约 <b>{d_tp2:+.3f}%</b>")
    else:
        d_sl = (sl - p) / p * 100.0
        d_tp1 = (p - t1) / p * 100.0 if p > t1 else None
        d_tp2 = (p - t2) / p * 100.0 if p > t2 else None
        lamp_sl = "🔴" if d_sl < 0.12 else ("🟡" if d_sl < 0.35 else "⚪")
        lamp_tp = "🟢" if (d_tp1 is not None and 0 < d_tp1 < 0.12) else "⚪"
        lines.append(
            f"{lamp_sl} 当前价距止损 SL：约 <b>{d_sl:+.3f}%</b>（向上触及 SL 所需大致比例）"
        )
        if d_tp1 is not None:
            lines.append(
                f"{lamp_tp} 距止盈 TP1：约 <b>{d_tp1:+.3f}%</b>（向下到 TP1 所需大致比例）"
            )
        if t2 > 0 and d_tp2 is not None:
            lines.append(f"⚪ 距 TP2：约 <b>{d_tp2:+.3f}%</b>")
    lines.append(
        "<br/><span class=\"muted\">单笔风险占账户：常见参考 <b>0.4%～0.8%</b>（按自有规则缩放杠杆）；"
        "双边手续费展示口径约 <b>0.16%</b>，净盈亏需自行扣除。</span>"
    )
    lines.append(
        "<br/><b>分批参考（非指令）：</b> TP1 附近可考虑减仓 30%～50%；剩余可尝试保本移损；"
        "TP2 再减一部分。实际以交易所挂单为准。"
    )
    return "<p style=\"line-height:1.75;margin:0\">" + "<br/>".join(lines) + "</p>"


def _data_confidence_line(km: dict) -> str:
    score = float(km.get("consistency_score") or 0.0)
    if abs(score) >= 0.65:
        grade = "可信"
    elif abs(score) >= 0.35:
        grade = "一般"
    else:
        grade = "谨慎"
    return f"{grade}（一致性分 {score:+.2f}）"


def _operator_signal_card_line(km: dict, coach_mode: str) -> str:
    side = _copytrade_side(km)
    signal = str(km.get("signal_label") or "无")
    raw_prob = float(km.get("prob_up_5m") or 0.0)
    # 兼容两种口径：0~1 概率值 或 0~100 百分值，避免出现 5250% 这类千倍显示错误。
    prob = raw_prob * 100.0 if raw_prob <= 1.0 else raw_prob
    prob = max(0.0, min(100.0, prob))
    score = float(km.get("consistency_score") or 0.0)
    edge = abs(prob - 50.0)
    side_text = side if side != "—" else "观望"
    if coach_mode == "starter":
        gate = "强过滤"
    elif coach_mode == "live":
        gate = "平衡过滤"
    else:
        gate = "机会优先"
    return (
        f"{gate}｜方向:{side_text}｜信号:{signal}｜上涨概率:{prob:.1f}%｜"
        f"一致性:{score:+.2f}｜概率边际:{edge:.1f}%"
    )


@app.get("/copytrade/", include_in_schema=False)
def page_copytrade_redirect_slash():
    """部分反代/浏览器访问 /copytrade/ 时 404，统一跳转到无尾斜杠。"""
    return RedirectResponse(url="/copytrade", status_code=307)


@app.get("/copytrade", response_class=HTMLResponse)
@app.get("/ct", response_class=HTMLResponse)
async def page_copytrade(symbol: str = Query("SOL/USDT")):
    """跟单简版：仅方向、参考价、SL/TP、RR、Markov 摘要，供带单观看（与 /decision 数据同源）。
    同页另注册短路径 /ct（便于反代或手输 URL）。若仍 404，请确认服务器已拉取含本路由的 main.py 并重启进程。"""
    sym = _pick_symbol(symbol)
    qsym = quote(sym, safe="")
    km = get_v313_decision_snapshot(force_refresh=True, symbol=sym)
    snap = build_indicator_snapshot(sym, 500)
    last_close = snap.get("last_close")
    try:
        live_ticker = await fetch_current_ticker_price(sym)
    except Exception:
        live_ticker = None
    px = float(live_ticker) if live_ticker is not None else None
    if px is None and last_close is not None:
        try:
            px = float(last_close)
        except Exception:
            px = None

    # 与 /decision 一致：刷新简版时也同步主观察池 memos（否则用户长期只看简版会「有信号但无记账」）
    try:
        if px is not None:
            sync_virtual_memos_from_state(sym, float(px), decision=km)
    except Exception:
        pass

    side = _copytrade_side(km)
    adv = _copytrade_advice_title(km)
    sig = html.escape(str(km.get("signal_label") or "—"))
    entry = km.get("entry_price")
    sl = km.get("sl_price")
    tp1 = km.get("tp1_price")
    tp2 = km.get("tp2_price")
    rr_line = "—"
    if side in ("做多", "做空"):
        try:
            rr_line = _copytrade_rr_gross_one_line(
                float(entry or 0), float(sl or 0), float(tp1 or 0), side
            )
        except Exception:
            rr_line = "—"

    nav_ct = []
    for s in SYMBOL_CHOICES:
        active = "font-weight:700;color:#ffe082;" if s == sym else "color:#9ecbff;"
        nav_ct.append(
            f'<a style="margin-right:12px;{active}" href="/copytrade?symbol={quote(s, safe="")}">{html.escape(s)}</a>'
        )
    nav_ct_html = "\n".join(nav_ct)

    mk = html.escape(_zh_decision_copy(km.get("markov_regime_line") or "—"))
    tpl = html.escape(_zh_decision_copy(km.get("experiment_markov_template_line") or "—"))
    confidence = _data_confidence_line(km)
    signal_card = _operator_signal_card_line(km, "call")

    pos_html = _copytrade_position_mgmt_html(km, px)
    px_s = fmt_price(px) if px is not None else "—"

    body = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>跟单简版 · {html.escape(sym)}</title>
<style>
body{{margin:0;background:#0f1419;color:#e8eef7;font-family:system-ui,"PingFang SC","Microsoft YaHei",sans-serif;min-height:100vh;}}
.copytrade-page{{max-width:640px;margin:0 auto;padding:20px 16px 40px;box-sizing:border-box;}}
h1{{font-size:1.25rem;margin:0 0 12px;}}
.muted{{color:#8b9bb4;font-size:0.88rem;}}
.card{{background:#1a2332;border-radius:14px;padding:16px 18px;margin:14px 0;border:1px solid rgba(255,255,255,.08);width:100%;}}
.card h2{{font-size:1.02rem;margin:0 0 10px;color:#a5d8ff;}}
table.simple{{width:100%;border-collapse:collapse;font-size:0.95rem;}}
table.simple td{{padding:6px 0;border-bottom:1px solid rgba(255,255,255,.06);}}
table.simple td:first-child{{color:#8b9bb4;width:42%;}}
a{{color:#7c9cff;}}
.top-entry-strip{{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;margin-bottom:14px;padding:12px 16px;background:rgba(0,0,0,.28);border-radius:12px;border:1px solid rgba(255,255,255,.1);}}
.top-entry{{color:#a5b4fc;text-decoration:none;font-size:0.95rem;padding:6px 14px;border-radius:10px;border:1px solid transparent;}}
.top-entry:hover{{background:rgba(255,255,255,.07);color:#fff;}}
.top-entry-active{{color:#51cf66!important;font-weight:700;border-color:rgba(81,207,102,.45);background:rgba(81,207,102,.08);}}
.memos-banner{{background:linear-gradient(135deg,#2b2149 0%,#1a3d52 50%,#143d2e 100%);border:1px solid rgba(124,92,255,.35);border-radius:14px;padding:16px 20px;margin-bottom:18px;font-size:1.02rem;line-height:1.65;text-align:center;color:#f0f4ff;}}
.memos-banner strong{{color:#ffe066;font-weight:600;}}
.memos-banner-meta{{margin-top:6px;font-size:0.82rem;color:#8b9bb4;}}
</style></head><body>
{_HTML_BUILD_MARKER}
<div class="copytrade-page">
{_top_entry_strip("copytrade", sym)}
{_memos_banner_html()}
<h1>跟单简版（喊单）</h1>
<p class="muted" style="margin:0 0 8px">币种切换（与决策页同源）</p>
<p style="margin:0 0 14px">{nav_ct_html}</p>
<p class="muted" style="margin-bottom:14px">新基线说明：净口径统计建议以<strong>当前阶段起</strong>自行记日；历史完整样本仍在 <code>trade_memory.json</code> / 回测输出中可查，未删除。</p>
<div class="card">
<h2>实时执行卡（精简）</h2>
<table class="simple">
<tr><td>当前信号</td><td><b>{sig}</b></td></tr>
<tr><td>可信度</td><td>{html.escape(confidence)}</td></tr>
<tr><td>执行建议</td><td>{html.escape(signal_card)}</td></tr>
</table>
</div>
<div class="card">
<h2>参考价位（主观察池固定比例快照）</h2>
<table class="simple">
<tr><td>现价（约）</td><td><b>{html.escape(px_s)}</b> USDT</td></tr>
<tr><td>入场（参考）</td><td>{html.escape(str(entry if entry is not None else "—"))}</td></tr>
<tr><td>SL</td><td>{html.escape(str(sl if sl is not None else "—"))}</td></tr>
<tr><td>TP1</td><td>{html.escape(str(tp1 if tp1 is not None else "—"))}</td></tr>
<tr><td>TP2</td><td>{html.escape(str(tp2 if tp2 is not None else "—"))}</td></tr>
<tr><td>RR（毛）</td><td>{html.escape(rr_line)}</td></tr>
</table>
</div>
<div class="card">
<h2>实时仓位管理建议（比例供口头带单）</h2>
{pos_html}
</div>
<div class="card">
<h2>行情 / 模板（摘要）</h2>
<p style="margin:0;line-height:1.65">行情（Markov）：{mk}</p>
<p style="margin:10px 0 0;line-height:1.65">策略模板：{tpl}</p>
</div>
<p class="muted">风险提示：高杠杆请严格执行止损，不可重仓扛单；本页为辅助展示，非投资建议。</p>
<p><a href="/decision?symbol={qsym}">打开完整决策页</a></p>
<div class="muted" style="margin-top:20px;font-size:0.82rem;">约 15 秒自动刷新本页</div>
<script>
setTimeout(function(){{ window.location.href = "/copytrade?symbol={qsym}"; }}, 15000);
</script>
</div>
</body></html>"""
    return HTMLResponse(content=body, headers=_HTML_NO_CACHE_HEADERS)


async def _operator_page_simple(
    *,
    symbol: str,
    mode: str,
    title: str,
    refresh_sec: int,
    note: str,
    active_key: str,
    route_path: str,
) -> HTMLResponse:
    sym = _pick_symbol(symbol)
    qsym = quote(sym, safe="")
    km = get_v313_decision_snapshot(force_refresh=True, symbol=sym)
    snap = build_indicator_snapshot(sym, 500)
    last_close = snap.get("last_close")
    try:
        live_ticker = await fetch_current_ticker_price(sym)
    except Exception:
        live_ticker = None
    px = float(live_ticker) if live_ticker is not None else None
    if px is None and last_close is not None:
        try:
            px = float(last_close)
        except Exception:
            px = None
    try:
        if px is not None:
            sync_virtual_memos_from_state(sym, float(px), decision=km)
    except Exception:
        pass

    side = _copytrade_side(km)
    sig = html.escape(str(km.get("signal_label") or "—"))
    entry = km.get("entry_price")
    sl = km.get("sl_price")
    tp1 = km.get("tp1_price")
    rr_line = "—"
    if side in ("做多", "做空"):
        try:
            rr_line = _copytrade_rr_gross_one_line(
                float(entry or 0), float(sl or 0), float(tp1 or 0), side
            )
        except Exception:
            rr_line = "—"
    confidence = _data_confidence_line(km)
    signal_card = _operator_signal_card_line(km, mode)

    nav_ct = []
    for s in SYMBOL_CHOICES:
        active = "font-weight:700;color:#ffe082;" if s == sym else "color:#9ecbff;"
        nav_ct.append(
            f'<a style="margin-right:12px;{active}" href="?symbol={quote(s, safe="")}">{html.escape(s)}</a>'
        )
    nav_ct_html = "\n".join(nav_ct)
    px_s = fmt_price(px) if px is not None else "—"

    body = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)} · {html.escape(sym)}</title>
<style>
body{{margin:0;background:#0f1419;color:#e8eef7;font-family:system-ui,"PingFang SC","Microsoft YaHei",sans-serif;min-height:100vh;}}
.copytrade-page{{max-width:680px;margin:0 auto;padding:20px 16px 40px;box-sizing:border-box;}}
h1{{font-size:1.25rem;margin:0 0 12px;}}
.muted{{color:#8b9bb4;font-size:0.88rem;}}
.card{{background:#1a2332;border-radius:14px;padding:16px 18px;margin:14px 0;border:1px solid rgba(255,255,255,.08);width:100%;}}
.card h2{{font-size:1.02rem;margin:0 0 10px;color:#a5d8ff;}}
table.simple{{width:100%;border-collapse:collapse;font-size:0.95rem;}}
table.simple td{{padding:6px 0;border-bottom:1px solid rgba(255,255,255,.06);}}
table.simple td:first-child{{color:#8b9bb4;width:42%;}}
a{{color:#7c9cff;}}
</style></head><body>
{_HTML_BUILD_MARKER}
<div class="copytrade-page">
{_top_entry_strip(active_key, sym)}
{_memos_banner_html()}
<h1>{html.escape(title)}</h1>
<p class="muted">{html.escape(note)}</p>
<p style="margin:0 0 14px">{nav_ct_html}</p>
<div class="card">
<h2>实时执行卡</h2>
<table class="simple">
<tr><td>当前信号</td><td><b>{sig}</b></td></tr>
<tr><td>可信度</td><td>{html.escape(confidence)}</td></tr>
<tr><td>执行建议</td><td>{html.escape(signal_card)}</td></tr>
<tr><td>方向</td><td><b>{html.escape(side)}</b></td></tr>
<tr><td>现价</td><td>{html.escape(px_s)} USDT</td></tr>
<tr><td>入场 / SL / TP1</td><td>{html.escape(str(entry))} / {html.escape(str(sl))} / {html.escape(str(tp1))}</td></tr>
<tr><td>RR（毛）</td><td>{html.escape(rr_line)}</td></tr>
</table>
</div>
<p class="muted">仅供带单执行辅助，最终以下单盘面与风控纪律为准。</p>
<div class="muted" style="margin-top:20px;font-size:0.82rem;">约 {refresh_sec} 秒自动刷新本页</div>
<script>
setTimeout(function(){{ window.location.href = "{route_path}?symbol={qsym}"; }}, {refresh_sec * 1000});
</script>
</div>
</body></html>"""
    return HTMLResponse(content=body, headers=_HTML_NO_CACHE_HEADERS)


@app.get("/teacher_boost", response_class=HTMLResponse)
@app.get("/teacher_boost/", include_in_schema=False)
@app.get("/teacher-boost", response_class=HTMLResponse)
@app.get("/tb", response_class=HTMLResponse)
async def page_teacher_boost(symbol: str = Query("SOL/USDT")):
    """带单老师·起号：简版实时执行卡（强过滤）。"""
    return await _operator_page_simple(
        symbol=symbol,
        mode="starter",
        title="带单老师 · 起号",
        refresh_sec=30,
        note="起号模式：强过滤、低频高质量（默认更偏观望）。",
        active_key="teacher_boost",
        route_path="/teacher_boost",
    )


@app.get("/teacher_combat", response_class=HTMLResponse)
@app.get("/teacher_combat/", include_in_schema=False)
@app.get("/teacher-combat", response_class=HTMLResponse)
@app.get("/tc", response_class=HTMLResponse)
async def page_teacher_combat(symbol: str = Query("SOL/USDT")):
    """带单老师·实盘：简版实时执行卡（平衡频率和质量）。"""
    return await _operator_page_simple(
        symbol=symbol,
        mode="live",
        title="带单老师 · 实盘",
        refresh_sec=20,
        note="实盘模式：平衡信号质量与机会频率。",
        active_key="teacher_combat",
        route_path="/teacher_combat",
    )


if __name__ == "__main__":
    def _http_port() -> int:
        """本地 HTTP 端口：默认 18080；可用 LONGXIA_HTTP_PORT 或 PORT 覆盖（systemd/容器常用）。"""
        for k in ("LONGXIA_HTTP_PORT", "PORT"):
            raw = str(os.environ.get(k, "")).strip()
            if not raw:
                continue
            try:
                p = int(raw)
                if 1 <= p <= 65535:
                    return p
            except ValueError:
                continue
        return 18080

    uvicorn.run(app, host="0.0.0.0", port=_http_port())
