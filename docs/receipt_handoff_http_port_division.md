# 回执：HTTP 端口分工与代码一致性（转 仓位 / 资金 / 杠杆管理 侧）

**日期**：2026-04-21  
**仓库**：`longxia_system`  
**用途**：本机并行跑 **Phase-1 风险真理层 + Web 验收** 与 **回测 / 快轨** 时，端口固定分工，避免探活、压测、人工验收打错实例。

---

## 1. 约定摘要（执行口径）

| 场景 | 端口 | 说明 |
|------|------|------|
| `python3 main.py`（Web / 决策页 / `/api/version`）**未**设置 `LONGXIA_HTTP_PORT` / `PORT` | **18080** | Phase-1 风险真理层 + Web 验收默认实例 |
| 回测 / 快轨并行（`exp_fastlane_*.env` 等） | **8080** | 通过 `LONGXIA_HTTP_PORT=8080` 绑定第二套进程，与 18080 **并行、不抢端口** |
| 任意覆盖 | `LONGXIA_HTTP_PORT` 或 `PORT` | 与容器 / systemd 习惯一致 |

**单一说明文档**：`docs/RISK_TRUTH_LAYER_PHASE1.md` → 章节 **Run** →「推荐端口分工（本机并行）」。

---

## 2. 已落地文件清单（便于对账）

| 路径 | 变更要点 |
|------|----------|
| `main.py` | `uvicorn` 默认端口 **18080**；docstring 与 Phase-1 文档一致；部署自检示例 URL 为 **18080** |
| `scripts/decision_pressure.py` | 未设置 `LONGXIA_HTTP_PORT` / `PORT` 时，默认基址端口 **18080**（与裸起 `main.py` 一致）；快轨 shell 若已 `export LONGXIA_HTTP_PORT=8080` 则自动跟 env |
| `scripts/exp_track_fastlane_3day.sh` | 探活：`http://127.0.0.1:${LONGXIA_HTTP_PORT:-8080}/api/version`，与所 `source` 的 `exp_fastlane_*.env` 一致；文件头注释标明勿与 Phase-1 默认实例混淆 |
| `config/exp_fastlane_A.env`、`config/exp_fastlane_B.env` | 含 `LONGXIA_HTTP_PORT=8080`；首行注释说明与默认 **18080** 并行 |
| `config/http_port_backtest.env` | 显式 `LONGXIA_HTTP_PORT=8080`，供回测/快轨一键 `source` |
| `config/http_port_phase1_web.env` | 显式 `LONGXIA_HTTP_PORT=18080`，与 Phase-1/Web 默认语义一致（可选 `source`） |
| `.cursor/rules/http-port-conventions.mdc` | 开发侧强制对齐上述口径（`alwaysApply`） |
| `docs/RISK_TRUTH_LAYER_PHASE1.md` | 端口分工下补充便捷 env 文件名 |

**已移除**：`config/http_port_leverage_lab.env`（旧「杠杆实验室专用文件名」易与当前「18080 = Phase-1 默认 Web」语义冲突，故删除；端口仍仅由 env / 默认表达）。

---

## 3. 对侧可执行的自检步骤

1. **Phase-1 / Web 默认实例**（预期 **18080**）  
   - 在项目根：`python3 main.py`（不设端口 env）  
   - 验证：`curl -s http://127.0.0.1:18080/api/version` 有 JSON。

2. **回测 / 快轨实例**（预期 **8080**）  
   - `set -a && source config/exp_fastlane_A.env && set +a && python3 main.py`（或 `http_port_backtest.env`）  
   - 验证：`curl -s http://127.0.0.1:8080/api/version` 有 JSON；且 **18080** 上仍可保留另一进程（若已启动）。

3. **编排脚本探活**  
   - 跑 `scripts/exp_track_fastlane_3day.sh` 时，`api/version` 请求应对应当前组的 `LONGXIA_HTTP_PORT`（快轨为 **8080**），不应写死误指 **18080**。

---

## 4. 责任边界说明（给资金 / 杠杆侧）

- 本回执仅覆盖 **HTTP 监听端口分工** 与 **脚本/配置一致性**，不涉及交易所杠杆参数、下单限额等业务规则的变更。  
- Phase-1 风险层行为仍以 `docs/RISK_TRUTH_LAYER_PHASE1.md` 全文为准（`observe`、审计日志路径等）。

---

## 5. 签章栏（可选）

| 角色 | 姓名 | 日期 | 备注 |
|------|------|------|------|
| 工程交付 | | | |
| 仓位 / 资金 / 杠杆管理 收悉 | | | |
