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
