import os
from dotenv import load_dotenv
import requests
from memos import add_memory, auto_review

load_dotenv(".env.dev")
KEY = "lobster-proxy-key"
# ====================== 【核心：你只需要改这里】 ======================
# 默认使用 V3（便宜、快、不超时）
# 想切 R1 只需要改成 "r1"
USE_MODEL = "v3"  # 可选：v3 / r1
# ======================================================================

def call(prompt):
    if not KEY:
        return "❌ 未配置 API Key"

    review = auto_review("lobster", prompt)
    full_prompt = review + "\n当前任务: " + prompt

    # 统一接口地址（全部模型都支持）
    url = "http://localhost:4000/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json"
    }

    # ---------------------- V3 模型配置（默认） ----------------------
    if USE_MODEL == "v3":
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是龙虾系统【Lobster核心角色】，负责最终执行交易、推送、决策。"},
                {"role": "user", "content": full_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 800
        }

    # ---------------------- R1 推理模型配置 ----------------------
    elif USE_MODEL == "r1":
        data = {
            "model": "deepseek-reasoner",
            "thinking": {
                "type": "adaptive",
                "enabled": True
            },
            "messages": [
                {"role": "system", "content": "你是龙虾系统【Lobster核心角色】，负责最终执行交易、推送、决策。"},
                {"role": "user", "content": full_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2000
        }

    # 开始请求
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=90)
            resp.raise_for_status()
            result = resp.json()['choices'][0]['message']['content']
            add_memory("lobster", prompt, result)
            return result

        except requests.exceptions.HTTPError as e:
            return f"❌ HTTP错误 {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            if attempt == 2:
                return f"❌ 调用失败：{str(e)[:100]}"
            continue
