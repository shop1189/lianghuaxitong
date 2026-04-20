# 全对话工作归档（本地段 · 断档回忆用）

> **用途**：整段对话窗口关闭后，按时间线回忆「问过什么、云端回了什么、本地改了什么、卡在哪、怎么修的」。  
> **维护**：随仓库走；新事实以 `git log` 为准。  
> **配套**：`docs/phase1_handoff_prompt_zh.md`（给 AI 的**短提示词** + 第二阶段命令入口）。

---

## 〇、全对话时间线（回忆索引）

下列按对话**大致先后顺序**整理；细节以正文各节为准。

1. **云端书面要求前置**  
   用户带入云端说明：分工（云实盘不动、本地验证）、实验轨 SSOT（`live_trading.py` 头注释）、`.env` 中 `LONGXIA_EXPERIMENT_MODE=legacy`、Markov 两项、标准 `backtest.py` 命令、`min_alignment_bundle` 交付物、主/实验两轨语义文档路径等。

2. **执行框架 A0→A5 + A4b + A6**  
   用户逐步指令「执行 A0/A1/…」。本地段在 WSL 中实际跑：`verify_env.sh`、`sync_from_server.sh`、环境 `grep LONGXIA_`、export legacy+Markov off、标准 experiment（500/2000）与 main 对照。  
   **现象**：对齐后 experiment 仍 0 笔，main 有数十笔 → 触发云端下一轮代码级复核。

3. **云端根因一：P0**  
   云端结论：`backtest.py` experiment 分支**固定**调用 `_experiment_entry_filter_kronos_light`，与线上 `LONGXIA_EXPERIMENT_MODE=legacy` 时 `_experiment_entry_filter` 不一致。  
   **本地段改动**：改为调用 `_experiment_entry_filter`；`summary.json` 增加 `experiment_mode`；更新 `_experiment_km_for_backtest_bar` 文档。  
   **现象**：legacy 下仍可能 0 笔（与云端预判的第二条根因一致）。

4. **云端根因二：P0.5（bayes）**  
   云端结论：`experiment_km_for_bar` 不含 `bayes_posterior_winrate`，线上在合并进快照前有 `beta_update_from_score_throttled`；legacy 过滤易因 post=0 恒失败。回测须**无副作用**等价。  
   **本地段改动**：新增 `live_trading.beta_posterior_mean_for_replay_bar`；`backtest.py` 在合并 `km_bar` 后写入 `bayes_posterior_winrate`（内存状态、K 线时间节流、不写 `bayes_beta_state.json`）。  
   **自测**：legacy experiment 500 根量级可出单。

5. **交付与签收**  
   生成/更新 `min_alignment_bundle.txt`；用户微信发文件给云端的路径说明（`\\wsl$\...`）；云端多轮「形式点验 / 签收」书面回执；用户转述云端对 P0/P0.5/bundle 的认可。

6. **GitHub push 与 SSH**  
   用户最初在 **PowerShell** 路径与 **WSL** 路径混淆；`git push` 遇 `known_hosts` 指纹提示（说明应对照 GitHub 官方指纹后输入 `yes`）；随后 **`Permission denied (publickey)`**；用户 **`ssh-keygen` 覆盖**旧钥；**Gitee** 与 **GitHub** 分平台绑 key 的说明；本地段代验 `ssh -T` + `git push` 成功。

7. **云端无法 fetch 与即时点验**  
   云端说明本机对象库尚无 `e9dd09b`、无法 `git show`，本地段贴出 **`git show e9dd09b --stat`** 供形式核对；云端签收 push 通知 + bundle，树校验待运维拉齐。

8. **阶段定义与「更大一坨」**  
   用户问第一阶段是否完成、与「主轨网格/阈值/FinRL」关系；本地段解释**范围边界**与**排期**。

9. **第二阶段：基线脚本与锁文件**  
   用户授权「你安排」commit：`pip_freeze_lock.sh`、`smoke_dual_track_3d_14d.sh`、handoff 增补、`.gitignore` 放行 `outputs/env/requirements_lock_*.txt` → **8f18a5b**。  
   云端要求三运维脚本进树 → **8026b3b**。

10. **记忆与全对话整理**  
    用户要求把对话工作装进记忆文件、下一步做什么；本地段写 `session_work_memory` 初版并 **4d0c53d** 链到 handoff。  
    **本次**：用户要求「整个对话框都整理」→ 扩充为本文件的**第〇节时间线 + 下文对话主题索引**。

---

## 一、角色与称呼约定

- **本地段**：本机 WSL / 仓库维护、回测、材料、Git push 的执行方（对话里的助手自称）。  
- **云端段**：对方运维/研发书面回执、签收、环境权威说明。  
- **勿混**：Gitee SSH 密钥展示 ≠ GitHub `git@github.com` 推送已配置；两平台分别检查。

---

## 二、云端书面要点（浓缩）

| 主题 | 云端口径（摘要） |
|------|------------------|
| 分工 | 云实盘不动；本地 `rsync` + `verify_env.sh` + 同源 `backtest.py` 验证。 |
| SSOT | `live_trading.py` 头部环境变量速查；根 `.env` 显式 `LONGXIA_EXPERIMENT_MODE=legacy` 等。 |
| 标准命令 | `legacy` + Markov off 下 SOL/USDT 1m experiment 等（见 bundle / handoff）。 |
| P0 | 回测须用 `_experiment_entry_filter`，不能写死 kronos_light。 |
| P0.5 | `bayes_posterior_winrate` 合并顺序与 `get_v313` 一致；回测勿污染 `bayes_beta_state.json`。 |
| 签收 | bundle + `git show --stat` 形式通过；对方本机 fetch 失败不阻塞；8026b3b 三脚本签收。 |

