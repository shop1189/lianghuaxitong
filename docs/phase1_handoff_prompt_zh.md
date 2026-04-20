# 第一阶段（实验轨回测与线上一致性）— 交接提示词

> 用途：新对话 / 新窗口 / 丢上下文时，把本文件全文或「## 给 AI 的一键提示词」一节粘贴给助手，避免口径断裂。  
> 维护：本地段；与云端工单范围一致部分已签收。

---

## 给 AI 的一键提示词（复制以下整段到新对话）

```
你是本地段助手，接续 longxia_system 工单上下文。

【第一阶段定义与状态】
「第一阶段」= 实验轨同源回测与线上一致性（环境变量 + 入场过滤 + legacy 所需快照字段），不含主轨网格验收、上线阈值、FinRL 统一 requirements（另立项）。

【已完成】
1. 云端口径：实验轨以 live_trading.py 头部环境变量速查为 SSOT；线上 .env 显式 LONGXIA_EXPERIMENT_MODE=legacy；Markov 默认 off；两轨语义见 docs/trade_memory_two_tracks.md。
2. P0：backtest.py 实验轨改为调用 live_trading._experiment_entry_filter（按 LONGXIA_EXPERIMENT_MODE 分支 legacy / kronos_light）；summary.json 增加 experiment_mode。
3. P0.5：在 experiment_km_for_bar 结果合并后、过滤前补齐 bayes_posterior_winrate；新增 live_trading.beta_posterior_mean_for_replay_bar（与 beta_update_from_score_throttled 同 44s/0.35 律，K 线时间节流，仅内存 dict，不读不写 bayes_beta_state.json）。
4. 验证：legacy + Markov off 下实验轨回测可出单（非「缺 bayes 恒 0」假阳性）；P1 kronos_light 同参对照已写入 bundle。
5. 交付：outputs/backtest_parallel/min_alignment_bundle.txt（A4/A4b/A6/P1、legacy 与 kronos_light 的 LONGXIA_* ENV、experiment_mode + bayes 策略一行说明、四份 summary.json 全文）。
6. Git：已 push GitHub origin/main，合并提交 e9dd09ba04c326c80d6824c58b5a532f9863b58e（仅 backtest.py、live_trading.py）。云端已凭 git show --stat 与 bundle 做形式点验签收；其本机若无法 fetch GitHub 为对方 SSH 问题，不阻塞我方交付。

【标准对照命令模板】
legacy 实验轨（与线上一致时常用）：
  cd ~/projects/longxia_system && source .venv/bin/activate
  export LONGXIA_EXPERIMENT_MODE=legacy LONGXIA_MARKOV_TEMPLATE=off LONGXIA_USE_MARKOV_THRESHOLD_TEMPLATE=0
  python backtest.py --symbol SOL/USDT --timeframe 1m --limit 500 --level-mode experiment --entry-cooldown 3 --max-hold-bars 120 --out-dir outputs/backtest_parallel --out-prefix <前缀>

【勿混淆】
- 云实盘不动；本地 verify_env.sh + rsync + 同源 backtest.py。
- 工作区可能仍有未提交文件（main.py、bayes_beta_state.json 等），未纳入 e9dd09b，勿与工单提交混为一谈。

【可选后续】
云端在可达 GitHub 的环境补 git fetch 与树校验；主轨网格、上线阈值、FinRL 统一 requirements 另排期。
```

---

## 关键事实速查

| 项 | 值 |
|----|-----|
| 合并提交（GitHub main） | `e9dd09ba04c326c80d6824c58b5a532f9863b58e` |
| 变更文件 | `backtest.py`, `live_trading.py` |
| 远端 origin | `git@github.com:shop1189/lianghuaxitong.git` |
| Bundle 相对路径 | `outputs/backtest_parallel/min_alignment_bundle.txt` |
| legacy 对齐 export（最低集） | `LONGXIA_EXPERIMENT_MODE=legacy` + `LONGXIA_MARKOV_TEMPLATE=off` + `LONGXIA_USE_MARKOV_THRESHOLD_TEMPLATE=0` |

---

## 关于「助手记忆」

跨聊天窗口的持久记忆依赖你方保存的本文件或工单；助手无法保证永久记住未写入仓库/工单的内容。

---

## 第二阶段入口（冻结基线 + 双轨小窗）

- **新机/同步/校验（与工单同源，已进树）**：`scripts/setup_new_machine.sh`、`scripts/sync_from_server.sh`、`scripts/verify_env.sh`
- **锁依赖**：`bash scripts/pip_freeze_lock.sh` → 写入 `outputs/env/requirements_lock_<时间戳>.txt`
- **双轨 3d/14d 最小验收（非大网格）**：`bash scripts/smoke_dual_track_3d_14d.sh` 或 `bash scripts/smoke_dual_track_3d_14d.sh BTC/USDT`  
  - 1m：`limit = 天 * 1440`；主轨 `cd2 mh40`，实验轨 `cd3 mh120` + 默认 legacy/Markov off export（可用环境变量覆盖）
- 产出目录默认：`outputs/baseline_smoke/`（可用 `BASELINE_OUT_DIR=...` 覆盖）
