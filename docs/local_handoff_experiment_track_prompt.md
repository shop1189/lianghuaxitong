# 本地 / 对端机：实验轨变更操作与回执（可复制）

> **用途**：发给「将要动线上或类线上进程」的同事，让对方按同一套步骤操作并回传表格字段。  
> **权威环境变量列表**：`live_trading.py` 文件**开头 docstring**（约第 1～45 行起，「环境变量速查」整段；含 `LONGXIA_EXPERIMENT_*`、`LONGXIA_MARKOV_*` 等）。**不要**凭记忆猜默认值。  
> **合约 / 永续价口径**：见同目录 **`docs/local_handoff_contract_price_swap.md`**（与本文独立，避免混在实验轨一条里）。

---

## 一、可复制正文（发给执行人）

请按顺序执行；**只改与实验轨相关的 env**（名称以 `LONGXIA_EXPERIMENT_` 为主，及 `LONGXIA_MARKOV_*`、`LONGXIA_USE_MARKOV_THRESHOLD_TEMPLATE` 等；完整白名单以 `live_trading.py` 顶部注释为准），**勿改**与密钥、API Key、数据库连接无关的其它配置，除非另有工单。

1. **备份**  
   - 备份当前运行目录下：`.env`（或你们实际使用的 env 文件）、`live_trading_state.json`、`trade_memory.json`（若体积大则只备份与实验轨相关的最近片段或按运维规范）。  
   - 若有 systemd/supervisor 配置，记录当前 unit 名称与 `ExecStart`。

2. **拉代码**  
   - `git fetch` → `git checkout <约定分支>` → `git pull`，确认 `HEAD` 与工单要求一致。

3. **语法自检**  
   - 在**将用于启动的同一 venv** 下：  
     `python -m py_compile live_trading.py main.py`（或工单指定的入口文件）。  
   - 失败则**停止**，不要重启进程。

4. **只改实验轨相关 env**  
   - 在 `.env` 或进程环境中**仅**调整实验轨/Markov 相关项（示例：`LONGXIA_EXPERIMENT_MODE`、`LONGXIA_EXPERIMENT_TRACK`、`LONGXIA_MARKOV_TEMPLATE`、`LONGXIA_USE_MARKOV_THRESHOLD_TEMPLATE` 等）。  
   - **权威列表与默认值**：见 `live_trading.py` 顶部「环境变量速查」。  
   - **不要**在此步骤粘贴整份 `.env` 到聊天或工单。

5. **重启进程**  
   - 按你们标准方式重启（systemd / screen / docker / 手工 nohup 等），确认新进程已加载 env（必要时 `truss`/日志时间戳核对）。

6. **冒烟**  
   - **决策页**：打开与实验轨相关的标的/页面，确认无 500、关键字段有值。  
   - **版本接口**：`GET /api/version`（见 `main.py` 中路由），保存返回 JSON 一两行关键字段即可（**不要**整页 HTML）。

7. **回滚方式**（若异常）  
   - 恢复步骤 1 的 `.env` / 状态文件备份；`git checkout` 回滚到上一已知良好 `HEAD`；重启进程。  
   - 若动过 `trade_memory.json` / `live_trading_state.json`，按备份恢复或按运维手册处理。

---

## 二、回执（请对方填表回传）

**不要回传**：整份 `.env`、任何私钥/Secret、决策页整页 HTML、完整 `trade_memory` 正文。

| 字段 | 填写说明 |
|------|----------|
| 机器标识 / 项目路径 | 如 `hostname` + 仓库绝对路径（可打码中间段） |
| `git rev-parse HEAD` | 当前运行代码完整哈希 |
| 分支名 | 如 `main` |
| Python 版本 / venv 路径 | `python -V`；venv 激活路径或容器镜像 tag |
| 启动方式与 PID | systemd 服务名 **或** 启动命令摘要；主进程 **PID** |
| 本次改动的 env **白名单**（键名即可） | 仅列改动的 `LONGXIA_*` 键，**不要**给值若含敏感；非敏感值可给 |
| `python -m py_compile …` 结果 | `OK` / 报错末行 |
| 永续价自检一句 | 见 **`docs/local_handoff_contract_price_swap.md`** 中自检项一句结论（若该文档未更新则写「按现场口径已核对 / 未改价源」） |
| `/api/version` JSON 摘要 | 截取 `ENGINE_VERSION` 或等价字段 1～3 行 |
| 实验轨现象 1～3 句 | 如：是否有新 memos、是否仍 0 笔、日志是否有报错关键词 |
| 是否动过 `trade_memory.json` | 是 / 否 |
| 是否动过 `live_trading_state.json` | 是 / 否 |

---

## 三、与回测侧对齐提醒

本地同源回测请仍使用 **`backtest.py`** + 与线上一致的 `LONGXIA_EXPERIMENT_*`（及 Markov 相关项）；两轨语义见 **`docs/trade_memory_two_tracks.md`**。本文**不替代**回测工单，仅覆盖**进程侧**实验轨变更与回执。

---

## 四、与 GitHub SSOT（文件互通）

- **权威树**：`git@github.com:shop1189/lianghuaxitong.git` 的 **`origin/main`**。工单请贴 **`git rev-parse HEAD`**（或短 SHA）+ **本文件相对路径**，避免长文手抄。  
- **若仅在某台机器 `git commit` 而未 `git push`**：其它环境 **`git pull` 无法对齐该对象**；请运维或已配 **GitHub 写权限** 的机器尽快 **push**，或由本地段合并等价变更后 **push**，再全员 **pull**。