---

## 三、技术结论表（仍是最常翻的一块）

| 现象 | 根因 | 修复 |
|------|------|------|
| export legacy 仍 experiment 0 笔 | `backtest` 写死 kronos 过滤 | **P0** `_experiment_entry_filter` + `experiment_mode` |
| P0 后 legacy 仍 0 笔 | `km_bar` 缺 bayes，legacy 读 post=0 | **P0.5** `beta_posterior_mean_for_replay_bar` + 写入 `bayes_posterior_winrate` |
| main 有单 experiment 无 | 上两者之一或数据窗口 | 与「整链坏了」区分 |

---

## 四、本地执行清单（A 系列 + P1）

| 步骤 | 命令要点 | 结果记忆 |
|------|-----------|----------|
| A0 | `bash scripts/verify_env.sh` | PASS |
| A1 | `bash scripts/sync_from_server.sh` | PASS |
| A2 | `env \| grep LONGXIA_` → 文件 | 对齐前可为空 |
| A3 | export legacy + Markov off | 三行 ENV |
| A4/A4b | experiment limit 500/2000 | P0 前 0；修复后有单 |
| A6 | main 500 对照 | 有成交 |
| A5 | bundle 文本 | 曾遇 PowerShell 引号问题，改 pipe-to-wsl-bash |
| P1 | `kronos_light` 同参 | 0 笔作交叉记录入 bundle |

---

## 五、Git 提交链（GitHub `origin/main`）

| 哈希 | 内容 |
|------|------|
| **e9dd09b** | P0 + P0.5：`backtest.py`、`live_trading.py` |
| **8f18a5b** | 基线脚本、`phase1_handoff` 增补、`.gitignore` 放行 env lock、示例 `requirements_lock_*.txt` |
| **8026b3b** | `setup_new_machine.sh`、`sync_from_server.sh`、`verify_env.sh` + handoff |
| **4d0c53d** | `session_work_memory_zh.md` 初版 + handoff 顶部链到本文件 |

**说明**：提交正文里可能出现环境注入的 `Made-with: Cursor` trailer，云端已声明不影响签收；是否 `rebase` 清洗由团队自定。

---

## 六、产物与路径（便于搜）

| 类型 | 路径 |
|------|------|
| 一键提示 + 二阶段入口 | `docs/phase1_handoff_prompt_zh.md` |
| 本归档（全对话 + 技术） | `docs/session_work_memory_zh.md` |
| 对照 bundle（运行时生成，默认不进 Git） | `outputs/backtest_parallel/min_alignment_bundle.txt` |
| 锁依赖脚本 / 输出 | `scripts/pip_freeze_lock.sh`、`outputs/env/requirements_lock_*.txt` |
| 双轨 3d/14d | `scripts/smoke_dual_track_3d_14d.sh` → `outputs/baseline_smoke/` |
| Windows 看 WSL 文件 | `\\wsl$\Ubuntu\home\administrator\projects\longxia_system\...` |

---

## 七、踩坑与排障（对话里真出现过）

1. **在 `PS C:\>` 里跑 `cd ~/projects/...`**：不对，应 **`wsl` 进 bash** 或 `wsl -d Ubuntu -- bash -lc '...'`。  
2. **首次 SSH GitHub**：指纹确认后 `yes`；`publickey` → 生成/绑定 **GitHub** 用 key，不是只做 Gitee。  
3. **`ssh-keygen` 覆盖**：旧公钥在服务器上的 `authorized_keys` 需换**新公钥**配对。  
4. **`git commit` 报 trailer / PowerShell 吃字符**：用 **`bash -s` + heredoc** 或 `-F` 文件提交消息；`git push` 单独一行执行。  
5. **`.gitignore` 的 `outputs/`**：改为 `outputs/*` + 否定规则后才可跟踪 `outputs/env/requirements_lock_*.txt`。

---

## 八、与对话相关的「非 Git」约定

- 发给云端的材料：**不打密钥**；bundle / summary 可微信附件或工单。  
- **第一阶段**完成定义：对齐 + 能出单 + 材料 + 云端形式签收（不含主轨网格/上线阈值/FinRL 大一统）。  
- **第二阶段**入口：锁依赖 + `smoke_dual_track_3d_14d.sh`（见 handoff）。

---

## 九、下一步（操作 checklist）

1. **跑双轨小窗**：`bash scripts/smoke_dual_track_3d_14d.sh`，读 `outputs/baseline_smoke/*_summary.json`，写结论。  
2. **依赖变更再锁**：`bash scripts/pip_freeze_lock.sh`，按需 `git add` 新 lock。  
3. **云端**：能访问 GitHub 后 `git pull`，补 `git show e9dd09b` 树校验（非阻塞项）。  
4. **脏文件**：`main.py`、`bayes_beta_state.json` 等未与工单提交绑定，勿误推。

---

## 十、断档后怎么用最省时间

1. 打开 **`docs/session_work_memory_zh.md`**（本文件）→ 看 **第〇节时间线** 定位你记得片段。  
2. 需要让新 AI 接手 → 复制 **`docs/phase1_handoff_prompt_zh.md`** 里「给 AI 的一键提示词」整段。  
3. 对代码差异有疑问 → **`git show e9dd09b`** / **`git log -5 --oneline`**。

---

*归档说明：本节为「全对话」脉络整理，技术细节以各节与 Git 历史为准；若与某条聊天记录字面有出入，以当时工单与提交为准。*
