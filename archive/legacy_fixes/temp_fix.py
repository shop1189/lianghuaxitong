
file = 'openclaw_instruction.py'

# 备份
os.system(f'cp {file} {file}.bak3')

# 删旧坏prompt
os.system(f"sed -i '/prompt = f/d' {file}")
os.system(f"sed -i '/龙虾.*超短AI/d' {file}")
os.system(f"sed -i '/decision = lobster_call(prompt)/d' {file}")

# 新完美prompt + side（半角、全英文变量）
lines = [
    "        data = get_all_data()",
    "",
    "        prompt = f\"\"\"",
    "Lobster 100x Ultra-Short AI (1m/5m, SL 0.3%, RR 6:1).",
    "",
    "Data:",
    "Price: {current_price}",
    "Kline: {data.get('klines_summary', '')}",
    "RSI: {data.get('rsi', '50')} | MACD: {data.get('macd', '')} | Vol: {data.get('volume', '')}",
    "L/S Ratio: {data.get('long_short_ratio', '1.0')} | Taker Buy: {data.get('taker_buy', '50%')}",
    "OI: {data.get('oi_change', 'flat')} | Funding: {data.get('funding_rate', '0')}",
    "Sentiment: {data.get('social', '0.5')} | Winrate: {data.get('evolution', '75%')}",
    "",
    "Rules (4/6 match):",
    "LONG: RSI<32 + MACD Gold + Vol>1.2x + L/S>1.25 + TakerBuy>72% + Sent>0.65",
    "SHORT: RSI>68 + MACD Death + Vol<0.8x + L/S<0.75 + TakerSell>72% + Sent<0.35",
    "HOLD: Else",
    "",
    "[Final Decision: LONG/SHORT/HOLD]",
    "Reason: (data + rules)",
    "Entry: {current_price:.0f}",
    "SL: {current_price * 0.997:.0f} (0.3%)",
    "TP1 50%: {current_price * 1.006:.0f} | TP2 30%: {current_price * 1.012:.0f} | TP3 20%: {current_price * 1.020:.0f}",
    "\"\"\"",
    "",
    "        decision = lobster_call(prompt)",
    "",
    "        trade_side = \"HOLD\"",
    "        if \"LONG\" in decision.upper() or \"买入\" in decision:",
    "            trade_side = \"LONG\"",
    "        elif \"SHORT\" in decision.upper() or \"卖出\" in decision:",
    "            trade_side = \"SHORT\"",
    "",
    "        with open(\"last_entry.json\", \"w\", encoding=\"utf-8\") as f:",
    "            json.dump({\"entry_price\": current_price, \"side\": trade_side, \"time\": time.time(), \"decision\": decision[:200]}, f)",
    "",
    "        send_serverchan(\"龙虾决策\", f\"{trade_side}@{current_price:.0f} | {decision[:100]}\")"
]

with open(file, 'r') as f:
    content = f.read()

pos = content.find('get_all_data()') + len('get_all_data()')
content = content[:pos] + '\n' + '\n'.join(lines) + '\n' + content[pos:]

with open(file, 'w') as f:
    f.write(content)

print("✅ prompt升级完成！备份.bak3")
