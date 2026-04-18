# Agent 协作短约束（longxia_system）

面向 **Cursor / 自动化代理**；人类读者请优先 [`README.md`](README.md)。

## 必读顺序

1. [`.cursor/WORKSPACE_IDENTITY.txt`](.cursor/WORKSPACE_IDENTITY.txt)  
2. [`.cursor/rules/`](.cursor/rules/)（含 `chat-requirements-sync.mdc`：对照需求时「已有则跳过、无则加」）  
3. [`docs/UPGRADE_PLAN.md`](docs/UPGRADE_PLAN.md) 当前阶段边界  

## 硬约束

- **交易记忆 / 实盘状态**：勿在未获真人确认时批量删除或覆盖 `trade_memory.json`、随意清空 `live_trading_state.json`；破坏性写盘须与用户约定一致。  
- **首页 / 决策页**：默认 **只加不减** 大块；改策略须可回滚（Git 标签）。  
- **实验轨 / 主观察池**：逻辑优先**叠加**，少动无关文件；不擅自改风控阈值除非用户明确要求。  

## 索引

- Agent 文档目录：[`docs/agent/README.md`](docs/agent/README.md)  
