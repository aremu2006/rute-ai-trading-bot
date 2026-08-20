import requests
import json

url = "http://localhost:8000/api/recommendations"

# Test with watchlist symbols
payload = {
    "symbols": [
        {"symbol": "AAPL", "assetType": "STOCK"},
        {"symbol": "TSLA", "assetType": "STOCK"},
        {"symbol": "GOOGL", "assetType": "STOCK"},
        {"symbol": "MSFT", "assetType": "STOCK"}
    ],
    "riskSettings": {
        "maxPositionSize": 10000,
        "maxDailyLoss": 500,
        "stopLossPercentage": 2.0,
        "takeProfitPercentage": 5.0,
        "enableAutoTrade": True
    }
}

print("Testing AI Recommendations with 80% minimum confidence...\n")
response = requests.post(url, json=payload)

if response.status_code == 200:
    data = response.json()
    recommendations = data.get("recommendations", [])

    print(f"Status: Success")
    print(f"Found: {len(recommendations)} high-confidence recommendations (>=80%)\n")

    if recommendations:
        for rec in recommendations:
            print(f"{'='*60}")
            print(f"Symbol: {rec['symbol']}")
            print(f"Action: {rec['type']}")
            print(f"Confidence: {rec['confidence']}%")
            print(f"Entry Price: ${rec['entryPrice']}")
            print(f"Stop Loss: ${rec['stopLoss']}")
            print(f"Take Profit: ${rec['takeProfit']}")
            print(f"\nReasoning:")
            print(f"  Trend: {rec['reasoning']['marketTrend']}")
            print(f"  Sentiment: {rec['reasoning']['sentiment']}")
            print(f"  Indicators:")
            for indicator in rec['reasoning']['technicalIndicators']:
                print(f"    - {indicator}")
            print(f"\nSummary: {rec['reasoning']['summary']}")
            print(f"{'='*60}\n")
    else:
        print("No recommendations meet the 80% confidence threshold.")
        print("This means current market conditions don't show strong enough signals.")
        print("\nNote: RUTE only recommends trades with:")
        print("  - RSI deeply oversold (<30) or overbought (>70): 30 points")
        print("  - Matching SMA trend (20 > 50 for BUY): 25 points")
        print("  - Price aligned with trend: 10 points")
        print("  - Bollinger Band confirmation: 15 points")
        print("  - High volume (>1.5x average): 10-15 points")
        print("  Total needed: 80+ points for recommendation")

    print(f"\nMarket Analysis:")
    print(f"  {data['marketAnalysis']['overall']}")
    print(f"  Sentiment: {data['marketAnalysis']['sentiment']}")
    print(f"  Volatility: {data['marketAnalysis']['volatility']}")
else:
    print(f"Error: {response.status_code}")
    print(response.text)
