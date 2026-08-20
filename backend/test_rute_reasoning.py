"""
Simple Test Script for RUTE's Reasoning Engine
Run this to see RUTE's thought process in action!
"""

import requests
import json

BASE_URL = "http://localhost:8000"

print("\n" + "="*70)
print("RUTE REASONING ENGINE - DEMO")
print("="*70)
print("\nGenerating ML recommendations...")
print("(RUTE will log its complete thought process)")

# Generate recommendations for 3 stocks
request_data = {
    "symbols": [
        {"symbol": "AAPL", "assetType": "stock"},
        {"symbol": "TSLA", "assetType": "stock"},
        {"symbol": "GOOGL", "assetType": "stock"}
    ],
    "riskSettings": {
        "maxPositionSize": 1000,
        "maxDailyLoss": 500,
        "stopLossPercentage": 2,
        "takeProfitPercentage": 6,
        "enableAutoTrade": False
    }
}

try:
    response = requests.post(f"{BASE_URL}/api/recommendations", json=request_data)
    result = response.json()

    print(f"\n[SUCCESS] Generated {len(result.get('recommendations', []))} recommendations\n")

    if result.get('recommendations'):
        for rec in result['recommendations']:
            print(f"  {rec['symbol']}: {rec['type']}")
            print(f"    Entry Price: ${rec['entryPrice']:.2f}")
            print(f"    Confidence: {rec['confidence']}%")
            print(f"    Stop Loss: ${rec['stopLoss']:.2f}")
            print(f"    Take Profit: ${rec['takeProfit']:.2f}")
            reasoning = rec.get('reasoning', {})
            summary = reasoning.get('summary', 'N/A')
            print(f"    Reasoning: {summary[:80]}...")
            print()
    else:
        print("  Note: No recommendations generated (may need market data)")

    # Now test the thought logging endpoints
    print("\n" + "="*70)
    print("TESTING THOUGHT LOGGING ENDPOINTS")
    print("="*70)

    # Use a sample symbol
    symbol = result['recommendations'][0]['symbol'] if result.get('recommendations') else "AAPL"

    print(f"\n1. Getting thoughts for {symbol}...")
    thoughts_response = requests.get(f"{BASE_URL}/api/thoughts/{symbol}")
    thoughts = thoughts_response.json()

    if "error" in thoughts:
        print(f"   Note: {thoughts['error']}")
        print("   Thought logging works when auto-trading is enabled")
    else:
        print(f"   Analysis thoughts: {len(thoughts.get('analysis', []))}")
        print(f"   Decision thoughts: {len(thoughts.get('decisions', []))}")
        print(f"   Execution thoughts: {len(thoughts.get('executions', []))}")
        print(f"   Outcome thoughts: {len(thoughts.get('outcomes', []))}")

    print(f"\n2. Getting learning summary...")
    learning_response = requests.get(f"{BASE_URL}/api/learning/summary?days=7")
    learning = learning_response.json()

    if "error" in learning:
        print(f"   Note: {learning['error']}")
        print("   Learning summary works when auto-trading is enabled")
    else:
        metrics = learning.get('performance_metrics', {})
        print(f"   Total trades: {metrics.get('total_trades', 0)}")
        print(f"   Win rate: {metrics.get('win_rate', 0):.1f}%")

    print(f"\n3. Getting learning insights...")
    insights_response = requests.get(f"{BASE_URL}/api/learning/insights")
    insights = insights_response.json()

    if "error" in insights:
        print(f"   Note: {insights['error']}")
    else:
        print(f"   Insights available: {len(insights)} data points")

    print("\n" + "="*70)
    print("REASONING ENGINE TEST COMPLETE")
    print("="*70)
    print("\nKEY FEATURES:")
    print("  * Complete thought logging - every decision documented")
    print("  * Self-improvement - learns from wins and losses")
    print("  * Pattern recognition - identifies what works")
    print("  * API endpoints to access all reasoning")
    print("\nTo enable full thought logging:")
    print("  1. Set up auto-trading with broker credentials")
    print("  2. Enable auto-trading via /api/auto-trade/setup")
    print("  3. RUTE will trade AND log all thoughts automatically")
    print("\nSee REASONING_ENGINE_GUIDE.md for complete documentation")
    print()

except Exception as e:
    print(f"\n[ERROR] {e}")
    print("\nMake sure the backend server is running:")
    print("  cd backend")
    print("  python main.py")
