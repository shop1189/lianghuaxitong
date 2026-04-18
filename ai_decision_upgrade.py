from evolution_core import ai_evo
import time
import pandas as pd
import requests
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

# ====================== LiteLLM 本地AI配置 ======================
LITELLM_API_URL = "http://127.0.0.1:4000/v1/chat/completions"
LITELLM_API_KEY = "lobster-proxy-key"

def ai_make_decision(price, trend_5m, trend_15m, trend_1h, trend_4h,
    rsi_1m, patterns, long_prob, short_prob,
    macd_line, macd_signal, macd_hist,
    long_short_ratio, taker_buy_sell, open_interest,
    funding_rate, volume_confirm, greed_fear, support, resistance):

    try:
        prompt = f"""你是专业BTC合约超短线交易AI，100倍杠杆，严格风控。
根据全维度数据预测下一根5分钟K线，严格按格式输出，不要多余内容：

决策：做多/做空/观望
上涨概率：数字
下跌概率：数字
理由：一句话
入场价：数字（保留2位小数，必须根据支撑位、阻力位、K线形态动态判断）

当前价格：{price}
5m趋势：{trend_5m}
15m趋势：{trend_15m}
1H趋势：{trend_1h}
4H趋势：{trend_4h}
1mRSI：{rsi_1m}
K线形态：{patterns}
MACD快线：{macd_line}
MACD慢线：{macd_signal}
MACD柱：{macd_hist}
多空持仓比：{long_short_ratio}
主动买卖比：{taker_buy_sell}
持仓量OI：{open_interest}
资金费率：{funding_rate}
成交量确认：{volume_confirm}
恐惧贪婪指数：{greed_fear}
支撑位：{support}
阻力位：{resistance}
"""
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 120
        }
        headers = {
            "Authorization": f"Bearer {LITELLM_API_KEY}",
            "Content-Type": "application/json"
        }
        resp = requests.post(LITELLM_API_URL, json=payload, headers=headers, timeout=8)
        result = resp.json()["choices"][0]["message"]["content"].strip()

        decision = "观望"
        up = 50
        down = 50
        reason = "AI分析中"
        entry_price = round(price, 2)

        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("决策："):
                decision = line.replace("决策：", "").strip()
            elif line.startswith("上涨概率："):
                try:
                    up = int(line.replace("上涨概率：", "").strip())
                except:
                    up = 50
            elif line.startswith("下跌概率："):
                try:
                    down = int(line.replace("下跌概率：", "").strip())
                except:
                    down = 50
            elif line.startswith("理由："):
                reason = line.replace("理由：", "").strip()
            elif line.startswith("入场价："):
                try:
                    entry_price = round(float(line.replace("入场价：", "").strip()), 2)
                except:
                    entry_price = round(price, 2)

        total = up + down
        if total <= 0:
            up, down = 50, 50
        else:
            up = round(up / total * 100)
            down = 100 - up

        return decision, up, down, reason, entry_price

    except Exception as e:
        return "观望", 50, 50, "AI服务异常", round(price, 2)


def ai_think(price, trend_5m, trend_15m, trend_1h, trend_4h, rsi_1m, patterns):
    try:
        prompt = f"""
你是BTC合约AI交易助手，根据以下行情做思考：
当前价格：{price}
5m趋势：{trend_5m}
15m趋势：{trend_15m}
1H趋势：{trend_1h}
4H趋势：{trend_4h}
1mRSI：{rsi_1m}
K线形态：{patterns}
请用专业、简短的一句话给出思考结论，只输出思考，不要格式、不要符号。
"""
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 150
        }
        headers = {
            "Authorization": f"Bearer {LITELLM_API_KEY}",
            "Content-Type": "application/json"
        }
        resp = requests.post(LITELLM_API_URL, json=payload, headers=headers, timeout=8)
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return "AI思考暂时不可用"


def debug_1m_klines():
    klines = get_klines(timeframe="1m", limit=50)
    print(f"[DEBUG] 1m K线数量: {len(klines)}")
    return len(klines)


