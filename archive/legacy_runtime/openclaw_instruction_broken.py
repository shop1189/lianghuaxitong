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

# 加载模板(你之前重建过的 template.html）
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
prompt = f"""
龙虾100x超短AI（1m/5m，止损0.3%，R:R6:1）。
data = get_all_data()
prompt = f"""
龙虾100x超短AI（1m/5m，止损0.3%，R:R6:1）。

    send_serverchan("🦞 龙虾聊天决策", decision)
    return {"status": "ok", "decision": decision}

if __name__ == "__main__":
    asyncio.create_task(instruction_loop())
    print("🚀 OpenClaw 满血版已启动！访问 http://0.0.0.0:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
