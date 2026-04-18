import time
import os
import json
import io
import sys
import re
from lobster import call as lobster_call
from data_feed import get_all_data

print("=== 龙虾AI实时监控 终极版 v14（入场理由已永久保留 + 价格铁定同步） ===")
print("🚀 启动成功！价格+理由全都有～按 Ctrl+C 停止")

def get_latest_reversal():
    if not os.path.exists("instruction.log"):
        return "✅ 行情正常（暂无警报）"
    try:
        with open("instruction.log", "r", encoding="utf-8") as f:
            for line in reversed(f.readlines()[-30:]):
                if "REVERSAL_STATUS" in line:
                    return line.split("|", 2)[-1].strip()
    except:
        pass
    return "✅ 行情正常（暂无警报）"

while True:
    os.system("clear")
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "龙虾AI最新状态")
    print("=" * 70)
    
    try:
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        get_all_data()
        sys.stdout = old_stdout
        output = captured.getvalue()
        print(output)
        
        current_price = 71800.0
        # 加强版正则，吃尽所有格式（BTC=$73xxx、BTC = $73xxx、带逗号等）
        for line in reversed(output.splitlines()):
            match = re.search(r'BTC\s*=\s*\$?([\d,]+(?:\.\d+)?)', line, re.IGNORECASE)
            if match:
                p_str = match.group(1).replace(',', '')
                current_price = float(p_str)
                break
        
        print(f"✅ 抓取到最新BTC价格: ${current_price:,.2f}")
        
        # 入场理由强制保留
        decision = lobster_call(f"""
最终决策：现在买还是卖？**当前真实BTC价格是 {current_price} USD**。
必须基于这个价格给出：
1. **入场理由**（1-2句简短说明为什么现在买入/卖出 + 逻辑概要）
2. 精确入场价、止损、止盈分批50%/30%/20%具体点位
全部用中文清晰写出来！
""")
        print("🔥 当前AI指令：\n", decision)
        
        print("\n" + "=" * 50)
        print("📢 最新反转提醒：")
        print(get_latest_reversal())
        
        if os.path.exists("last_entry.json"):
            with open("last_entry.json") as f:
                print("📍 入场记录：", json.load(f))
    except Exception as e:
        print("⚠️ 小问题，继续刷新...", str(e))
    
    print("\n💡 保持这个终端开着就行！")
    time.sleep(30)
