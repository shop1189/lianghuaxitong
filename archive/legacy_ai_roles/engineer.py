import os
from dotenv import load_dotenv
import requests
from memos import add_memory, auto_review
load_dotenv()
KEY = os.getenv("DEEPSEEK_API_KEY")
def call(prompt):
    review = auto_review("engineer", prompt)
    full_prompt = review + "\n当前任务: " + prompt
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    data = {"model": "deepseek-chat", "messages": [{"role": "system", "content": "你是龙虾系统【工程师角色】，负责写代码、实现功能、调试。"}, {"role": "user", "content": full_prompt}]}
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=90)
            resp.raise_for_status()
            result = resp.json()['choices'][0]['message']['content']
            add_memory("engineer", prompt, result)
            return result
        except Exception as e:
            print(f"❌ Engineer 第{attempt+1}次超时，重试...")
            if attempt == 2: return f"错误: {str(e)[:100]}"
