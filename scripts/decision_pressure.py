#!/usr/bin/env python3
import os
import threading
import time
import urllib.request

def _http_port() -> int:
    # 与 main.py 一致：无环境变量时默认 18080（Phase-1 Web）；快轨/回测 shell 已 export 8080 则自动对齐。
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


BASE = os.environ.get(
    "LONGXIA_PRESSURE_BASE", f"http://127.0.0.1:{_http_port()}"
)
SYMBOLS = os.environ.get(
    "LONGXIA_PRESSURE_SYMBOLS",
    "SOL%2FUSDT,BTC%2FUSDT,ETH%2FUSDT,DOGE%2FUSDT,XRP%2FUSDT,BNB%2FUSDT",
).split(",")
WORKERS = int(os.environ.get("LONGXIA_PRESSURE_WORKERS", "8"))
SLEEP_SEC = float(os.environ.get("LONGXIA_PRESSURE_SLEEP_SEC", "0.35"))
DURATION_SEC = int(os.environ.get("LONGXIA_PRESSURE_DURATION_SEC", "86400"))

ok = 0
err = 0
lock = threading.Lock()
stop_at = time.time() + DURATION_SEC


def hit(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False


def worker(worker_id: int) -> None:
    global ok, err
    i = worker_id
    n = len(SYMBOLS)
    while time.time() < stop_at:
        sym = SYMBOLS[i % n].strip()
        url = f"{BASE}/decision?symbol={sym}"
        passed = hit(url)
        with lock:
            if passed:
                ok += 1
            else:
                err += 1
        i += 1
        time.sleep(SLEEP_SEC)


def main() -> None:
    threads = []
    for idx in range(WORKERS):
        t = threading.Thread(target=worker, args=(idx,), daemon=True)
        t.start()
        threads.append(t)
    while time.time() < stop_at:
        time.sleep(60)
        with lock:
            print(f"[pressure] ok={ok} err={err} workers={WORKERS} sleep={SLEEP_SEC}", flush=True)
    for t in threads:
        t.join(timeout=1)
    with lock:
        print(f"[pressure] done ok={ok} err={err}", flush=True)


if __name__ == "__main__":
    main()
