import time
import pandas as pd
import numpy as np
from data_upgrade import (
    get_price, get_klines, get_fear_greed,
    get_funding_rate, get_taker_ratio,
    get_open_interest, get_long_short_ratio
)
from indicator_upgrade import (
    support_resistance, volume_analysis, ema, rsi, macd, detect_kline_pattern
)

last_signal = {
    "direction": "观望",
    "timestamp": 0
}

# 调试 1m K线
def debug_1m_klines():
    klines = get_klines(timeframe="1m", limit=50)
    print(f"[DEBUG] 1m K线数量: {len(klines)}")
    return len(klines)

def ai_analysis_multi_timeframe():
    global last_signal
    now = time.time()

    price = get_price()
    fng = get_fear_greed()
    funding_rate = get_funding_rate()
    taker_buy, taker_sell = get_taker_ratio()
    open_interest = get_open_interest()
    long_ratio = get_long_short_ratio()

    tf_config = {
        "1m": 50,
        "5m": 50,
        "15m": 30,
        "1h": 50,
        "4h": 50
    }
    tf_data = {}

    for tf, limit in tf_config.items():
        try:
            klines = get_klines(timeframe=tf, limit=limit)
            close_list = []
            for k in klines:
                if isinstance(k, dict):
                    close_list.append(float(k['close']))
                else:
                    close_list.append(float(k[4]))
            close = pd.Series(close_list)
            support, resistance = support_resistance(klines)
            vol = volume_analysis(klines)

            ema13 = ema(close, 13).iloc[-1] if len(close) >= 13 else 0
            ema21 = ema(close, 21).iloc[-1] if len(close) >= 21 else 0

            if len(close) >= 14:
                r = rsi(close, 14).iloc[-1]
            elif len(close) >= 7:
                r = rsi(close, 7).iloc[-1]
            else:
                r = 50

            if ema13 > ema21 * 1.0003:
                trend = "上涨"
            elif ema13 < ema21 * 0.9997:
                trend = "下跌"
            else:
                trend = "震荡"

            tf_data[tf] = {
                "trend": trend,
                "support": support,
                "resistance": resistance,
                "volume": vol,
                "rsi": round(r, 1)
            }
        except Exception as e:
            tf_data[tf] = {
                "trend": "震荡",
                "rsi": 50
            }

    trend_1h = tf_data["1h"]["trend"]
    trend_4h = tf_data["4h"]["trend"]
    big_bull = (trend_1h == "上涨" or trend_4h == "上涨")
    big_bear = (trend_1h == "下跌" or trend_4h == "下跌")

    trend_5m = tf_data["5m"]["trend"]
    trend_15m = tf_data["15m"]["trend"]
    rsi_1m = tf_data["1m"]["rsi"]

    long_condition  = trend_5m == "上涨" and trend_15m != "下跌" and 30 < rsi_1m < 70
    short_condition = trend_5m == "下跌" and trend_15m != "上涨" and 30 < rsi_1m < 70

    score = 0
    if big_bull: score += 40
    if big_bear: score -= 40
    if trend_5m == "上涨": score += 30
    if trend_5m == "下跌": score -= 30
    if 30 < rsi_1m < 65: score += 15
    if 35 < rsi_1m < 70: score -= 15
    if taker_buy > 0.51: score += 10
    if taker_buy < 0.49: score -= 10

    kl5 = get_klines(timeframe="5m", limit=50)
    patterns = detect_kline_pattern(kl5)
    for p in patterns:
        if "看涨" in p or "底分型" in p or "启明星" in p: score +=5
        if "看跌" in p or "顶分型" in p or "流星线" in p: score -=5

    long_prob = max(0, min(100, 50 + score))
    short_prob = 100 - long_prob

    if big_bull:
        final_long = long_condition and long_prob >= 60
        final_short = False
    elif big_bear:
        final_short = short_condition and short_prob >= 60
        final_long = False
    else:
        final_long = False
        final_short = False

    current_dir = "观望"
    if final_long:
        current_dir = "做多"
    elif final_short:
        current_dir = "做空"

    if last_signal["direction"] != "观望" and now - last_signal["timestamp"] < 120:
        current_dir = last_signal["direction"]
    else:
        last_signal["direction"] = current_dir
        last_signal["timestamp"] = now

    if current_dir == "做多":
        decision = "🟢 做多 ✅"
        sl = round(price * 0.997, 2)
        tp1 = round(price * 1.005, 2)
        tp2 = round(price * 1.010, 2)
        tp3 = round(price * 1.015, 2)
    elif current_dir == "做空":
        decision = "🔴 做空 ✅"
        sl = round(price * 1.003, 2)
        tp1 = round(price * 0.995, 2)
        tp2 = round(price * 0.990, 2)
        tp3 = round(price * 0.985, 2)
    else:
        decision = "⚪ 观望 ⚪"
        sl = 0
        tp1 = tp2 = tp3 = 0

    return {
        "price": price,
        "fear_greed": fng,
        "funding_rate": round(funding_rate * 100, 4),
        "taker_buy": round(taker_buy, 2),
        "open_interest": round(open_interest, 2),
        "long_ratio": round(long_ratio, 2),
        "decision": decision,
        "stop_loss": sl,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "take_profit_3": tp3,
        "max_loss_pct": 0.3,
        "long_prob": round(long_prob),
        "short_prob": round(short_prob),
        "big_trend": "多头" if big_bull else "空头" if big_bear else "震荡",
        "predict_timeframe": "下一根 5 分钟 K线",
        "timeframe_summary": {
            "5m趋势": trend_5m,
            "15m过渡": trend_15m,
            "1mRSI": rsi_1m,
            "1H趋势": trend_1h,
            "4H趋势": trend_4h
        },
        "patterns": patterns
    }

