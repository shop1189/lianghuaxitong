# -*- coding: utf-8 -*-
"""分批止盈 / 动态价位 — 功能开关（默认全关，与现有行为 100% 一致）。"""
from __future__ import annotations

import os


def dynamic_levels_enabled() -> bool:
    return os.environ.get("LONGXIA_DYNAMIC_LEVELS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def scaled_exit_enabled() -> bool:
    return os.environ.get("LONGXIA_SCALED_EXIT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def main_virtual_tp1_partial_enabled() -> bool:
    """主观察池虚拟单：TP1 部分锁定 + 保本抬损（默认开，与分批止盈二选一写仓）。"""
    return os.environ.get("LONGXIA_MAIN_VIRTUAL_TP1_PARTIAL", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
