import requests
import json

payload = {
    "symbols": [{"symbol": "AAPL", "assetType": "STOCK"}],
    "riskSettings": {
        "maxPositionSize": 1000,
        "maxDailyLoss": 500,
        "stopLossPercentage": 2,
        "takeProfitPercentage": 5,
        "enableAutoTrade": False,
        "minConfidence": 65
    },
    "notifications": {
        "tradeAlerts": True,
        "priceAlerts": True,
        "newsAlerts": False
    },
    "apiKeys": {}
}

try:
    res = requests.post("http://127.0.0.1:8001/api/recommendations", json=payload)
    print("Status:", res.status_code)
    print("Response:", res.json())
except Exception as e:
    print(e)
