import os
from dotenv import load_dotenv
import requests
import json
from memos import add_memory, auto_review
from data_feed import get_all_data
load_dotenv()
KEY = os.getenv("DEEPSEEK_API_KEY")
def call(prompt):
    review = auto_review("expert", prompt)
    real_data = get_all_data()
    full_prompt = f"{review}\n实时六大数据: {json.dumps(real_data, ensure_ascii=False)}\n当前任务: {prompt}"
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    data = {"model": "deepseek-chat", "messages": [{"role": "system", "content": "你是龙虾系统【专家角色】，专注市场趋势、Fear&Greed、CryptoQuant分析。"}, {"role": "user", "content": full_prompt}]}
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=90)
            resp.raise_for_status()
            result = resp.json()['choices'][0]['message']['content']
            add_memory("expert", prompt, result)
            return result
        except Exception as e:
            print(f"❌ Expert 第{attempt+1}次超时，重试...")
            if attempt == 2: return f"错误: {str(e)[:100]}"
print("✅ expert.py 已由AI程序员自动重建")
