"""
可选第三方 / 签名接口：仅从环境变量读取 Key，不写死在仓库。

- Coinglass：REST v4，头 ``CG-API-KEY``（已接短线核心：OI/资金费率/爆仓）
- CryptoQuant：``Authorization: Bearer``
- LunarCrush：优先 ``api4`` Bearer；失败则尝试 ``api3`` 的 ``?key=``
- 币安 U 本位：若配置 ``BINANCE_API_KEY/SECRET``，拉 ``/fapi/v2/account`` 摘要
- Gate 永续：若配置 ``LONGXIA_GATE_API_KEY/SECRET``（或 ``GATE_API_KEY/SECRET``），拉清算摘要

结果供决策页展示；失败时返回 ``error`` 短文案，不抛异常。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_lock = threading.Lock()
_cache: Dict[str, Any] = {"ts": 0.0, "data": {}}
_TTL_SEC = 90.0


def _http_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 12.0,
) -> tuple[Optional[bytes], Optional[str]]:
    try:
        req = Request(url, headers=headers or {"User-Agent": "longxia-system/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read(), None
    except HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            body = str(e)
        return None, f"HTTP {e.code}: {body}"
    except (URLError, TimeoutError, OSError) as e:
        return None, str(e)[:400]


def _ccxt_to_binance_symbol(ccxt_symbol: str) -> str:
    s = (ccxt_symbol or "BTC/USDT").strip().upper()
    return s.replace("/", "")


def _to_f(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_coinglass(ccxt_symbol: str) -> Dict[str, Any]:
    key = (os.environ.get("COINGLASS_API_KEY") or "").strip()
    if not key or len(key) < 8:
        return {"enabled": False, "summary": "未配置 COINGLASS_API_KEY"}

    base = "https://open-api-v4.coinglass.com"
    hdr = {"accept": "application/json", "CG-API-KEY": key}
    sym = _ccxt_to_binance_symbol(ccxt_symbol)
    interval = os.environ.get("LONGXIA_COINGLASS_INTERVAL", "4h").strip() or "4h"
    limit = int(os.environ.get("LONGXIA_COINGLASS_LIMIT", "4") or 4)

    def _fetch_ts(path: str) -> Tuple[Optional[list], Optional[str]]:
        q = urlencode(
            {
                "exchange": "Binance",
                "symbol": sym,
                "interval": interval,
                "limit": max(3, min(limit, 20)),
            }
        )
        raw, err = _http_get(f"{base}{path}?{q}", headers=hdr)
        if err:
            return None, err
        try:
            j = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception as e:
            return None, str(e)
        code = str((j or {}).get("code") or "")
        if code not in ("0", "200", ""):
            return None, str(j)[:280]
        arr = (j or {}).get("data")
        if isinstance(arr, list):
            return arr, None
        return None, "data 结构异常"

    oi_arr, oi_err = _fetch_ts("/api/futures/open-interest/history")
    fr_arr, fr_err = _fetch_ts("/api/futures/funding-rate/history")
    liq_arr, liq_err = _fetch_ts("/api/futures/liquidation/history")
    gls_arr, gls_err = _fetch_ts("/api/futures/global-long-short-account-ratio/history")
    topa_arr, topa_err = _fetch_ts("/api/futures/top-long-short-account-ratio/history")

    if oi_err and fr_err and liq_err and gls_err and topa_err:
        return {
            "enabled": True,
            "ok": False,
            "error": f"OI={oi_err}; FR={fr_err}; LIQ={liq_err}; GLS={gls_err}; TOPA={topa_err}",
        }

    def _close_delta_pct(arr: Optional[list]) -> Optional[float]:
        if not arr or len(arr) < 2:
            return None
        c1 = _to_f(arr[-2].get("close"))
        c2 = _to_f(arr[-1].get("close"))
        if c1 is None or c2 is None or c1 == 0:
            return None
        return (c2 - c1) / c1 * 100.0

    oi_chg = _close_delta_pct(oi_arr)
    fr_latest = _to_f((fr_arr or [{}])[-1].get("close")) if fr_arr else None

    liq_bias = None
    if liq_arr and len(liq_arr) >= 1:
        last = liq_arr[-1]
        ll = _to_f(last.get("long_liquidation_usd")) or 0.0
        sl = _to_f(last.get("short_liquidation_usd")) or 0.0
        den = ll + sl
        if den > 0:
            liq_bias = (sl - ll) / den  # >0 短方爆仓更多（偏多）

    summary_parts = []
    if oi_chg is not None:
        summary_parts.append(f"OI近{interval}变动 {oi_chg:+.2f}%")
    if fr_latest is not None:
        summary_parts.append(f"Funding {fr_latest*100:+.4f}%")
    if liq_bias is not None:
        summary_parts.append(f"爆仓偏置 {(liq_bias*100):+.1f}%")
    gl_long = None
    gl_short = None
    if gls_arr and len(gls_arr) >= 1:
        gl_last = gls_arr[-1]
        gl_long = _to_f(gl_last.get("global_account_long_percent"))
        gl_short = _to_f(gl_last.get("global_account_short_percent"))
        if gl_long is not None and gl_short is not None:
            summary_parts.append(f"全市场多空比 {gl_long:.1f}/{gl_short:.1f}")

    top_long = None
    top_short = None
    if topa_arr and len(topa_arr) >= 1:
        top_last = topa_arr[-1]
        top_long = _to_f(top_last.get("top_account_long_percent"))
        top_short = _to_f(top_last.get("top_account_short_percent"))
    summary = " · ".join(summary_parts) if summary_parts else "已连通（数据不足以计算摘要）"

    return {
        "enabled": True,
        "ok": True,
        "symbol": sym,
        "interval": interval,
        "summary": summary,
        "oi_change_pct": oi_chg,
        "funding_close": fr_latest,
        "liq_bias": liq_bias,
        "global_long_percent": gl_long,
        "global_short_percent": gl_short,
        "top_long_percent": top_long,
        "top_short_percent": top_short,
        "raw_errors": {
            "oi": oi_err,
            "fr": fr_err,
            "liq": liq_err,
            "global_ls": gls_err,
            "top_ls": topa_err,
        },
    }


def apply_coinglass_score_nudge(score: float, cg: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """用 Coinglass 的 OI/资金费率/爆仓偏置做小幅修正。"""
    meta: Dict[str, Any] = {"notes": [], "delta_total": 0.0}
    if not cg or not cg.get("enabled") or not cg.get("ok"):
        return score, meta
    if os.environ.get("LONGXIA_COINGLASS_SCORE_ENABLE", "1").strip().lower() in ("0", "false", "no", "off"):
        return score, meta

    oi = _to_f(cg.get("oi_change_pct"))
    fr = _to_f(cg.get("funding_close"))
    lb = _to_f(cg.get("liq_bias"))

    th_oi = float(os.environ.get("LONGXIA_COINGLASS_OI_THRESH_PCT", "1.2"))
    d_oi = float(os.environ.get("LONGXIA_COINGLASS_OI_DELTA", "0.026"))
    th_fr = float(os.environ.get("LONGXIA_COINGLASS_FR_THRESH", "0.00020"))
    d_fr = float(os.environ.get("LONGXIA_COINGLASS_FR_DELTA", "0.024"))
    th_lb = float(os.environ.get("LONGXIA_COINGLASS_LIQ_BIAS_THRESH", "0.30"))
    d_lb = float(os.environ.get("LONGXIA_COINGLASS_LIQ_BIAS_DELTA", "0.022"))
    cap = float(os.environ.get("LONGXIA_COINGLASS_DELTA_CAP", "0.065"))

    delta = 0.0
    if oi is not None and abs(oi) >= th_oi:
        if oi > 0:
            # OI 同时升高说明拥挤，方向交给资金费率判断
            if fr is not None and fr > th_fr:
                delta -= d_oi
                meta["notes"].append(f"OI+且费率偏高→-{d_oi:.3f}")
            elif fr is not None and fr < -th_fr:
                delta += d_oi
                meta["notes"].append(f"OI+且费率偏低→+{d_oi:.3f}")
        else:
            # OI 大幅回落：趋势衰减，向0收敛
            d = min(d_oi, abs(score) * 0.6)
            if score > 0:
                delta -= d
            elif score < 0:
                delta += d
            if d > 0:
                meta["notes"].append(f"OI回落→收敛{d:+.3f}")

    if fr is not None and abs(fr) >= th_fr:
        if fr > 0:
            delta -= d_fr
            meta["notes"].append(f"Funding>{th_fr}→-{d_fr:.3f}")
        else:
            delta += d_fr
            meta["notes"].append(f"Funding<-{th_fr}→+{d_fr:.3f}")

    if lb is not None and abs(lb) >= th_lb:
        if lb > 0:
            delta += d_lb
            meta["notes"].append(f"短方爆仓占优→+{d_lb:.3f}")
        else:
            delta -= d_lb
            meta["notes"].append(f"多方爆仓占优→-{d_lb:.3f}")

    delta = max(-cap, min(cap, delta))
    meta["delta_total"] = delta
    return max(-1.0, min(1.0, float(score) + delta)), meta


def _fetch_cryptoquant() -> Dict[str, Any]:
    token = (os.environ.get("CRYPTOQUANT_API_TOKEN") or "").strip()
    if not token or len(token) < 8:
        return {"enabled": False, "summary": "未配置 CRYPTOQUANT_API_TOKEN"}
    # 先试 Bearer，再试 query api_key（部分网络/套餐环境下 Bearer 会被风控拦截）
    url = "https://api.cryptoquant.com/v1/discovery/endpoints?format=json"
    raw, err = _http_get(
        url, headers={"Authorization": f"Bearer {token}", "accept": "application/json"}
    )
    if err:
        q = urlencode({"format": "json", "api_key": token})
        raw, err = _http_get(f"https://api.cryptoquant.com/v1/discovery/endpoints?{q}")
        if err:
            return {"enabled": True, "ok": False, "error": err}
    try:
        j = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as e:
        return {"enabled": True, "ok": False, "error": str(e)}
    st = j.get("status") or {}
    code = st.get("code")
    if isinstance(code, int) and code >= 400:
        return {
            "enabled": True,
            "ok": False,
            "error": f"code={code} msg={st.get('message', '')[:120]}",
        }
    return {
        "enabled": True,
        "ok": True,
        "summary": f"discovery code={st.get('code')} msg={st.get('message', '')[:80]}",
    }


def _fetch_lunarcrush(coin_symbol: str) -> Dict[str, Any]:
    key = (os.environ.get("LUNARCRUSH_API_KEY") or "").strip()
    if not key or len(key) < 8:
        return {"enabled": False, "summary": "未配置 LUNARCRUSH_API_KEY"}
    coin = (coin_symbol or "BTC").split("/")[0].upper()
    # api4：先试 list v2（官方公开文档更稳定），再尝试在列表里匹配目标币
    url4 = "https://lunarcrush.com/api4/public/coins/list/v2?limit=200"
    raw, err = _http_get(
        url4, headers={"Authorization": f"Bearer {key}", "accept": "application/json"}
    )
    if not err and raw:
        try:
            j = json.loads(raw.decode("utf-8", errors="replace"))
            if isinstance(j, dict) and str(j.get("error") or "").strip():
                em = str(j.get("error") or "").strip()
                if "active Individual" in em or "subscription" in em.lower():
                    return {
                        "enabled": True,
                        "ok": False,
                        "error": "权限不足：当前 LunarCrush 套餐不支持该 API（需付费升级）",
                    }
            data = j.get("data") if isinstance(j, dict) else None
            if isinstance(data, list):
                hit = None
                for r in data:
                    sym = str((r or {}).get("symbol") or "").upper()
                    if sym == coin:
                        hit = r
                        break
                if hit is None and data:
                    hit = data[0]
                if isinstance(hit, dict):
                    gs = hit.get("galaxy_score") or hit.get("galaxyScore")
                    ar = hit.get("alt_rank") or hit.get("altRank")
                    hs = str(hit.get("symbol") or coin)
                    return {
                        "enabled": True,
                        "ok": True,
                        "via": "api4",
                        "summary": f"{hs} Galaxy≈{gs} AltRank≈{ar}",
                    }
        except Exception:
            pass
    url3 = f"https://lunarcrush.com/api3/coins/{coin}?data=market,galaxy,alt_rank&key={key}"
    raw2, err2 = _http_get(url3)
    if err2:
        e2 = str(err2 or err)
        if "Invalid endpoint" in e2 or "HTTP 404" in e2:
            return {
                "enabled": True,
                "ok": False,
                "error": "权限不足或端点不可用：当前 key/套餐无法使用 LunarCrush API（暂不启用）",
            }
        return {"enabled": True, "ok": False, "error": e2}
    try:
        j2 = json.loads(raw2.decode("utf-8", errors="replace"))
    except Exception as e:
        return {"enabled": True, "ok": False, "error": str(e)}
    if isinstance(j2, dict) and j2.get("status") == "error":
        msg = str(j2.get("message", j2))[:200]
        if "Invalid endpoint" in msg:
            return {
                "enabled": True,
                "ok": False,
                "error": "权限不足或端点不可用：当前 key/套餐无法使用 LunarCrush API（暂不启用）",
            }
        return {"enabled": True, "ok": False, "error": msg}
    d0 = j2.get("data") if isinstance(j2, dict) else None
    if isinstance(d0, dict):
        gs = d0.get("galaxy_score")
        ar = d0.get("alt_rank")
        return {"enabled": True, "ok": True, "via": "api3", "summary": f"{coin} Galaxy≈{gs} AltRank≈{ar}"}
    return {
        "enabled": True,
        "ok": False,
        "error": "权限不足或端点不可用：当前 key/套餐无法使用 LunarCrush API（暂不启用）",
    }


def _fetch_binance_signed() -> Dict[str, Any]:
    ak = (os.environ.get("BINANCE_API_KEY") or "").strip()
    sk = (os.environ.get("BINANCE_API_SECRET") or "").strip()
    if not ak or not sk:
        return {"enabled": False, "summary": "未配置 BINANCE_API_KEY/SECRET"}
    base = "https://fapi.binance.com"
    ep = "/fapi/v2/account"
    ts = int(time.time() * 1000)
    qs = urlencode({"timestamp": ts, "recvWindow": 5000})
    sig = hmac.new(sk.encode("utf-8"), qs.encode("utf-8"), hashlib.sha256).hexdigest()
    url = f"{base}{ep}?{qs}&signature={sig}"
    raw, err = _http_get(url, headers={"X-MBX-APIKEY": ak})
    if err:
        return {"enabled": True, "ok": False, "error": err}
    try:
        j = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as e:
        return {"enabled": True, "ok": False, "error": str(e)}
    if isinstance(j, dict) and j.get("code") is not None and j.get("code") != 200:
        return {"enabled": True, "ok": False, "error": str(j)[:300]}
    twb = j.get("totalWalletBalance") if isinstance(j, dict) else None
    te = j.get("totalUnrealizedProfit") if isinstance(j, dict) else None
    return {"enabled": True, "ok": True, "summary": f"合约账户 totalWalletBalance≈{twb} unrealized≈{te}"}


def _gate_sign_v4(method: str, url_path: str, query_string: str, body: str) -> Dict[str, str]:
    sk = os.environ.get("LONGXIA_GATE_API_SECRET") or os.environ.get("GATE_API_SECRET") or ""
    ak = os.environ.get("LONGXIA_GATE_API_KEY") or os.environ.get("GATE_API_KEY") or ""
    t = str(int(time.time()))
    m = hashlib.sha512()
    m.update((body or "").encode("utf-8"))
    hp = m.hexdigest()
    s = f"{method}\n{url_path}\n{query_string}\n{hp}\n{t}"
    sign = hmac.new(sk.encode("utf-8"), s.encode("utf-8"), hashlib.sha512).hexdigest()
    return {"KEY": ak, "SIGN": sign, "Timestamp": t}


def _fetch_gate_signed_liquidates() -> Dict[str, Any]:
    ak = (os.environ.get("LONGXIA_GATE_API_KEY") or os.environ.get("GATE_API_KEY") or "").strip()
    sk = (os.environ.get("LONGXIA_GATE_API_SECRET") or os.environ.get("GATE_API_SECRET") or "").strip()
    if not ak or not sk:
        return {"enabled": False, "summary": "未配置 LONGXIA_GATE_API_KEY/SECRET（或 GATE_*）"}
    host = "https://api.gateio.ws"
    path = "/api/v4/futures/usdt/liquidates"
    q = "limit=5"
    hdr = _gate_sign_v4("GET", path, q, "")
    url = f"{host}{path}?{q}"
    raw, err = _http_get(
        url,
        headers={
            "Accept": "application/json",
            "KEY": hdr["KEY"],
            "SIGN": hdr["SIGN"],
            "Timestamp": hdr["Timestamp"],
        },
    )
    if err:
        return {"enabled": True, "ok": False, "error": err}
    try:
        arr = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as e:
        return {"enabled": True, "ok": False, "error": str(e)}
    if isinstance(arr, dict) and arr.get("label"):
        return {"enabled": True, "ok": False, "error": str(arr)[:300]}
    n = len(arr) if isinstance(arr, list) else 0
    return {"enabled": True, "ok": True, "summary": f"最近清算记录 {n} 条（limit=5）"}


def _refresh_bundle(ccxt_symbol: str) -> Dict[str, Any]:
    return {
        "coinglass": _fetch_coinglass(ccxt_symbol),
        "cryptoquant": _fetch_cryptoquant(),
        "lunarcrush": _fetch_lunarcrush(ccxt_symbol),
        "binance_signed": _fetch_binance_signed(),
        "gate_signed": _fetch_gate_signed_liquidates(),
        "refreshed_at": time.time(),
    }


def get_third_party_cached(ccxt_symbol: str) -> Dict[str, Any]:
    """按 ``ccxt_symbol`` 刷新 Coinglass/LunarCrush 币种；其余全局缓存 ``_TTL_SEC``。"""
    sym = (ccxt_symbol or "BTC/USDT").strip()
    now = time.time()
    with _lock:
        age = now - float(_cache.get("ts") or 0.0)
        prev = dict(_cache.get("data") or {})
    if age < _TTL_SEC and prev and prev.get("_symbol") == sym:
        return prev
    data = _refresh_bundle(sym)
    data["_symbol"] = sym
    with _lock:
        _cache["ts"] = time.time()
        _cache["data"] = data
    return data


def third_party_metrics_html_rows(ccxt_symbol: str) -> str:
    import html as _html

    def esc(s: Any) -> str:
        return _html.escape(str(s), quote=True)

    b = get_third_party_cached(ccxt_symbol)

    def row(title: str, d: dict) -> str:
        if not d.get("enabled"):
            return f"<tr><td>{esc(title)}</td><td class=\"muted\">{esc(d.get('summary', '—'))}</td></tr>"
        if d.get("ok"):
            extra = f" · {esc(d.get('via', ''))}" if d.get("via") else ""
            return f"<tr><td>{esc(title)}</td><td>{esc(d.get('summary', '—'))}{extra}</td></tr>"
        return f"<tr><td>{esc(title)}</td><td class=\"muted\">{esc(d.get('error', '失败'))}</td></tr>"

    block = "\n".join(
        [
            '<tr><td colspan="2" style="padding-top:10px;border-top:1px solid rgba(255,255,255,.12)"><strong>指标参考 · 第三方与签名接口（.env 密钥）</strong></td></tr>',
            row("Coinglass（短线核心）", b.get("coinglass") or {}),
            row("CryptoQuant", b.get("cryptoquant") or {}),
            row("LunarCrush", b.get("lunarcrush") or {}),
            row("币安合约账户（签名）", b.get("binance_signed") or {}),
            row("Gate 永续清算（签名）", b.get("gate_signed") or {}),
        ]
    )
    return block
