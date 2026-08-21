"""
Comprehensive Verification Test for RUTE Decision Logs & Autonomous Scanner
Worker 1 Verification Suite
"""

import sys
import os
import asyncio
import time
from datetime import datetime
from typing import Dict

# Ensure backend path is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trading_engine.auto_trader import AutoTrader
from trading_engine.broker_interface import BrokerInterface, TradeOrder
import pytest
from fastapi.testclient import TestClient
from main import app, SCAN_LOG, _run_recommendation_scan, RecommendationRequest, Symbol, RiskSettings


class DummyBroker(BrokerInterface):
    """Mock broker for testing AutoTrader position sizing and execution"""
    def __init__(self, balance=10000.0):
        super().__init__({"paper_trading": True})
        self.balance = balance
        self.connected = True
        self.orders = []

    def connect(self) -> bool:
        self.connected = True
        return True

    def get_account_balance(self) -> Dict:
        return {"balance": self.balance, "equity": self.balance, "currency": "USD"}

    def execute_trade(self, order: TradeOrder) -> Dict:
        self.orders.append(order)
        return {"success": True, "order_id": f"mock-{len(self.orders)}"}

    def get_open_positions(self) -> list:
        return []

    def close_position(self, position_id: str) -> bool:
        return True


def test_auto_trader_calculate_position_size():
    """Test calculate_position_size for various asset types (Forex, Crypto, Stock)"""
    broker = DummyBroker(balance=10000.0)
    config = {
        "enabled": True,
        "max_position_size": 2000,
        "max_daily_loss": 500,
        "max_daily_profit": 1000,
        "min_confidence": 60
    }
    trader = AutoTrader(broker, config)

    # 1. Stock (e.g. AAPL)
    size_stock, risk_stock = trader.calculate_position_size(
        entry_price=150.0,
        stop_loss=147.0,
        symbol="AAPL",
        win_prob=0.60,
        r_r=3.0
    )
    assert size_stock > 0, f"Stock size should be positive, got {size_stock}"
    assert risk_stock > 0, f"Risk amount should be positive, got {risk_stock}"

    # 2. Forex (e.g. EURUSD - 6 char alpha) -> should normalize to lots (/ 100,000)
    size_fx, risk_fx = trader.calculate_position_size(
        entry_price=1.0850,
        stop_loss=1.0800,
        symbol="EURUSD",
        win_prob=0.60,
        r_r=3.0
    )
    assert size_fx > 0, f"Forex lot size should be positive, got {size_fx}"
    # Standard lots should be scaled down by 100,000
    assert size_fx <= (2000 / 1.0850) / 100000.0 + 1e-5

    # 3. Crypto (e.g. BTC-USD or BTCUSDT) -> should NOT be divided by 100,000
    size_crypto, risk_crypto = trader.calculate_position_size(
        entry_price=60000.0,
        stop_loss=58000.0,
        symbol="BTC-USD",
        win_prob=0.65,
        r_r=3.0
    )
    assert size_crypto > 0, f"Crypto size should be positive, got {size_crypto}"


def test_auto_trader_execute_recommendation():
    """Test full execute_recommendation flow with thought logging resilience"""
    broker = DummyBroker(balance=10000.0)
    config = {
        "enabled": True,
        "max_position_size": 2000,
        "max_daily_loss": 500,
        "max_daily_profit": 1000,
        "min_confidence": 60
    }
    trader = AutoTrader(broker, config)

    rec = {
        "id": "test-rec-1",
        "symbol": "AAPL",
        "type": "BUY",
        "entryPrice": 150.0,
        "stopLoss": 147.0,
        "takeProfit": 159.0,
        "confidence": 75,
        "reasoning": {
            "technicalIndicators": ["RSI Oversold", "SMA Bullish Cross"],
            "marketTrend": "Bullish",
            "sentiment": "Positive",
            "summary": "High confidence long setup"
        }
    }

    result = trader.execute_recommendation(rec)
    assert result.get("executed") is True, f"Expected trade execution, got {result}"
    assert result.get("symbol") == "AAPL"
    assert len(broker.orders) == 1


def test_market_data_endpoints():
    """Test GET and POST /api/market-data endpoint contract and events presence"""
    client = TestClient(app)

    # 1. Test GET /api/market-data
    response_get = client.get("/api/market-data")
    assert response_get.status_code == 200, f"GET /api/market-data returned {response_get.status_code}"
    data_get = response_get.json()
    assert "marketData" in data_get, "marketData key missing in GET response"
    assert "events" in data_get, "events key missing in GET response"
    assert "status" in data_get, "status key missing in GET response"
    assert data_get["status"] == "active"
    assert isinstance(data_get["events"], list)

    # 2. Test POST /api/market-data with payload
    response_post = client.post("/api/market-data", json={"symbols": ["EURUSD=X", "BTC-USD"]})
    assert response_post.status_code == 200, f"POST /api/market-data returned {response_post.status_code}"
    data_post = response_post.json()
    assert "marketData" in data_post, "marketData key missing in POST response"
    assert "events" in data_post, "events key missing in POST response"
    assert "status" in data_post, "status key missing in POST response"
    assert data_post["status"] == "active"
    assert isinstance(data_post["events"], list)

    # 3. Test GET /api/scan-log
    response_scan_log = client.get("/api/scan-log")
    assert response_scan_log.status_code == 200
    assert "events" in response_scan_log.json()


def test_recommendation_scan_populates_scan_log():
    """Verify that running recommendation scan populates SCAN_LOG with fresh timestamps"""
    initial_len = len(SCAN_LOG)

    req = RecommendationRequest(
        symbols=[
            Symbol(symbol="EURUSD=X", assetType="FOREX"),
            Symbol(symbol="BTC-USD", assetType="CRYPTO")
        ],
        riskSettings=RiskSettings(minConfidence=50)
    )

    # Run scan asynchronously
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    res = loop.run_until_complete(_run_recommendation_scan(req))
    loop.close()

    assert len(SCAN_LOG) > initial_len, "SCAN_LOG should have new entries"
    latest_event = SCAN_LOG[0]
    assert "ts" in latest_event, "Event must contain timestamp 'ts'"
    assert "type" in latest_event, "Event must contain 'type'"
    print(f"\n[PASSED] Latest SCAN_LOG event: {latest_event}")


if __name__ == "__main__":
    print("Running Worker 1 Verification Suite...")
    test_auto_trader_calculate_position_size()
    print("✓ test_auto_trader_calculate_position_size passed")
    test_auto_trader_execute_recommendation()
    print("✓ test_auto_trader_execute_recommendation passed")
    test_market_data_endpoints()
    print("✓ test_market_data_endpoints passed")
    test_recommendation_scan_populates_scan_log()
    print("✓ test_recommendation_scan_populates_scan_log passed")
    print("\nAll Worker 1 tests passed successfully!")
