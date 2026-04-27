"""
可选第三方 / 签名接口：仅从环境变量读取 Key，不写死在仓库。

- Coinglass：REST v4，头 ``CG-API-KEY``
- CryptoQuant：``Authorization: Bearer``
- LunarCrush：优先 ``api4`` Bearer；失败则尝试 ``api3`` 的 ``?key=``
- 币安 U 本位：若配置 ``BINANCE_API_KEY/SECRET``，拉 ``/fapi/v2/account`` 摘要（需合约账户读权限）
- Gate 永续：若配置 ``LONGXIA_GATE_API_KEY/SECRET``（或 ``GATE_API_KEY/SECRET``），拉 ``/futures/usdt/liquidates`` 最近几条（需合约只读 Key）

结果供决策页展示；失败时返回 ``error`` 短文案，不抛异常。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from typing import Any, Dict, Optional
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


def _fetch_coinglass() -> Dict[str, Any]:
    key = (os.environ.get("COINGLASS_API_KEY") or "").strip()
    if not key or len(key) < 8:
        return {"enabled": False, "summary": "未配置 COINGLASS_API_KEY"}
    headers = {"accept": "application/json", "CG-API-KEY": key}
    coin = (os.environ.get("LONGXIA_COINGLASS_SYMBOL") or "BTC").strip().upper()
    pair = (os.environ.get("LONGXIA_COINGLASS_PAIR") or f"{coin}USDT").strip().upper()
    exchange = (os.environ.get("LONGXIA_COINGLASS_EXCHANGE") or "Binance").strip()
    interval = (os.environ.get("LONGXIA_COINGLASS_INTERVAL") or "4h").strip()

    def _req(path: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        raw, err = _http_get(f"https://open-api-v4.coinglass.com{path}", headers=headers)
        if err:
            return None, err
        try:
            j = json.loads((raw or b"").decode("utf-8", errors="replace"))
            if isinstance(j, dict):
                code = str(j.get("code") or "")
                if code and code != "0":
                    msg = str(j.get("msg") or "unknown")
                    return None, f"code={code} msg={msg}"
                return j, None
            return {"data": j}, None
        except Exception as ex:
            return None, str(ex)

    out: Dict[str, Any] = {"enabled": True, "ok": True}

    j0, e0 = _req("/api/futures/supported-coins")
    if e0:
        return {"enabled": True, "ok": False, "error": e0}
    data0 = (j0 or {}).get("data")
    n = len(data0) if isinstance(data0, list) else "—"
    out["summary"] = f"supported-coins 条数≈{n}"
    out["code"] = (j0 or {}).get("code")

    # 付费 key：尽量展示可实时读取的核心项；任一失败不阻断其他项。
    # 不同套餐/端点可能返回 401/404，统一通过 notes 回显，前端可见。
    notes = []

    j1, e1 = _req(
        f"/api/futures/funding-rate/history?symbol={pair}&exchange={exchange}&interval={interval}&limit=1"
    )
    if not e1 and j1:
        d1 = j1.get("data")
        if isinstance(d1, list) and d1:
            last = d1[-1] if isinstance(d1[-1], dict) else {}
            fr = (
                last.get("fundingRate")
                or last.get("funding_rate")
                or last.get("close")
            )
            if fr is not None:
                out["funding_rate"] = fr
    else:
        notes.append(f"funding:{e1}")

    j2, e2 = _req(
        f"/api/futures/open-interest/history?symbol={pair}&exchange={exchange}&interval={interval}&limit=1"
    )
    if not e2 and j2:
        d2 = j2.get("data")
        if isinstance(d2, list) and d2:
            last = d2[-1] if isinstance(d2[-1], dict) else {}
            oi = (
                last.get("openInterest")
                or last.get("open_interest")
                or last.get("value")
                or last.get("close")
            )
            if oi is not None:
                out["open_interest"] = oi
    else:
        notes.append(f"oi:{e2}")

    j3, e3 = _req(
        f"/api/futures/liquidation/history?symbol={pair}&exchange={exchange}&interval={interval}&limit=1"
    )
    if not e3 and j3:
        d3 = j3.get("data")
        if isinstance(d3, list) and d3:
            last = d3[-1] if isinstance(d3[-1], dict) else {}
            lv = (
                last.get("liquidation")
                or last.get("value")
                or last.get("sum")
                or last.get("amount")
                or (
                    float(last.get("long_liquidation_usd") or 0.0)
                    + float(last.get("short_liquidation_usd") or 0.0)
                )
            )
            if lv is not None:
                out["liquidation_1h"] = lv
    else:
        notes.append(f"liq:{e3}")

    j4, e4 = _req(
        f"/api/futures/global-long-short-account-ratio/history?symbol={pair}&exchange={exchange}&interval={interval}&limit=1"
    )
    if not e4 and j4:
        d4 = j4.get("data")
        if isinstance(d4, list) and d4:
            last = d4[-1] if isinstance(d4[-1], dict) else {}
            ls = (
                last.get("longShortRatio")
                or last.get("long_short_ratio")
                or last.get("ratio")
                or last.get("global_account_long_short_ratio")
            )
            if ls is not None:
                out["global_long_short_ratio"] = ls
    else:
        notes.append(f"ls_ratio:{e4}")

    if notes:
        out["notes"] = notes
    out["interval"] = interval
    out["pair"] = pair
    out["exchange"] = exchange
    return out


def _fetch_cryptoquant() -> Dict[str, Any]:
    token = (os.environ.get("CRYPTOQUANT_API_TOKEN") or "").strip()
    if not token or len(token) < 8:
        return {"enabled": False, "summary": "未配置 CRYPTOQUANT_API_TOKEN"}
    url = "https://api.cryptoquant.com/v1/discovery/endpoints?format=json"
    raw, err = _http_get(
        url, headers={"Authorization": f"Bearer {token}", "accept": "application/json"}
    )
    if err:
        return {"enabled": True, "ok": False, "error": err}
    try:
        j = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as e:
        return {"enabled": True, "ok": False, "error": str(e)}
    st = j.get("status") or {}
    return {
        "enabled": True,
        "ok": True,
        "summary": f"discovery 状态 code={st.get('code')} msg={st.get('message', '')[:80]}",
    }


def _fetch_lunarcrush(coin_symbol: str) -> Dict[str, Any]:
    key = (os.environ.get("LUNARCRUSH_API_KEY") or "").strip()
    if not key or len(key) < 8:
        return {"enabled": False, "summary": "未配置 LUNARCRUSH_API_KEY"}
    coin = (coin_symbol or "BTC").split("/")[0].upper()
    # api4 Bearer
    url4 = f"https://lunarcrush.com/api4/public/coins/{coin}/v1"
    raw, err = _http_get(
        url4,
        headers={"Authorization": f"Bearer {key}", "accept": "application/json"},
    )
    if not err and raw:
        try:
            j = json.loads(raw.decode("utf-8", errors="replace"))
            d = j.get("data") if isinstance(j, dict) else j
            if isinstance(d, dict):
                gs = d.get("galaxy_score") or d.get("galaxyScore")
                ar = d.get("alt_rank") or d.get("altRank")
                return {
                    "enabled": True,
                    "ok": True,
                    "via": "api4",
                    "summary": f"{coin} Galaxy≈{gs} AltRank≈{ar}",
                }
        except Exception:
            pass
    # api3 query key
    url3 = f"https://lunarcrush.com/api3/coins/{coin}?data=market,galaxy,alt_rank&key={key}"
    raw2, err2 = _http_get(url3)
    if err2:
        return {"enabled": True, "ok": False, "error": err2 or err}
    try:
        j2 = json.loads(raw2.decode("utf-8", errors="replace"))
    except Exception as e:
        return {"enabled": True, "ok": False, "error": str(e)}
    if isinstance(j2, dict) and j2.get("status") == "error":
        return {"enabled": True, "ok": False, "error": str(j2.get("message", j2))[:200]}
    d0 = j2.get("data") if isinstance(j2, dict) else None
    if isinstance(d0, dict):
        gs = d0.get("galaxy_score")
        ar = d0.get("alt_rank")
        return {
            "enabled": True,
            "ok": True,
            "via": "api3",
            "summary": f"{coin} Galaxy≈{gs} AltRank≈{ar}",
        }
    return {"enabled": True, "ok": True, "via": "api3", "summary": "已返回（结构未解析）"}


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
    return {
        "enabled": True,
        "ok": True,
        "summary": f"合约账户 totalWalletBalance≈{twb} unrealized≈{te}",
    }


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
        "coinglass": _fetch_coinglass(),
        "cryptoquant": _fetch_cryptoquant(),
        "lunarcrush": _fetch_lunarcrush(ccxt_symbol),
        "binance_signed": _fetch_binance_signed(),
        "gate_signed": _fetch_gate_signed_liquidates(),
        "refreshed_at": time.time(),
    }


def get_third_party_cached(ccxt_symbol: str) -> Dict[str, Any]:
    """按 ``ccxt_symbol`` 刷新 LunarCrush 币种；其余全局缓存 ``_TTL_SEC``。"""
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

    def _friendly_error(err: Any) -> str:
        s = str(err or "").strip()
        low = s.lower()
        if not s:
            return "暂不可用（未返回错误详情）"
        if "error 1010" in low or "browser_signature_banned" in low:
            return "CryptoQuant 被 Cloudflare 拦截（1010），当前服务器指纹受限；建议改代理/IP 或改官方白名单接入。"
        if "invalid endpoint" in low:
            return "接口端点不可用（当前 key/套餐不支持该 LunarCrush 端点）。"
        if "timed out" in low or "timeout" in low:
            return "请求超时（可重试，或延长超时/降低刷新频率）。"
        if len(s) > 180:
            return s[:180] + "…"
        return s

    b = get_third_party_cached(ccxt_symbol)

    def row(title: str, d: dict) -> str:
        if not d.get("enabled"):
            return f"<tr><td>{esc(title)}</td><td class=\"muted\">{esc(d.get('summary', '—'))}</td></tr>"
        if d.get("ok"):
            extra = f" · {esc(d.get('via', ''))}" if d.get("via") else ""
            return f"<tr><td>{esc(title)}</td><td>{esc(d.get('summary', '—'))}{extra}</td></tr>"
        return f"<tr><td>{esc(title)}</td><td class=\"muted\">{esc(_friendly_error(d.get('error', '失败')))}</td></tr>"

    enabled_cnt = 0
    ok_cnt = 0
    for k in ("coinglass", "cryptoquant", "lunarcrush", "binance_signed", "gate_signed"):
        d = b.get(k) or {}
        if d.get("enabled"):
            enabled_cnt += 1
            if d.get("ok"):
                ok_cnt += 1
    ts = float(b.get("refreshed_at") or 0.0)
    if ts > 0:
        age_sec = max(0.0, time.time() - ts)
        freshness = f"缓存约 {age_sec:.1f} 秒前刷新"
    else:
        freshness = "缓存时间未知"

    block = "\n".join(
        [
            f'<tr><td colspan="2" style="padding-top:10px;border-top:1px solid rgba(255,255,255,.12)"><strong>指标参考 · 第三方与签名接口（.env 密钥）</strong> · {esc(freshness)}</td></tr>',
            f'<tr><td>第三方数据可用性</td><td>{esc(f"已启用 {enabled_cnt} 项 · 成功 {ok_cnt} 项 · 失败 {max(0, enabled_cnt-ok_cnt)} 项")}</td></tr>',
            row("Coinglass", b.get("coinglass") or {}),
            (
                f'<tr><td>Coinglass · 资金费率({esc((b.get("coinglass") or {}).get("interval", "4h"))}最近)</td><td>{esc((b.get("coinglass") or {}).get("funding_rate", "暂缺（端点或权限受限）"))}</td></tr>'
            ),
            (
                f'<tr><td>Coinglass · OI({esc((b.get("coinglass") or {}).get("interval", "4h"))}最近)</td><td>{esc((b.get("coinglass") or {}).get("open_interest", "暂缺（端点或权限受限）"))}</td></tr>'
            ),
            (
                f'<tr><td>Coinglass · 爆仓额({esc((b.get("coinglass") or {}).get("interval", "4h"))}最近)</td><td>{esc((b.get("coinglass") or {}).get("liquidation_1h", "暂缺（端点或权限受限）"))}</td></tr>'
            ),
            (
                f'<tr><td>Coinglass · 全网多空比({esc((b.get("coinglass") or {}).get("interval", "4h"))}最近)</td><td>{esc((b.get("coinglass") or {}).get("global_long_short_ratio", "暂缺（端点或权限受限）"))}</td></tr>'
            ),
            row("CryptoQuant", b.get("cryptoquant") or {}),
            row("LunarCrush", b.get("lunarcrush") or {}),
            row("币安合约账户（签名）", b.get("binance_signed") or {}),
            row("Gate 永续清算（签名）", b.get("gate_signed") or {}),
        ]
    )
    return block
