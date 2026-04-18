# 直接对接我们的策略系统
from ai_decision_upgrade import ai_analysis_multi_timeframe, format_decision_output

# 兼容页面传入的多个参数（*args 接收任意位置参数）
async def get_ai_decision_with_prefs(*args):
    res = ai_analysis_multi_timeframe()
    return format_decision_output(res)
