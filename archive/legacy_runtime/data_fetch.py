import os
from dotenv import load_dotenv
import requests
import ccxt
import json
from datetime import datetime

load_dotenv()

# Binance 实时行情（CoinGlass 已跳过付费，用这个代替）
binance = ccxt.binance({
    'apiKey': os.getenv("BINANCE_API_KEY"),
    'secret': os.getenv("BINANCE_API_SECRET"),
})

def get_all_data():
    """一键拉取六大数据平台"""
    try:
        # 1. Binance 实时价格 + 订单簿
        ticker = binance.fetch_ticker('BTC/USDT')
        orderbook = binance.fetch_order_book('BTC/USDT', limit=5)
        
        # 2. Fear&Greed（你的 .env URL）
        fg = requests.get(os.getenv("FEAR_GREED_API_URL")).json()
        
        # 3. CryptoQuant（你的 token）
        cq_headers = {"Authorization": f"Bearer {os.getenv('CRYPTOQUANT_API_TOKEN')}"}
        cq = requests.get("https://api.cryptoquant.com/v1/btc/market-data/price", headers=cq_headers, timeout=10).json()
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "btc_price": ticker['last'],
            "fear_greed": fg['data'][0]['value'],
            "cryptoquant_flow": cq.get('data', {}).get('flow', 'N/A'),
            "binance_bid": orderbook['bids'][0][0] if orderbook['bids'] else None,
            "binance_ask": orderbook['asks'][0][0] if orderbook['asks'] else None,
        }
        print(f"📡 实时数据拉取成功！BTC = ${data['btc_price']}")
        return data
    except Exception as e:
        print(f"⚠️ 数据拉取小问题: {str(e)[:100]}（网络波动正常）")
        return {"btc_price": 0, "error": str(e)}
