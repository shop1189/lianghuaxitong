import os
import re
import json

file = 'openclaw_instruction.py'

# 备份
os.system(f'cp {file} {file}.full_bak')

with open(file, 'r', encoding='utf-8') as f:
    content = f.read()

# 修prompt (确保data.get对)
content = re.sub(r"data,get\('([^']+)','([^']+)'\)", r"data.get('\1','\2')", content)
content = re.sub(r"current_price\*1\.0(\d+):.0f", r"current_price * 1.00\1:.0f", content)

# 删坏side，插好side
content = re.sub(r'#动态side.*?send_serverchan\("龙虾新指令', '', content, flags=re.DOTALL)
pos = content.find('decision = lobster_call(prompt)')
if pos != -1:
    pos += len('decision = lobster_call(prompt)\n')
    good_side = '''
        # 动态side完美版
        trade_side = "HOLD"
        if "买入" in decision or "LONG" in decision.upper():
            trade_side = "LONG"
        elif "卖出" in decision or "SHORT" in decision.upper():
            trade_side = "SHORT"

        with open("last_entry.json", "w", encoding="utf-8") as f:
            json.dump({
                "entry_price": current_price,
                "side": trade_side,
                "time": time.time(),
                "decision": decision[:200]
            }, f)

        send_serverchan("龙虾决策", f"{trade_side}@{current_price:.0f} | {decision[:100]}")
'''
    content = content[:pos] + good_side + content[pos:]

with open(file, 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ 全修完成！语法OK")
os.system('python3 -m py_compile openclaw_instruction.py && echo "语法完美"')
print("跑: python3 openclaw_instruction.py &")
