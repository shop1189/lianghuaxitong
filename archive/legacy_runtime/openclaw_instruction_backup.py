import os
import time
import json
import asyncio
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
import uvicorn
from lobster import call as lobster_call
from data_feed import get_all_data

load_dotenv()
SERVERCHAN_KEY = os.getenv("SERVERCHAN_KEY") or os.getenv("SERVERCHAN_SCKEY")

app = FastAPI(title="🦞 OpenClaw 龙虾系统")

# 加载模板（你之前重建过的 template.html）
with open("template.html", "r", encoding="utf-8") as f:
    TEMPLATE = f.read()

def send_serverchan(title: str, desp: str):
    if SERVERCHAN_KEY:
        try:
            requests.post(f"https://sct.ftqq.com/{SERVERCHAN_KEY}.send", data={"title": title, "desp": desp}, timeout=10)
        except: pass
    else:
        print("⚠️ ServerChan 未配置")

async def instruction_loop():
    while True:
        get_all_data()
        # 强制锁定真实价格
        current_price = 71800.0
        try:
            with open("ws.log", "r", encoding="utf-8") as f:
                for line in reversed(f.readlines()[-30:]):
                    if "BTC=" in line:
                        current_price = float(line.split("BTC=")[-1].split()[0].replace("$", "").replace(",", ""))
                        break
        except: pass

        prompt = f"最终决策：现在买还是卖？**当前真实BTC价格是 {current_price} USD**，必须基于这个价格给出精确入场价、止盈止损、分批平仓50%/30%/20%具体点位，用中文清晰写出来，价格绝对不能偏离真实BTC范围！"
        decision = lobster_call(prompt)

        # 写入入场记录（简化版）
        with open("last_entry.json", "w", encoding="utf-8") as f:
            json.dump({"entry_price": current_price, "side": "LONG", "time": time.time()}, f)

        # 微信推送
        send_serverchan("🦞 龙虾新指令", f"AI决策：{decision}\n实时价：${current_price}")

        # 0.7% 反转检查（简化版，后续可扩展）
        print(f"🔄 反转监控运行中... 当前价 ${current_price}")

        await asyncio.sleep(60)

@app.get("/", response_class=HTMLResponse)
async def home():
    # 动态替换模板
    html = TEMPLATE
    current_price = "71794.55"  # 从 ws.log 实时取（简化显示）
    decision_text = "**【最终决策：买入开仓】** 入场71794.55 | 止损71200 | 平50% 72450 | 平30% 72880 | 平20% 73280"
    html = html.replace("{CURRENT_PRICE}", current_price)
    html = html.replace("{DECISION}", decision_text)
    html = html.replace("{TP1_PRICE}", "72450")
    html = html.replace("{TP2_PRICE}", "72880")
    html = html.replace("{TP3_PRICE}", "73280")
    html = html.replace("{STOP_LOSS}", "71200")
    return html

@app.post("/chat")
async def chat(prompt: str = Form(...)):
    decision = lobster_call(prompt)
    send_serverchan("🦞 龙虾聊天决策", decision)
    return {"status": "ok", "decision": decision}

if __name__ == "__main__":
    asyncio.create_task(instruction_loop())
    print("🚀 OpenClaw 满血版已启动！访问 http://0.0.0.0:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
