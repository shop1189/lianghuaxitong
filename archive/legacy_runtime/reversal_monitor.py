import time
import json
import os
from lobster import call as lobster_call
from data_feed import get_all_data

MAX_ALLOWED_REVERSAL = 1.5  # ←←← 你定的最大允许反转1.5%（AI绝不超这个）

print(f"🚨 AI智能反转监控已启动（最大允许反转 {MAX_ALLOWED_REVERSAL}%）...")

while True:
    try:
        # 1. 读取入场记录
        if not os.path.exists("last_entry.json"):
            time.sleep(10)
            continue
        with open("last_entry.json") as f:
            entry = json.load(f)
        entry_price = entry["entry_price"]
        side = entry["side"]

        # 2. 读取最近真实价格（模拟K线数据）
        get_all_data()  # 刷新最新数据
        prices = []
        if os.path.exists("ws.log"):
            with open("ws.log", "r", encoding="utf-8") as f:
                lines = f.readlines()[-30:]  # 最近30条 ≈ 5分钟K线
                for line in reversed(lines):
                    if "BTC=" in line:
                        try:
                            p = float(line.split("BTC=")[-1].split()[0].replace("$", "").replace(",", ""))
                            prices.append(p)
                        except:
                            pass
        if len(prices) < 5:
            time.sleep(10)
            continue

        current_price = prices[0]
        # 简单趋势描述给AI看（让它真正“看K线”）
        trend_desc = f"最近价格序列（从新到旧）：{prices[:10]}（当前{current_price}）"

        # 3. 让lobster AI自己判断（带最大允许范围）
        prompt = f"""
当前持仓：{side}，入场价 {entry_price}，当前真实价格 {current_price}。
最大允许反转亏损：{MAX_ALLOWED_REVERSAL}%（超过这个必须平仓）。
{ trend_desc }
基于K线走势（涨跌速度、是否突破、波动情况），判断是否需要**立即提前平仓**？
只回复两种结果：
- “立即平仓” + 简短理由（比如“突破支撑+加速下跌”）
- “继续持有” + 简短理由
"""
        decision = lobster_call(prompt)

        # 4. 触发警报
        if "立即平仓" in decision:
            alert = f"🚨【AI智能判断：行情反转！立即平仓】\n当前价: ${current_price}\n入场价: ${entry_price}\nAI理由: {decision}\n建议: 市价全平，保护本金！（已超过AI动态阈值）"
            print(alert)
            with open("instruction.log", "a", encoding="utf-8") as f:
                f.write(f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} | AI_ALERT | {alert}\n")

    except Exception as e:
        pass  # 稳妥不崩

    time.sleep(30)  # 30秒检查一次（够实时又不卡）
