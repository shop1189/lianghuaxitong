import os
from dotenv import load_dotenv
import redis
import json
from datetime import datetime

load_dotenv()
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=int(os.getenv("REDIS_DB", 0)),
    decode_responses=True
)

def add_memory(role: str, prompt: str, response: str):
    """每单自动复盘存Redis（30天过期）"""
    key = f"memos:{role}:{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    data = {"prompt": prompt, "response": response[:500], "time": datetime.now().isoformat()}
    r.setex(key, 86400*30, json.dumps(data))
    r.lpush(f"memos:{role}:history", key)
    print(f"🧠 MemOS 已存 {role} 复盘到 Redis ✅")

def get_memory(role: str, limit: int = 3):
    """读取历史复盘"""
    keys = r.lrange(f"memos:{role}:history", 0, limit-1)
    memories = [json.loads(r.get(k)) for k in keys if r.get(k)]
    return memories

def auto_review(role: str, prompt: str):
    """自动复盘历史"""
    history = get_memory(role)
    if history:
        return f"历史复盘({len(history)}条): 上次决策 → {history[0]['response'][:100]}..."
    return "🆕 无历史记忆，开始新复盘"
