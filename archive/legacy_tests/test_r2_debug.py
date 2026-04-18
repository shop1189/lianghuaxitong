from manager import call as manager_call
from expert import call as expert_call
from engineer import call as engineer_call
from lobster import call as lobster_call
import traceback

print("=== 第2步 调试版测试开始（每步都会打印）===")
try:
    print("1. Manager 调用中...")
    print("🧠 Manager:", manager_call("开始测试龙虾系统"))
except Exception as e:
    print("❌ Manager 报错:", str(e))
    traceback.print_exc()

try:
    print("2. Expert 调用中...")
    print("📊 Expert:", expert_call("比特币现在趋势如何？"))
except Exception as e:
    print("❌ Expert 报错:", str(e))
    traceback.print_exc()

try:
    print("3. Engineer 调用中...")
    print("🔧 Engineer:", engineer_call("帮我写个简单Redis缓存函数"))
except Exception as e:
    print("❌ Engineer 报错:", str(e))
    traceback.print_exc()

try:
    print("4. Lobster 调用中...")
    print("🦞 Lobster:", lobster_call("最终决策：现在买还是卖？"))
except Exception as e:
    print("❌ Lobster 报错:", str(e))
    traceback.print_exc()

print("🎉 测试结束！如果看到上面4个角色回复就成功了")