def format_decision_output(res):
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    price = round(res["price"], 2)
    decision = res["decision"]
    sl = res["stop_loss"]
    tp1 = res["take_profit_1"]
    tp2 = res["take_profit_2"]
    tp3 = res["take_profit_3"]
    long_prob = res["long_prob"]
    short_prob = res["short_prob"]
    big_trend = res["big_trend"]
    patterns = res.get("patterns", [])
    pattern_text = " | ".join(patterns) if patterns else "无特殊形态"

    trend_text = "1H+4H 多头趋势" if big_trend == "多头" else \
                 "1H+4H 空头趋势" if big_trend == "空头" else "1H+4H 震荡趋势"
    status_text = "顺势持仓" if "做多" in decision else "空仓观望"

    tf_summary = res.get("timeframe_summary", {})
    t_5m = tf_summary.get("5m趋势", "未知")
    t_15m = tf_summary.get("15m过渡", "未知")
    t_1h = tf_summary.get("1H趋势", "未知")
    t_4h = tf_summary.get("4H趋势", "未知")
    rsi_1m = tf_summary.get("1mRSI", 50)

    decision_reason = (
        f"周期判断：5m={t_5m} | 15m={t_15m} | 1H={t_1h} | 4H={t_4h}\n"
        f"技术指标：RSI(1m)={rsi_1m} | K线形态={pattern_text}\n"
        f"概率模型：上涨{long_prob}% | 下跌{short_prob}%\n"
        f"趋势状态：{trend_text} | 资金健康"
    )

    if "做多" in decision:
        risk_detail = f"100倍杠杆 | 止损={sl} | 最大亏损0.3% | 严禁扛单"
    elif "做空" in decision:
        risk_detail = f"100倍杠杆 | 止损={sl} | 最大亏损0.3% | 严禁扛单"
    else:
        risk_detail = "无共振信号 → 空仓观望"

    if "做多" in decision:
        return f"""【当前时间】{current_time}
【当前价格】{price} USDT
【决策建议】{decision}
【预测周期】下一根 5 分钟 K线
【涨跌概率】上涨：{long_prob}% ⚪ 下跌：{short_prob}%
【大周期趋势】{trend_text}
【决策理由】
{decision_reason}
【风险提示】
{risk_detail}
【交易点位】
• 入场价：{price}
• 止损价：{sl}
• 止盈1：{tp1}
• 止盈2：{tp2}
• 止盈3：{tp3}
【状态提示】{status_text}
"""
    elif "做空" in decision:
        return f"""【当前时间】{current_time}
【当前价格】{price} USDT
【决策建议】{decision}
【预测周期】下一根 5 分钟 K线
【涨跌概率】上涨：{long_prob}% ⚪ 下跌：{short_prob}%
【大周期趋势】{trend_text}
【决策理由】
{decision_reason}
【风险提示】
{risk_detail}
【交易点位】
• 入场价：{price}
• 止损价：{sl}
• 止盈1：{tp1}
• 止盈2：{tp2}
• 止盈3：{tp3}
【状态提示】{status_text}
"""
    else:
        return f"""【当前时间】{current_time}
【当前价格】{price} USDT
【决策建议】{decision}
【预测周期】下一根 5 分钟 K线
【涨跌概率】上涨：{long_prob}% ⚪ 下跌：{short_prob}%
【大周期趋势】{trend_text}
【决策理由】
{decision_reason}
【风险提示】
{risk_detail}
【状态提示】{status_text}
"""

if __name__ == "__main__":
    debug_1m_klines()
    result = ai_analysis_multi_timeframe()
    show_text = format_decision_output(result)
    print(show_text)
