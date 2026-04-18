# -*- coding: utf-8 -*-
"""trade_memory.json 写入前限速自动备份，降低误覆盖、部署换文件导致的一周样本丢失风险。"""
from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

# 同一文件两次备份最短间隔（秒）；过短会刷屏且占盘
_MIN_INTERVAL_SEC = float(os.environ.get("LONGXIA_TRADE_MEMORY_AUTOBAK_MIN_SEC", str(6 * 3600)))
# 至少这么大才备份，避免空文件/测试环境狂备
_MIN_BYTES = 2048
# 保留最近 N 个自动备份
_KEEP = 14


def maybe_backup_trade_memory(path: Path) -> None:
    """在覆盖写入前，将现有文件复制到 ``backups/trade_memory_autosave/``（限速）。"""
    try:
        p = Path(path).resolve()
        if not p.exists():
            return
        sz = p.stat().st_size
        if sz < _MIN_BYTES:
            return
        root = p.parent
        bdir = root / "backups" / "trade_memory_autosave"
        bdir.mkdir(parents=True, exist_ok=True)
        ts_file = bdir / ".last_backup_epoch"
        now = time.time()
        last = 0.0
        if ts_file.exists():
            try:
                last = float(ts_file.read_text(encoding="utf-8").strip())
            except Exception:
                last = 0.0
        if now - last < _MIN_INTERVAL_SEC:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = bdir / f"trade_memory_{stamp}.json"
        shutil.copy2(p, dest)
        ts_file.write_text(str(now), encoding="utf-8")
        files = sorted(
            bdir.glob("trade_memory_*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        for old in files[_KEEP:]:
            try:
                old.unlink()
            except Exception:
                pass
    except Exception:
        pass
