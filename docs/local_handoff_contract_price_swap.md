# Gate 现货 / USDT 永续（swap）口径 — 本地交接

> 与 **`docs/local_handoff_experiment_track_prompt.md`** 分拆：本文只管**价源与 CCXT 类型**；实验轨 env 见该文 + `live_trading.py` 顶部「环境变量速查」。

---

## 1. 当前代码行为（以本仓库树为准；合并后请 `git pull` 再核对）

| 能力 | 位置（约） | 说明 |
|------|------------|------|
| **现货 ticker / OHLCV 主路径** | `data_fetcher.py`：`fetch_ticker`、`fetch_ohlcv` → `build_indicator_snapshot`（`data/fetcher.py`） | 使用 **Gate 现货** CCXT 实例（无 `defaultType` 时即为现货）。 |
| **决策页现货展示价** | `live_trading.LiveTrading.fetch_current_ticker_price` | 与 `data_fetcher._fetch_current_ticker_price_sync` 一致。 |
| **永续（swap）展示价** | `live_trading.LiveTrading.fetch_futures_ticker_price` | 单独 `ccxt.gateio`，并设 **`options["defaultType"] = "swap"`**，`fetch_ticker(symbol)` 取 **USDT 永续** last。 |

**协调方说明（与运维对齐用）**：若通过环境变量 **`LONGXIA_CCXT_DEFAULT_TYPE`** 统一 Gate CCXT 的 `defaultType`（例如默认 **`swap`**），则 **K 线 / `fetch_ticker` / `fetch_current_ticker_price`** 等路径须与 `data_fetcher.py`、`data/fetcher.py` 及 `_ccxt_default_type()`（若分支已引入）**保持一致**；**回滚为现货口径**时，将该变量设为 **`spot`** 或 **`cash`**（以你们 Gate/CCXT 约定为准），**改 env 后必须重启进程**。

> 若你方 `origin/main` 上某提交才引入 `LONGXIA_CCXT_DEFAULT_TYPE` / `_ccxt_default_type`，**以 pull 后的实际 `grep` 结果为准**，本文表格仅描述本机当前可见实现。

---

## 2. 操作与回滚（摘要）

1. **改口径前**：备份 `.env`、记录当前 `LONGXIA_CCXT_DEFAULT_TYPE`（若存在）及进程启动方式。  
2. **修改**：仅调整 env（及工单允许的代码合并），**勿**在聊天贴整份 `.env`。  
3. **重启**：使 CCXT 客户端重建。  
4. **冒烟**：决策页现货/合约两行是否与预期一致；`GET /api/version` 仍 200。  
5. **回滚**：恢复 env 备份 + 重启；必要时 `git revert` / 回退 `HEAD`（按工单）。

---

## 3. 回执用「永续价自检一句」示例

- 「永续价仍走 `fetch_futures_ticker_price` 的 swap 实例；现货价仍走 `fetch_current_ticker_price`；与变更前一致。」  
- 或：「已设 `LONGXIA_CCXT_DEFAULT_TYPE=swap`，K 线与 ticker 经抽样与 Gate 网页永续一致；决策页无 500。」

---

## 4. 检查清单

- [ ] 现货 last 与永续 last 价差在合理范围（非明显同值错接）  
- [ ] 日志无连续 CCXT 报错  
- [ ] 实验轨/主池用到的价格字段与工单约定一致  

---

*工单贴 **提交 SHA + 本路径** 即可；勿贴密钥。*
