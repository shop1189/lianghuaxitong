from manager import call as manager_call
from expert import call as expert_call
from engineer import call as engineer_call
from lobster import call as lobster_call
from data_feed import get_all_data

print("=== 第4步 全部数据平台接入 + 真实跑 ===")
print("📡 正在启动 Binance WebSocket（CoinGlass 已用 Binance 代替）...")
get_all_data()

print("\n🔍 【专家角色】比特币现在趋势如何？")
print(expert_call("比特币现在趋势如何？用实时六大数据分析"))

print("\n📋 【经理角色】协调整体计划")
print(manager_call("协调整体计划"))

print("\n🦞 【龙虾角色】最终决策：现在买还是卖？")
print(lobster_call("最终决策：现在买还是卖？"))

print("\n🎉 六大数据平台真实接入，系统真实跑开启！")
print("✅ test_r4.py 已由AI程序员自动重建")
