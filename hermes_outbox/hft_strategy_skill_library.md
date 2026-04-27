---
name: HFT / 短线策略情报库
description: 公开来源的短线交易、微结构、指标调参、投机/博彩数学、心理学与实证研究条目；由每日 cron append-only 维护
category: quant-research
triggers: ['HFT', 'STRATEGY INTEL', '技能库', '短线', '微结构']
---

# HFT / 短线策略情报库（公开情报）

本目录由定时任务写入：只追加到下方“## Entries”区块；不保存密钥、不给出可执行下单参数。每条目对应一个独立主题（技能包级摘要），需含可核查引用。

## Entries

### Crypto-HFT-25MM-01 | Crypto Market Making Dilemma (2025)
- Source: Albers, Cucuringu, Howison, Shestopaloff (2025), arXiv 2502.18625.
- Insight: 做市成交概率与成交后收益存在显著负相关，顺着盘口拥挤方向挂单更易成交但后续收益更差。
- Method/Rule: 将盘口不平衡作为逆向报价信号，优先控制 adverse selection 风险。

### GAMBLE-BANKR-26AL | Betting Bankruptcy Under Null Hypothesis (2026)
- Source: arXiv 2602.08888.
- Insight: 在零优势/零假设场景下，长期“下注式”增益策略几乎必然走向资金衰减。
- Method/Rule: 在无统计优势的区间收缩仓位，优先做存活约束（risk-of-ruin first）。

### BEHAV-PRED-18BA | Psychology-Based Asset Price Models (2018)
- Source: Barberis (2018), NBER w24723.
- Insight: 外推偏差、过度自信与前景理论共同影响价格与成交量动态。
- Method/Rule: 将行为偏差当作状态变量，用于解释短期偏离与过度交易风险。

### CRYPTO-BMM-25FL | Better Market Maker Algorithm (2025)
- Source: CY Yan (2025), arXiv 2502.20001.
- Insight: 通过幂律不变量 AMM 设计，可在流动性与无常损失之间取得更优折中。
- Method/Rule: 在高波动阶段优先采用对冲无常损失的曲线参数，而非固定乘积基线。

### CRYPTO-XPLAIN-2602 | Explainable Cryptocurrency Microstructure Patterns (2026)
- Source: Bieganowski, Slepaczuk (2026), arXiv 2602.00776.
- Insight: 跨资产订单簿特征重要性结构相对稳定，可解释模型能复用关键微结构信号。
- Method/Rule: 使用时序交叉验证与可解释特征归因（如 SHAP）做稳健性复核。

### AI-BEHAV-MKT-2604 | AI Trading Behavioral Dynamics (2026)
- Source: Ouyang, Sui (2026), arXiv 2604.18373.
- Insight: LLM 交易代理可呈现类人行为偏差并在群体层面放大泡沫-回撤动态。
- Method/Rule: 在代理策略评估中增加行为偏差监测与提示词干预敏感性测试。

### AI-COLLUS-NBER-2604 | AI-Powered Trading and Algorithmic Collusion (2026)
- Source: National Bureau of Economic Research Working Paper w34054.
- Insight: AI驱动交易算法可在无明确协议场景下出现自发性合谋风险，损害市场竞争与效率。
- Method/Rule: 在AI策略上线前增加合谋检测与超竞争收益异常监控。

### PSYCH-BTC-OVCONF-26BB | Bitcoin Overconfidence Bias and Market Anomalies (2026)
- Source: Belhadj Hana & Ben Hamad Salah, "Overconfidence bias: explaining Bitcoin's market anomalies" (2026), Springer SN Business & Economics 6(1):1-12.
- Insight: Bitcoin投资者在正向收益后显著提升交易活跃度，这种过度自信偏差正向推动条件波动性。
- Method/Rule: 将交易量作为过度自信代理变量，对顺势策略增加行为偏差风险预算约束。

### SENTIMENT-MICRO-2602 | Sentiment Extremity Premium in Cryptocurrency Markets (2026)
- Source: Farzulla (2026), "The Extremity Premium: Sentiment Regimes and Adverse Selection in Cryptocurrency Markets", arXiv:2602.07018
- Insight: 极端恐惧与贪婪情绪状态下的买卖价差显著高于中性区间（"极值溢价"），市场做市商主要响应不确定性而非情绪方向。
- Method/Rule: 在情绪极值阶段优先管理不确定性驱动的流动性收缩风险，而非过度关注情绪方向性信号。

（Cron 仅允许通过 skill_manage 或受控 patch 在本锚点下追加；禁止覆盖式写入整个文件。）
