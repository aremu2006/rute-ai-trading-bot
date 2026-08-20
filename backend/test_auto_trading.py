"""
Test Auto-Trading System
Quick start example for setting up autonomous trading
"""

import requests
import json

# Backend URL
BASE_URL = "http://localhost:8000"

def setup_auto_trading():
    """
    Setup auto-trading with Alpaca (paper trading)

    TO USE:
    1. Sign up at https://alpaca.markets
    2. Get your Paper Trading API keys
    3. Replace YOUR_API_KEY and YOUR_API_SECRET below
    """

    config = {
        "enabled": True,
        "broker_config": {
            "broker_type": "alpaca",
            "api_key": "YOUR_API_KEY",  # Replace with your Alpaca API key
            "api_secret": "YOUR_API_SECRET",  # Replace with your secret
            "paper_trading": True  # Set to False for real trading
        },
        "max_position_size": 1000,  # Max $1000 per trade
        "max_daily_loss": 500,      # Stop trading after $500 loss
        "min_confidence": 60        # Only trade when ML confidence ≥ 60%
    }

    print("🤖 Setting up auto-trading...")
    response = requests.post(
        f"{BASE_URL}/api/auto-trade/setup",
        json=config
    )

    result = response.json()
    print(json.dumps(result, indent=2))

    if result.get("success"):
        print("\n✅ Auto-trading configured successfully!")
        print("RUTE will now trade automatically on your behalf.")
    else:
        print(f"\n❌ Setup failed: {result.get('error')}")

    return result


def check_status():
    """Check auto-trading status"""
    print("\n📊 Checking status...")
    response = requests.get(f"{BASE_URL}/api/auto-trade/status")
    status = response.json()
    print(json.dumps(status, indent=2))
    return status


def get_positions():
    """Get open positions"""
    print("\n💼 Getting open positions...")
    response = requests.get(f"{BASE_URL}/api/auto-trade/positions")
    positions = response.json()
    print(json.dumps(positions, indent=2))
    return positions


def generate_recommendations():
    """
    Generate ML recommendations
    If auto-trading is enabled, this will execute trades automatically!
    """
    print("\n🔍 Generating ML recommendations...")

    request_data = {
        "symbols": [
            {"symbol": "AAPL", "assetType": "stock"},
            {"symbol": "GOOGL", "assetType": "stock"},
            {"symbol": "MSFT", "assetType": "stock"}
        ],
        "riskSettings": {
            "maxPositionSize": 1000,
            "maxDailyLoss": 500,
            "stopLossPercentage": 2,
            "takeProfitPercentage": 6,
            "enableAutoTrade": True  # Enable auto-execution
        }
    }

    response = requests.post(
        f"{BASE_URL}/api/recommendations",
        json=request_data
    )

    result = response.json()

    # Show recommendations
    print(f"\nFound {len(result['recommendations'])} recommendations:")
    for rec in result['recommendations']:
        print(f"\n  {rec['symbol']}: {rec['type']}")
        print(f"    Entry: ${rec['entryPrice']}")
        print(f"    Stop Loss: ${rec['stopLoss']}")
        print(f"    Take Profit: ${rec['takeProfit']}")
        print(f"    Confidence: {rec['confidence']}%")

    # Show auto-executed trades
    if result.get("autoExecuted"):
        print(f"\n🤖 AUTO-EXECUTED {len(result['autoExecuted'])} TRADES:")
        for trade in result['autoExecuted']:
            print(f"  ✓ {trade['type']} {trade['symbol']} (Order: {trade['order_id']})")

    return result


def disable_auto_trading():
    """Disable auto-trading"""
    print("\n⏸️  Disabling auto-trading...")
    response = requests.post(f"{BASE_URL}/api/auto-trade/disable")
    result = response.json()
    print(json.dumps(result, indent=2))
    return result


def main():
    """
    Main demo flow
    """
    print("="*60)
    print("RUTE AUTO-TRADING DEMO")
    print("="*60)

    # Step 1: Setup
    print("\n1️⃣  Setting up auto-trading...")
    print("⚠️  Update YOUR_API_KEY and YOUR_API_SECRET in this script first!")
    # setup = setup_auto_trading()
    # if not setup.get("success"):
    #     print("Setup failed. Please check your API keys.")
    #     return

    # Step 2: Check status
    print("\n2️⃣  Checking status...")
    status = check_status()

    # Step 3: Generate recommendations (auto-executes if enabled)
    print("\n3️⃣  Generating recommendations...")
    print("⚠️  If auto-trading is enabled, this will execute real trades!")
    # Uncomment to actually generate and execute:
    # recommendations = generate_recommendations()

    # Step 4: Monitor positions
    print("\n4️⃣  Monitoring positions...")
    # positions = get_positions()

    # Step 5: Disable (optional)
    # print("\n5️⃣  Disabling auto-trading...")
    # disable_auto_trading()

    print("\n" + "="*60)
    print("DEMO COMPLETE")
    print("="*60)
    print("\nTo actually use auto-trading:")
    print("1. Get Alpaca API keys from https://alpaca.markets")
    print("2. Update config in setup_auto_trading()")
    print("3. Uncomment the function calls above")
    print("4. Run: python test_auto_trading.py")


if __name__ == "__main__":
    main()
