import logging
from config.config import logger
from ai_decision_upgrade import ai_analysis_multi_timeframe

async def get_ai_decision_with_prefs(prefs):
    try:
        # 调用核心AI策略
        res = ai_analysis_multi_timeframe()

        # 基础数据
        decision = res["decision"]
        price = round(res["price"], 2)
        sl = res["stop_loss"]
        tp = res["take_profit"]
        max_loss = res["max_loss_pct"]

        # 新增概率与趋势
        long_prob = res["long_prob"]
        short_prob = res["short_prob"]
        big_trend = res["big_trend"]
        predict_timeframe = res["predict_timeframe"]
        patterns = res.get("patterns", [])
        pattern_text = " | ".join(patterns) if patterns else "趋势稳定"

        # 盈亏百分比
        sl_pct = round(abs(price - sl) / price * 100, 2) if sl != 0 else 0
        tp_pct = round(abs(tp - price) / price * 100, 1) if tp != 0 else 0

        # ======================
        # 最终输出界面（完整版）
        # ======================
        if "做多" in decision:
            text = f"""【决策建议】：做多 ✅
【预测周期】：{predict_timeframe}
【涨跌概率】：上涨 {long_prob}% ⚪ 下跌 {short_prob}%
【大周期趋势】：1H+4H {big_trend}
【入场依据】：多周期共振 + {pattern_text}
【风险提示】：100倍杠杆 · 严格止损{max_loss}%

【精确点位】
• 入场价：{price}
• 止损价：{sl}  (-{sl_pct}%)
• 止盈价：{tp}  (+{tp_pct}%)

【策略状态】：顺势持仓
"""

        elif "做空" in decision:
            text = f"""【决策建议】：做空 ✅
【预测周期】：{predict_timeframe}
【涨跌概率】：上涨 {long_prob}% ⚪ 下跌 {short_prob}%
【大周期趋势】：1H+4H {big_trend}
【入场依据】：多周期共振 + {pattern_text}
【风险提示】：100倍杠杆 · 严格止损{max_loss}%

【精确点位】
• 入场价：{price}
• 止损价：{sl}  (+{sl_pct}%)
• 止盈价：{tp}  (-{tp_pct}%)

【策略状态】：顺势持仓
"""

        else:
            text = f"""【决策建议】：观望 ⚪
【预测周期】：{predict_timeframe}
【涨跌概率】：上涨 {long_prob}% ⚪ 下跌 {short_prob}%
【大周期趋势】：1H+4H {big_trend}
【入场依据】：无共振信号 · 等待趋势
【策略状态】：空仓等待 · 不入场
"""

        return text

    except Exception as e:
        logger.error(f"AI决策输出错误: {str(e)}")
        return "📊 系统分析中，请稍候..."
