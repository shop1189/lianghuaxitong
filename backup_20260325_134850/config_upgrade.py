# ==============================
# 量化升级系统 最终配置（已填好密钥）
# ==============================

API = {
    "binance_klines": "https://api.binance.com/api/v3/klines",
    "binance_price": "https://api.binance.com/api/v3/ticker/price",
    "fear_greed": "https://api.alternative.me/fng/?limit=1",
    "binance_funding": "https://fapi.binance.com/fapi/v1/fundingRate",
    "binance_taker": "https://fapi.binance.com/fapi/v1/takerlongshortRatio",
    "binance_oi": "https://fapi.binance.com/fapi/v1/openInterest",
    "binance_ls_ratio": "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
}

TIMEFRAMES = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
}

INDICATORS = {
    "ema_fast": 7,
    "ema_slow": 25,
    "rsi": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "bollinger_period": 20,
    "bollinger_dev": 2,
}

CACHE = {
    "price_ttl": 6,
    "kline_ttl": 60,
    "fear_greed_ttl": 3600,
    "funding_ttl": 60,    # 1分钟缓存
    "taker_ttl": 60,
    "oi_ttl": 60,
    "ls_ttl": 60,
}

DEEPSEEK = {
    "api_key": "sk-ba116a2e478645d39fb6134bf8ffd694",
    "model": "deepseek-chat",
    "url": "https://api.deepseek.com/v1/chat/completions"
}
