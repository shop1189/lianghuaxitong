from ai_decision import ai_analysis

if __name__ == "__main__":
    print("🚀 AI量化交易系统 启动成功")
    result = ai_analysis(timeframe="1m")

    print("\n📊 实时分析结果")
    print(f"价格：{result['price']} USDT")
    print(f"周期：{result['timeframe']}")
    print(f"趋势：{result['trend']}")
    print(f"支撑：{result['support']} | 压力：{result['resistance']}")
    print(f"量能：{result['volume']}")
    print(f"恐惧贪婪：{result['fear_greed']}")
    print(f"决策：{result['action']}")
    print(f"权重：{result['weights']}")
    print(f"止损：{result['stop_loss']}")
    print(f"止盈：{result['take_profit']}")
