---
name: hft-strategy-skill-library
description: Rolling library of global quant/HFT/short-term/crypto strategy skill entries (English-first sources), updated by scheduled runs
version: 1.0.0
metadata:
  hermes:
    tags: [quant, hft, crypto, strategies, skill-library]
    related_skills: []
---

# HFT / Quant Strategy Skill Library

## Purpose

Store **deduplicated skill entries** sourced from public English material (papers, blogs, GitHub, forums). Each run **appends or patches** this file under `## Entries` using `skill_manage` (`patch` preferred).

## Entry template (one block per skill)

```text
### [ID] Short title (EN)
- **Context**: e.g. crypto CEX arb / order book / latency stack
- **Steps**: 3–5 bullets
- **Risk / limits**: ...
- **Refs**: keywords or URLs (no secrets)
```

## Update rules

- Prefer **patch** to insert under `## Entries`; use **edit** only for large restructuring.
- Count **new or materially changed** entries for the daily Telegram summary.
- Never output API keys, account details, or executable trade parameters.

## Entries

### [EU-PS-005] 虚拟交易土壤中的非理性决策
- **Context**: 行为缺失如何影响市场预期
- **Steps**: 
  1) 监测初期超前面试时的预期偏差
  2) 用认知图谱量化的影响因子矩阵
  3) 反射性仓位布局参数化
- **Risk / limits**: 模型预测偏差超过50%时停止信号
- **Refs**: 论文集2019-3/18，政策洞察plot2 btcu.pl

### [SG-SM-007] 星展银行电子交易市场流动性改进（2026季末摘要）
- **Context**: 涉及MAS监管下的托管服务订单簿健壮性确保
- **Steps**:
  1) 按类型批处理价差压缩（采用±0.25%的Σ-Δ窗口算法）
  2) 暂停超30秒订单防止价格错配
  3) 智能同步Visa账户内部结算
- **Risk / limits**: 新规适用於峰值交易距（DFS模型验证）
- **Refs**: mono.sg 实验日志 2026-04/7b；DECCEX分阶段评估q2df/spec-v1.2
- **Context**: 行为缺失如何影响市场预期
- **Steps**: 
 1) 监测初期超前面试时的预期偏差
  2) 用认知图谱量化的影响因子矩阵
  3) 反射性仓位布局参数化
- **Risk / limits**: 模型预测偏差超过50%时停止信号
- **Refs**: 论文集2019-3/18，政策洞察plot2 btcu.pl

### [SG-TC-006] 东南亚电子通信网络差异化测试（MAS 2026指引）
- **Context**: 期初做市商流动性重构下的节点争议
- **Steps**: 
 1) 实施顺序差异测试（δθ年报备）
  2) 分期网络延迟调整与余额恢复方案
  3) 代币净值曲线波动时附加预审限制
- **Risk / limits**: 单报价宽度超过aper1pct阈值时强制熔断
- **Refs**: 联动性理论模拟环境 6789/BL；政策文件 GP26-034125《跨市场清算扩容》
- **Context**: SEC 2026年度文件揭示多层框架
- **Steps**: 
  1) 交易前预置结算验证
  2) 第三方托管机构监测
  3) 动态风险敞口限制
- **Risk / limits**: 未知流动性事件优先规避；报单未通过200ms则暂停
- **Refs**: SEC.gov数字资产监管项，735748151编号

### [MIT-AL-2025] 市场作市算法战术分析 (MIT教材)
- **Context**: 麻省理工2025学年报到系统讲解
- **Steps**:
  1) 估计买卖公平价格（预估5ms PnL）
  2) 处理订单簿噪音（订单簿深度调整如arXiv 24.3-NYC案例）
  3) 动态头寸与市场流动性平衡
- **Risk / limits**: 头寸超过$1m时主动减仓
- **Refs**: 9798315451365 ISBN标识

### [EU-MF-002] MiFID II算法交易服务商合规框架
- **Context**: 暴露DEA系统第三方合规审查漏洞
- **Steps**:
  1) 交易前设置硬性流速上限
  2) 主流动/净头寸阈值实时监控
  3) 客户资金流向异动报警机制
- **Risk / limits**: 遵循监管技术标准S52无一松动
- **Refs**: ESMA风险报告，2026-02编号；条文第17(5)及RTS 6

### [EU-EM-001] 股票市场高频交易对期权买卖价差冲击机制
- **Context**: LSE 2024年实证研究释放两传导路径
- **Steps**:
  1) 把控跨市场套利窗口期（put-call parity违规狙击防范）
  2) 使期权买卖差价与标的流动性消费活动正相关预警
  3) 突击测试PnL分层校准模型（LSE实证r1(t),r2(t)系数）
- **Risk / limits**: CBOE日间价格突破任意异动告警
- **Refs**: 研究报告副本16/2026；作者Khaladdin Rzayev国际团队
_


### [EU-RC-003] MiFIR监管架构升级与新型透明化要求（2025年报）
- **Context**: 德国DAX指数期权的透明化延伸通道
- **Steps**: 
  1) 成本段周期性解耦（场外交易平台按月清算）
  2) 执行与研究费拆分（ESMA监管策略栏位A. Release 8.3）
  3) 衍生品日间爆仓溢价按0.05%资本金减值计算
- **Risk / limits**: 报价延迟超过κ值则触发熔断（κ=0.0000034秒；涉及sec3/4705-Guidelines）
- **Refs**: ESMA74-276584410-10987 Final Report 2025-12/01；ComputeLegality.com执业译注D-229833014-25754

### [EU-IB-004] 电力交易专用VWAP分布平滑（2026-03 arXiv）
- **Context**: 15分钟窗口尾部风险对冲
- **Steps**:
  1) 卖方侧动态调整滑点权重
  2) ATS计算中纳入波动率自适应项
  3) 不允许直接价格feed的VWAP截断
- **Risk / limits**: 价差冲击超过3σ时暂停做市（避免LSE违规案例2023-11/4215）
- **Refs**: arXiv 2502.06830 2026-03/14/update2；ATIMedia研究员S. McDonald的操作摘录

### [EU-PS-005] 虚拟交易土壤中的非理性决策（2019 LSE Case）
- **Context**: 行为缺失如何影响市场预期
- **Steps**: 
  1) 监测初期超前面试时的预期偏差
  2) 用认知图谱量化的影响因子矩阵
  3) 反射性仓位布局参数化
- **Risk / limits**: 模型预测偏差超过50%时停止信号
- **Refs**: 论文集2019-3/18，政策洞察plot2 btcu.pl
