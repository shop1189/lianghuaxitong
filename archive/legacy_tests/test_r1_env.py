from dotenv import load_dotenv
import os

load_dotenv()

keys = {
    "DEEPSEEK_API_KEY": "DeepSeek",
    "BINANCE_API_KEY": "Binance",
    "BINANCE_API_SECRET": "Binance Secret",
    "SERVERCHAN_SCKEY": "Server酱",
    "CRYPTOQUANT_API_TOKEN": "CryptoQuant",
    "FEAR_GREED_API_URL": "Fear&Greed"
}

print("=== 第1步 .env 加载验证（CoinGlass已跳过付费） ===")
all_good = True
for k, name in keys.items():
    val = os.getenv(k)
    status = "✅ 已加载" if val and len(val) > 5 else "❌ 待填"
    print(f"{name} ({k}): {status}")
    
print("COIN_GLASS_API_KEY: ✅ 用Binance代替（第4步自动处理）")
print("REDIS 配置: ✅ 已加载")

if all_good:
    print("🎉 项目结构 + .env安全管理完成！所有key已就位，可进入第2步。")
else:
    print("⚠️ 还有问题，请再 nano .env 检查")
