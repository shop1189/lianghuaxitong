"""
币安 U 本位永续公开参考数据（不替代 Gate/CCXT 现货主链路）。

- REST：标记价 / 指数价 / 资金费率、持仓量 OI（无需 API Key）
- WS：订阅全市场强平快照流 ``!forceOrder@arr``，短时采样写入缓存（替代 Coinglass 全网热力）

由 ``main.py`` lifespan 后台任务定期刷新；决策快照只读缓存，避免阻塞请求。
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

FAPI_HTTP = "https://fapi.binance.com"
FAPI_WS = "wss://fstream.binance.com/stream?streams=!forceOrder@arr"

# 与 main.SYMBOL_CHOICES 对齐（CCXT 现货名 → 币安永续 symbol）
_CCXT_TO_BN: Dict[str, str] = {
    "SOL/USDT": "SOLUSDT",
    "BTC/USDT": "BTCUSDT",
    "ETH/USDT": "ETHUSDT",
    "DOGE/USDT": "DOGEUSDT",
    "XRP/USDT": "XRPUSDT",
    "BNB/USDT": "BNBUSDT",
}
_WATCH: frozenset[str] = frozenset(_CCXT_TO_BN.values())

_lock = threading.Lock()
_cache: Dict[str, Any] = {
    "updated_at": 0.0,
    "per_symbol": {},
    "liq": {
        "sample_sec": 0.0,
        "n_total": 0,
        "n_watch": 0,
        "by_symbol": {},
        "error": None,
    },
}


def _http_json(path_qs: str, timeout: float = 8.0) -> Optional[dict]:
    url = f"{FAPI_HTTP}{path_qs}" if path_qs.startswith("/") else f"{FAPI_HTTP}/{path_qs}"
    try:
        req = Request(url, headers={"User-Agent": "longxia-system/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError, OSError):
        return None


def _collect_liquidations_ws(
    duration_sec: float = 2.5, max_msgs: int = 400
) -> Dict[str, Any]:
    """短时连接 WS，统计全市场强平事件中本系统关注币种的出现次数。"""
    out: Dict[str, Any] = {
        "sample_sec": float(duration_sec),
        "n_total": 0,
        "n_watch": 0,
        "by_symbol": {},
        "price_by_symbol": {},
        "by_side": {"BUY": 0, "SELL": 0},
        "error": None,
    }
    t0 = time.time()
    by_sym: dict[str, int] = defaultdict(int)
    px_by_sym: dict[str, list[float]] = defaultdict(list)
    by_side: dict[str, int] = defaultdict(int)
    try:
        from websocket import create_connection

        ws = create_connection(FAPI_WS, timeout=duration_sec + 5.0)
        try:
            while time.time() - t0 < duration_sec and out["n_total"] < max_msgs:
                ws.settimeout(max(0.15, duration_sec - (time.time() - t0)))
                raw = ws.recv()
                if not raw:
                    break
                out["n_total"] += 1
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                data = msg.get("data") or msg
                if not isinstance(data, dict):
                    continue
                if data.get("e") != "forceOrder":
                    continue
                o = data.get("o") or {}
                sym = str(o.get("s") or "").upper()
                side = str(o.get("S") or "").upper()
                if side in ("BUY", "SELL"):
                    by_side[side] += 1
                ap = o.get("ap") or o.get("p")
                try:
                    apf = float(ap)
                except (TypeError, ValueError):
                    apf = 0.0
                if sym in _WATCH:
                    by_sym[sym] += 1
                    out["n_watch"] += 1
                    if apf > 0:
                        px_by_sym[sym].append(apf)
        finally:
            try:
                ws.close()
            except Exception:
                pass
    except Exception as e:
        out["error"] = str(e)[:220]
    out["by_symbol"] = dict(by_sym)
    out["by_side"] = {"BUY": int(by_side.get("BUY", 0)), "SELL": int(by_side.get("SELL", 0))}
    out["price_by_symbol"] = {
        k: {
            "n": len(v),
            "min": min(v) if v else None,
            "max": max(v) if v else None,
            "last": (v[-1] if v else None),
        }
        for k, v in px_by_sym.items()
    }
    return out


def refresh_binance_reference_cache() -> None:
    """阻塞调用：拉全币种 REST + 一次 WS 强平采样；由后台线程执行。"""
    liq = _collect_liquidations_ws(duration_sec=2.5, max_msgs=500)
    per: Dict[str, Dict[str, Any]] = {}
    for bn_sym in _WATCH:
        prem = _http_json(f"/fapi/v1/premiumIndex?symbol={bn_sym}")
        oi = _http_json(f"/fapi/v1/openInterest?symbol={bn_sym}")
        per[bn_sym] = {"premium": prem or {}, "oi": oi or {}}
    with _lock:
        _cache["updated_at"] = time.time()
        _cache["per_symbol"] = per
        _cache["liq"] = liq


def _fmt_funding(fr: Any) -> str:
    try:
        x = float(fr)
        return f"{x * 100:.4f}%"
    except (TypeError, ValueError):
        return "—"


def _basis_pct(mark: Any, index: Any) -> Optional[float]:
    try:
        m = float(mark)
        i = float(index)
        if i == 0:
            return None
        return (m - i) / i * 100.0
    except (TypeError, ValueError):
        return None


def get_binance_context_for_ccxt_symbol(ccxt_symbol: str) -> Dict[str, Any]:
    """
    供 ``get_v313_decision_snapshot`` 合并：短后缀文案 + 面板用结构化字段。

    不改变既有键语义；缺失数据时返回空后缀与占位面板。
    """
    sym = (ccxt_symbol or "").strip()
    bn_sym = _CCXT_TO_BN.get(sym)
    with _lock:
        age = time.time() - float(_cache.get("updated_at") or 0.0)
        per = dict(_cache.get("per_symbol") or {})
        liq = dict(_cache.get("liq") or {})

    panel: Dict[str, Any] = {
        "cache_age_sec": round(age, 1),
        "binance_symbol": bn_sym or "—",
        "mark_price": "—",
        "index_price": "—",
        "funding_rate": "—",
        "next_funding_ms": None,
        "open_interest": "—",
        "basis_mark_vs_index_pct": "—",
        "liq_hits_in_sample": 0,
        "liq_sample_sec": liq.get("sample_sec"),
        "liq_total_msgs": int(liq.get("n_total") or 0),
        "liq_watch_msgs": int(liq.get("n_watch") or 0),
        "liq_error": liq.get("error"),
        "liq_price_band": "—",
    }
    trend_suffix = ""
    if not bn_sym:
        return {
            "trend_suffix": "",
            "panel": panel,
            "raw": {"per": per, "liq": liq, "age_sec": age},
        }

    row = per.get(bn_sym) or {}
    prem = row.get("premium") or {}
    oi = row.get("oi") or {}
    mark = prem.get("markPrice")
    idx = prem.get("indexPrice")
    fr = prem.get("lastFundingRate")
    nft = prem.get("nextFundingTime")
    oi_v = oi.get("openInterest")

    panel["mark_price"] = str(mark) if mark is not None else "—"
    panel["index_price"] = str(idx) if idx is not None else "—"
    panel["funding_rate"] = _fmt_funding(fr)
    panel["next_funding_ms"] = nft
    bp = _basis_pct(mark, idx)
    panel["basis_mark_vs_index_pct"] = f"{bp:.4f}%" if bp is not None else "—"
    panel["open_interest"] = str(oi_v) if oi_v is not None else "—"
    try:
        panel["funding_rate_dec"] = float(fr) if fr is not None and str(fr).strip() != "" else None
    except (TypeError, ValueError):
        panel["funding_rate_dec"] = None
    panel["basis_pct_val"] = bp

    liq_n = int((liq.get("by_symbol") or {}).get(bn_sym) or 0)
    panel["liq_hits_in_sample"] = liq_n
    liq_band = (liq.get("price_by_symbol") or {}).get(bn_sym) if isinstance(liq.get("price_by_symbol"), dict) else None
    if isinstance(liq_band, dict) and liq_band.get("min") is not None and liq_band.get("max") is not None:
        try:
            panel["liq_price_band"] = f"{float(liq_band.get('min')):.4f} ~ {float(liq_band.get('max')):.4f}"
        except (TypeError, ValueError):
            panel["liq_price_band"] = "—"

    parts: List[str] = []
    if bp is not None and abs(bp) >= 0.01:
        parts.append(f"标记-指数基差≈{bp:.3f}%")
    if fr is not None:
        parts.append(f"资金费率≈{_fmt_funding(fr)}")
    if oi_v is not None:
        parts.append(f"OI≈{oi_v}")
    if liq_n > 0:
        parts.append(f"近窗强平采样 {liq_n} 笔（{bn_sym}）")
    stale = age >= 120.0
    if parts:
        tail = "（缓存偏旧，后台刷新中）" if stale else f"（约 {int(age)} 秒前）"
        trend_suffix = " | 币安永续参考：" + "，".join(parts) + tail
    elif stale:
        trend_suffix = " | 币安永续参考：缓存偏旧（后台采集中）"

    return {
        "trend_suffix": trend_suffix,
        "panel": panel,
        "raw": {"per_symbol_row": row, "liq": liq, "age_sec": age},
    }


def apply_binance_perp_score_nudge(
    score: float, panel: Dict[str, Any]
) -> Tuple[float, Dict[str, Any]]:
    """
    在 Gate 1m 聚合分之外，用币安永续公开字段做小幅修正（默认开，可用 LONGXIA_BINANCE_SCORE_ENABLE=0 关闭）。

    设计原则：单条幅度小、总修正有上限，避免与现有 RSI/MTF 主逻辑打架。
    """
    meta: Dict[str, Any] = {"notes": [], "delta_total": 0.0}
    if not panel or str(panel.get("binance_symbol") or "") in ("", "—"):
        return score, meta
    if os.environ.get("LONGXIA_BINANCE_SCORE_ENABLE", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return score, meta

    fr = panel.get("funding_rate_dec")
    bp = panel.get("basis_pct_val")
    liq_n = int(panel.get("liq_hits_in_sample") or 0)
    liq_ok = not panel.get("liq_error")

    th_fr = float(os.environ.get("LONGXIA_BINANCE_FUNDING_THRESH", "0.00035"))
    d_fr = float(os.environ.get("LONGXIA_BINANCE_FUNDING_DELTA", "0.028"))
    th_bp = float(os.environ.get("LONGXIA_BINANCE_BASIS_THRESH_PCT", "0.10"))
    d_bp = float(os.environ.get("LONGXIA_BINANCE_BASIS_DELTA", "0.022"))
    liq_th = int(os.environ.get("LONGXIA_BINANCE_LIQ_THRESH", "5"))
    d_liq_max = float(os.environ.get("LONGXIA_BINANCE_LIQ_DELTA_MAX", "0.035"))

    delta = 0.0
    if isinstance(fr, (int, float)):
        fv = float(fr)
        if fv > th_fr:
            delta -= d_fr
            meta["notes"].append(f"资金费率偏高→一致性分-{d_fr:.3f}")
        elif fv < -th_fr:
            delta += d_fr
            meta["notes"].append(f"资金费率偏低→一致性分+{d_fr:.3f}")
    if isinstance(bp, (int, float)):
        bpv = float(bp)
        if bpv > th_bp:
            delta -= d_bp
            meta["notes"].append(f"标记溢价>{th_bp}%→-{d_bp:.3f}")
        elif bpv < -th_bp:
            delta += d_bp
            meta["notes"].append(f"标记折价<{-th_bp}%→+{d_bp:.3f}")
    if liq_ok and liq_n >= liq_th:
        damp = min(d_liq_max, 0.04 + 0.006 * float(liq_n - liq_th))
        if score > 0:
            delta -= damp
            meta["notes"].append(f"近窗强平≥{liq_th}→收敛-{damp:.3f}")
        elif score < 0:
            delta += damp
            meta["notes"].append(f"近窗强平≥{liq_th}→收敛+{damp:.3f}")

    cap = float(os.environ.get("LONGXIA_BINANCE_SCORE_DELTA_CAP", "0.055"))
    delta = max(-cap, min(cap, delta))
    meta["delta_total"] = delta
    out = max(-1.0, min(1.0, float(score) + delta))
    return out, meta


def binance_metrics_html_rows(ccxt_symbol: str) -> str:
    """返回若干 <tr>…</tr>，嵌入决策页「关键指标」表。"""
    import html as _html

    def esc(x: Any) -> str:
        return _html.escape(str(x), quote=True)

    ctx = get_binance_context_for_ccxt_symbol(ccxt_symbol)
    p = ctx.get("panel") or {}
    liq_err = p.get("liq_error")
    liq_note = (
        f"采样窗≈{esc(p.get('liq_sample_sec') or '—')}s · 全流消息 {esc(p.get('liq_total_msgs'))} 条 · "
        f"命中本组币种 {esc(p.get('liq_watch_msgs'))} 条"
    )
    if liq_err:
        liq_note += f" · WS：{esc(liq_err)}"

    rows = f"""
<tr><td colspan="2" style="padding-top:10px;border-top:1px solid rgba(255,255,255,.12)">
<strong>指标参考 · 币安 U 本位永续（公有数据，与 Gate 现货并行）</strong>
<span class="muted" style="font-weight:400"> · 缓存约 {esc(p.get('cache_age_sec'))} 秒前刷新</span>
</td></tr>
<tr><td>币安 · 标记价 / 指数价</td><td>{esc(p.get('mark_price'))} / {esc(p.get('index_price'))}</td></tr>
<tr><td>币安 · 资金费率（当期）</td><td>{esc(p.get('funding_rate'))}</td></tr>
<tr><td>币安 · 标记相对指数基差</td><td>{esc(p.get('basis_mark_vs_index_pct'))}</td></tr>
<tr><td>币安 · 持仓量 OI</td><td>{esc(p.get('open_interest'))}</td></tr>
<tr><td>币安 · 强平事件采样（当前币对）</td><td>窗内命中 {esc(p.get('liq_hits_in_sample'))} 笔 · {liq_note}</td></tr>
<tr><td>币安 · 强平价格带样本（当前币对）</td><td>{esc(p.get('liq_price_band'))}</td></tr>
"""
    return rows.strip()
