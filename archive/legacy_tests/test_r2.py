from manager import call as manager_call
from expert import call as expert_call
from engineer import call as engineer_call
from lobster import call as lobster_call
print("=== 第2步 4角色 + R1真实调用测试 ===")
print(manager_call("开始测试龙虾系统"))
print(expert_call("比特币现在趋势如何？"))
print(engineer_call("帮我写个简单Redis缓存函数"))
print(lobster_call("最终决策：现在买还是卖？"))
print("🎉 4角色全部调用DeepSeek R1成功！")
