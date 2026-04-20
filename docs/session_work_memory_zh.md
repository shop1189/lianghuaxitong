# 本轮工作会话记忆归档（本地段）

> 目的：对话窗口丢失后仍可恢复「做了什么、提交哈希、云端结论、下一步」。  
> 关联：`docs/phase1_handoff_prompt_zh.md`（给 AI 的一键提示词 + 第二阶段入口）。

---

## 一、业务目标与阶段划分

1. **第一阶段（已收口）**  
   实验轨同源回测与线上一致性：环境变量对齐、`backtest` 与 `live_trading` 入场/快照字段一致、能出单、材料交付、云端形式签收。  
   **不包含**：主轨大网格验收、上线阈值决策、FinRL 统一 requirements（另立项）。

2. **第二阶段（进行中入口）**  
   冻结基线（锁依赖 + 固定对照命令/脚本）→ 双轨最小验收（主轨 + 实验轨 3d/14d，非大网格）。

---

## 二、技术结论（云端与本地共同确认）

| 问题 | 结论 |
|------|------|
| 实验轨 0 笔 + 已 export legacy | 根因一：`backtest.py` 曾固定 `_experiment_entry_filter_kronos_light`，与线上 legacy 语义不一致 → **P0** 改为 `_experiment_entry_filter`。 |
| P0 后 legacy 仍 0 笔 | 根因二：`km_bar` 缺 `bayes_posterior_winrate`（legacy 过滤读 post=0 恒不满足）→ **P0.5** 合并后与 `get_v313_decision_snapshot` 顺序一致；**`beta_posterior_mean_for_replay_bar`** 内存回放、K 线时间节流、**不写** `bayes_beta_state.json`。 |
| 主轨有单、实验轨无单 | 数据与主轨链路正常；问题在实验轨路径/字段，非 CCXT 全坏。 |

---

## 三、本地执行过的验证步骤（摘要）

- **A0** `scripts/verify_env.sh` → PASS  
- **A1** `scripts/sync_from_server.sh` → PASS  
- **A2/A3** `LONGXIA_*` 环境快照 + 对齐 `legacy` + Markov off  
- **A4/A4b** 标准 experiment 回测（500/2000）→ P0 前 0 笔；P0+P0.5 后可出单  
- **A6** main 对照 → 有成交  
- **A5** `min_alignment_bundle.txt` 打包  
- **P1** `kronos_light` 同参 → 0 笔入 bundle 作交叉对照  
- **交付跑**（合并后）：`deliver_*` 前缀回测 + 更新 bundle（见当时 `outputs/backtest_parallel/`）

---

## 四、Git 与远端（GitHub `shop1189/lianghuaxitong`）

| 提交 | 说明 |
|------|------|
| **e9dd09b** | P0 + P0.5：`backtest.py`、`live_trading.py`；云端凭 `git show --stat` + bundle **形式签收**。 |
| **8f18a5b** | 基线：`pip_freeze_lock.sh`、`smoke_dual_track_3d_14d.sh`、`phase1_handoff` 增补、`.gitignore` 放行 `outputs/env/requirements_lock_*.txt`、锁文件样例。 |
| **8026b3b** | 云端建议：`setup_new_machine.sh`、`sync_from_server.sh`、`verify_env.sh` 进树 + handoff 同步；云端 **签收**。 |

**SSH / 推送**：本机曾遇 `publickey`；生成 ED25519、GitHub 绑 key 后 **`git push origin main` 成功**。Gitee 与 GitHub 为不同用途，勿混。

---

## 五、关键路径与产物

- 交接 + 一键提示词：`docs/phase1_handoff_prompt_zh.md`  
- 本会话叙事：`docs/session_work_memory_zh.md`（本文件）  
- 对照 bundle（历史）：`outputs/backtest_parallel/min_alignment_bundle.txt`（**outputs/ 下大目录默认仍 ignore**，bundle 若需长期进仓需另改规则或迁路径）  
- 锁依赖：`bash scripts/pip_freeze_lock.sh` → `outputs/env/requirements_lock_<时间戳>.txt`  
- 双轨 3d/14d：`bash scripts/smoke_dual_track_3d_14d.sh [SYMBOL]` → 默认 `outputs/baseline_smoke/`

---

## 六、云端书面结论（摘要）

- 认可 P0 / P0.5 方向；bundle 结构签收；**不阻塞** push。  
- 本机无法 `fetch` GitHub 为云端侧 SSH，补树校验待运维。  
- 8026b3b 三脚本 + handoff 同源落盘 **签收通过**。

---

## 七、已知未提交项（刻意保留在工作区）

`PROJECT_MEMORY.md`、`bayes_beta_state.json`、`main.py`、`memos_v316_hook.json`、`hermes_outbox/*` 等仍有本地修改，**未**与工单提交混绑；后续清理或另提交时单独决策。

---

## 八、下一步（给操作者）

1. **跑双轨最小验收（第三步）**  
   `cd ~/projects/longxia_system && source .venv/bin/activate && bash scripts/smoke_dual_track_3d_14d.sh`  
   阅读 `outputs/baseline_smoke/*_summary.json`，把 **主/实验、3d/14d、total_trades、净回撤** 记到内部表或工单。

2. **需要时再锁依赖**  
   `bash scripts/pip_freeze_lock.sh`（环境变更后）。

3. **与云端同步代码**  
   对方以 **`git pull`** 对齐 `origin/main`（含 **8026b3b**）即可。

4. **更远期（另排期）**  
   主轨网格、上线阈值、FinRL 统一 requirements —— 不在本记忆文件闭环内。

---

*文件生成：本地段助手；内容覆盖本对话主线。若与仓库实际提交不一致，以 `git log` 为准。*
