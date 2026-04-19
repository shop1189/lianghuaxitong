# -*- coding: utf-8 -*-
"""
带单老师业务轨（内部统计）：与主观察池 / 实验轨并行，用 trade_memory 字段 ``signal_track`` 分桶。
写入逻辑由后续 LONGXIA_TEACHER_* 开关接入；本模块仅常量与说明。
"""
from __future__ import annotations

# 起号轨（展示向）：冲排名、单日少量高质量单
SIGNAL_TRACK_BOOST = "boost"
# 实战轨（资金向）：低杠杆、长持仓、控回撤
SIGNAL_TRACK_COMBAT = "combat"
