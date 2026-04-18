#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段 1 快速健康检查：交易记忆、实盘 state、可选 pandas_ta、可选 server.pid。

退出码：0 全部通过；1 存在失败项（便于 cron / 监控）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    errs: list[str] = []

    def ok(msg: str) -> None:
        print(f"OK  {msg}")

    def fail(msg: str) -> None:
        print(f"ERR {msg}")
        errs.append(msg)

    for rel in ("trade_memory.json", "live_trading_state.json"):
        p = ROOT / rel
        if not p.exists():
            fail(f"{rel} 不存在")
            continue
        try:
            json.loads(p.read_text(encoding="utf-8"))
            ok(f"{rel} 可解析")
        except Exception as ex:
            fail(f"{rel} JSON 解析失败: {ex}")

    try:
        import pandas_ta  # noqa: F401

        ok("pandas_ta 可导入")
    except Exception:
        try:
            import pandas_ta_classic  # noqa: F401

            ok("pandas_ta_classic 可导入")
        except Exception as ex2:
            fail(f"pandas_ta / pandas_ta_classic 导入失败: {ex2}")

    pidf = ROOT / "server.pid"
    if pidf.exists():
        try:
            pid = int(pidf.read_text(encoding="utf-8").strip().split()[0])
            ok(f"server.pid -> {pid}（仅提示，不校验进程存活）")
        except Exception as ex:
            fail(f"server.pid 读取失败: {ex}")
    else:
        ok("server.pid 不存在（可选）")

    print("---")
    if errs:
        print(f"phase1_health_check: {len(errs)} 项失败")
        return 1
    print("phase1_health_check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