def ai_analysis_multi_timeframe():
    global last_signal
    now = time.time()
    price = get_price()

    # ====================== 全数据已采集 ======================
    greed_fear = get_fear_greed()
    funding_rate = get_funding_rate()
    taker_buy, taker_sell = get_taker_ratio()
    taker_buy_sell = round(taker_buy / (taker_sell + 1e-8), 2)
    open_interest = get_open_interest()
    long_short_ratio = get_long_short_ratio()

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
            tf_data[tf] = {"trend": "震荡", "rsi": 50, "support": price*0.995, "resistance": price*1.005}

    trend_5m = tf_data["5m"]["trend"]
    trend_15m = tf_data["15m"]["trend"]
    trend_1h = tf_data["1h"]["trend"]
    trend_4h = tf_data["4h"]["trend"]
    rsi_1m = tf_data["1m"]["rsi"]
    support_5m = tf_data["5m"]["support"]
    resistance_5m = tf_data["5m"]["resistance"]

    big_bull = (trend_1h == "上涨" or trend_4h == "上涨")
    big_bear = (trend_1h == "下跌" or trend_4h == "下跌")

    # ====================== 计算MACD ======================
    kl5 = get_klines(timeframe="5m", limit=100)
    close5 = [float(k[4]) if not isinstance(k, dict) else float(k['close']) for k in kl5]
    close5_series = pd.Series(close5)
    macd_line, macd_signal, macd_hist = macd(close5_series)
    macd_line = round(macd_line.iloc[-1], 2)
    macd_signal = round(macd_signal.iloc[-1], 2)
    macd_hist = round(macd_hist.iloc[-1], 2)

    # K线形态
    patterns = detect_kline_pattern(kl5)
    volume_confirm = tf_data["5m"]["volume"]

    # 旧概率（给AI参考）
    score = 0
    if big_bull: score += 40
    if big_bear: score -= 40
    if trend_5m == "上涨": score += 30
    if trend_5m == "下跌": score -= 30
    if 30 < rsi_1m < 65: score += 15
    if rsi_1m > 70: score -= 15
    if taker_buy > 0.51: score += 10
    if taker_buy < 0.49: score -= 10
    for p in patterns:
        if "看涨" in p or "底分型" in p or "启明星" in p: score +=5
        if "看跌" in p or "顶分型" in p or "流星线" in p: score -=5

    long_prob = max(0, min(100, 50 + score))
    short_prob = 100 - long_prob

    # ====================== 调用AI（动态入场价） ======================
    current_dir, long_prob, short_prob, ai_decision_reason, entry_price = ai_make_decision(
        price, trend_5m, trend_15m, trend_1h, trend_4h,
        rsi_1m, patterns, long_prob, short_prob,
        macd_line, macd_signal, macd_hist,
        long_short_ratio, taker_buy_sell, open_interest,
        funding_rate, volume_confirm, greed_fear, support_5m, resistance_5m
    )

    # 冷却60秒
    if last_signal["direction"] != "观望" and now - last_signal["timestamp"] < 60:
        current_dir = last_signal["direction"]
    else:
        last_signal["direction"] = current_dir
        last_signal["timestamp"] = now
    ai_evo.tick(price, None)
    # 输出不变
    if current_dir == "做多":
        decision = "🟢 做多 ✅"
        sl = round(entry_price * 0.997, 2)
        tp1 = round(entry_price * 1.005, 2)
        tp2 = round(entry_price * 1.010, 2)
        tp3 = round(entry_price * 1.015, 2)
    elif current_dir == "做空":
        decision = "🔴 做空 ✅"
        sl = round(entry_price * 1.003, 2)
        tp1 = round(entry_price * 0.995, 2)
        tp2 = round(entry_price * 0.990, 2)
        tp3 = round(entry_price * 0.985, 2)
    else:
        decision = "⚪ 观望 ⚪"
        sl = 0
        tp1 = tp2 = tp3 = 0
        entry_price = round(price, 2)
    ai_evo.record(current_dir, entry_price, sl, tp1, tp2, tp3)
    ai_thought = ai_think(price, trend_5m, trend_15m, trend_1h, trend_4h, rsi_1m, patterns)

    return {
        "price": price,
        "entry_price": entry_price,
        "fear_greed": greed_fear,
        "funding_rate": round(funding_rate * 100, 4),
        "taker_buy": round(taker_buy, 2),
        "open_interest": round(open_interest, 2),
        "long_ratio": round(long_short_ratio, 2),
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
        "patterns": patterns,
        "ai_thought": ai_thought
    }


def format_decision_output(res):
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    price = round(res["price"], 2)
    entry_price = round(res["entry_price"], 2)
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
    ai_thought = res.get("ai_thought", "AI思考中")
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
        f"趋势状态：{trend_text} | 资金健康\n"
        f"🧠 AI思考：{ai_thought}"
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
• 动态入场价：{entry_price}
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
• 动态入场价：{entry_price}
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
# ========== 这下面才是主程序，和函数平级 ==========
if __name__ == "__main__":
    debug_1m_klines()
    result = ai_analysis_multi_timeframe()
    show_text = format_decision_output(result)
    print(show_text)
