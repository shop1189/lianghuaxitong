import re
import os

file = 'openclaw_instruction.py'

os.system(f'cp {file} {file}.char_bak')

with open(file, 'r', encoding='utf-8') as f:
    content = f.read()

# 全角 → 半角 (括号/引号/百分号)
content = re.sub(r'[（(][^）)]*[）)]', lambda m: re.sub(r'[（(（]', '(', re.sub(r'[）)]）]', ')', m.group(0))), content)
content = content.replace('％', '%').replace('：', ':').replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
content = re.sub(r'current_price', 'current_price', content)
content = re.sub(r'trade_side', 'trade_side', content)

# 确side动态 (插决策后)
if 'decision = lobster_call(prompt)' in content:
    pos = content.find('decision = lobster_call(prompt)') + len('decision = lobster_call(prompt)\n')
    side_block = '''
        trade_side = "HOLD"
        if "买入" in decision or "LONG" in decision.upper():
            trade_side = "LONG"
        elif "卖出" in decision or "SHORT" in decision.upper():
            trade_side = "SHORT"

        with open("last_entry.json", "w", encoding="utf-8") as f:
            json.dump({"entry_price": current_price, "side": trade_side, "time": time.time(), "decision": decision[:200]}, f)

        send_serverchan("龙虾决策", f"{trade_side}@{current_price:.0f} | {decision[:100]}")
'''
    content = content[:pos] + side_block + content[pos:]

with open(file, 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ 全角修 + side完！")
os.system('python3 -m py_compile openclaw_instruction.py && echo "语法OK！跑系统"')
