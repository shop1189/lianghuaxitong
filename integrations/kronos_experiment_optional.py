# -*- coding: utf-8 -*-
"""
可选：接入 shiyu-coder/Kronos 真模型时在此实现推理入口。

当前默认不加载模型（避免 HF 下载、GPU 依赖拖垮扫描线程）。

若已克隆 Kronos 并配置好环境，可实现例如::

    def experiment_direction_from_kronos(symbol: str, ohlcv_df) -> str | None:
        \"\"\"返回 \"做多\" / \"做空\" / None（不参与）。\"\"\"
        ...

并在 live_trading 中将 LONGXIA_EXPERIMENT_MODE=kronos_model 与上述函数对接（第二阶段）。
"""
