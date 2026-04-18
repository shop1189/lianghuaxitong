#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并两份 trade_memory.json（顶层数组或 envelope trades），按 (symbol, entry_time, entry, direction) 去重。

恢复场景：旧备份里有几千条，当前机子上只剩几百条，可把旧文件与现文件合并后再覆盖。

  python3 scripts/merge_trade_memory.py \\
    --a /path/to/older_trade_memory.json \\
    --b /path/to/current_trade_memory.json \\
    --out /path/to/merged.json

检查合并结果笔数后再 mv 到项目根 trade_memory.json，并重启进程。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _parse(raw: Any) -> Tuple[List[dict], Dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)], {}
    if isinstance(raw, dict) and isinstance(raw.get("trades"), list):
        env = {k: v for k, v in raw.items() if k != "trades"}
        return [x for x in raw["trades"] if isinstance(x, dict)], env
    return [], {}


def _key(r: dict) -> Tuple[str, str, str, str]:
    return (
        str(r.get("symbol") or ""),
        str(r.get("entry_time") or ""),
        str(r.get("entry") or ""),
        str(r.get("direction") or ""),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="第一份（通常较旧、样本多）")
    ap.add_argument("--b", required=True, help="第二份（通常较新）")
    ap.add_argument("--out", required=True, help="合并输出路径")
    args = ap.parse_args()
    pa, pb, pout = Path(args.a), Path(args.b), Path(args.out)

    ra = json.loads(pa.read_text(encoding="utf-8"))
    rb = json.loads(pb.read_text(encoding="utf-8"))
    la, ena = _parse(ra)
    lb, enb = _parse(rb)

    seen: set[Tuple[str, str, str, str]] = set()
    merged: List[dict] = []
    for r in la + lb:
        k = _key(r)
        if k in seen:
            continue
        seen.add(k)
        merged.append(r)

    env = ena or enb
    if env:
        out_obj = {**env, "trades": merged}
    else:
        out_obj = merged

    pout.parent.mkdir(parents=True, exist_ok=True)
    pout.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"合并完成: {len(la)} + {len(lb)} -> 去重后 {len(merged)} 条，已写入 {pout}")


if __name__ == "__main__":
    main()
