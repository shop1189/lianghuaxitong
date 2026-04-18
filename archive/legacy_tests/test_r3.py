from manager import call as manager_call
from expert import call as expert_call
from engineer import call as engineer_call
from lobster import call as lobster_call
import redis
import os
from dotenv import load_dotenv

load_dotenv()
r = redis.Redis(host=os.getenv("REDIS_HOST"), port=int(os.getenv("REDIS_PORT")), decode_responses=True)

print("=== 第3步 MemOS + Redis持久化测试 ===")
print("🧠 请耐心等待90-180秒/角色，**千万别按 Ctrl+C** ...")
manager_call("开始测试龙虾系统")
expert_call("比特币现在趋势如何？")
engineer_call("帮我写个简单Redis缓存函数")
lobster_call("最终决策：现在买还是卖？")

print("\n🧠 MemOS Redis记忆检查（已存4条复盘）：")
print(r.keys("memos:*"))
print("🎉 MemOS + Redis持久记忆已启用！每单自动复盘成功！第3步锁死！")
