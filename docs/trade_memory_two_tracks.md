# trade_memory 两轨说明（主观察池 / 规则实验轨）

## 命名与字段（不改数据结构，仅概念）

| 页面用语 | `trade_memory` 中 | 含义 |
|----------|---------------------|------|
| **主观察池** | `virtual_signal: true` | 与决策页 `get_v313_decision_snapshot` + `sync_virtual_memos_from_state` 同步，大版本外以**微调**为主。 |
| **规则实验轨** | `virtual_signal` 为假 / 缺省 | 用于规则/门槛**实验**与大版本对齐后的试验；统计与主观察池**分列**。 |

两轨都是**本地 memos 模拟记账**，不是交易所成交；手动跟单可自行对比两轨后再选择参考。

## 为什么「规则实验轨」可能长期没有订单？

当前 **Web / 决策主路径**只跑：

- `live_trading.get_v313_decision_snapshot`
- `sync_virtual_memos_from_state` → 写入 **`virtual_signal: true`**（主观察池）

而 **规则实验轨**（非虚拟）已平仓记录，历史上主要来自 **`evolution_core.TradeMemory`** 链路：

- `add_open_trade` → `check_close_trade` → `save_record`（记录中**无** `virtual_signal` 或视为假）
- 对外入口之一是 `ai_decision_upgrade.ai_analysis_multi_timeframe()` 末尾的 `ai_evo.record(...)`，且需配合周期性 `ai_evo.tick(价格)` 等

若线上 **未** 在常驻进程里调用上述 AI 多周期 + `ai_evo.record`，则规则实验轨**不会产生新流水**，统计为 0 是**预期现象**，不是随机故障。

## 和「真实单 / 虚拟单」口语的关系

代码层只有 **virtual_signal 真/假** 两档；口语「真实单」若指「非虚拟 memos」，对应规则实验轨这条写入链，**未必接交易所实盘**，请仍以字段与文档为准。

## 后续若要规则实验轨产生样本（讨论后再动代码）

需在**不破坏**主观察池现有逻辑的前提下，显式把实验规则接到会写入 **非 virtual_signal** 且会 `tick/平仓` 的流程（或单独「记录策略」层），并建议用**配置开关**默认关闭，便于回滚。
