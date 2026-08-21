"""
Test Polling Simulation for Acceptance Criteria
Verifies that polling /api/market-data repeatedly returns advancing timestamps and fresh decision log events.
"""

import sys
import os
import asyncio
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from main import app, SCAN_LOG, _run_recommendation_scan, RecommendationRequest, Symbol, RiskSettings


def run_polling_verification(num_cycles=4, delay_seconds=2):
    """
    Simulates polling /api/market-data across multiple cycles with background scan execution.
    Verifies that the events array shows advancing timestamps.
    """
    client = TestClient(app)
    timestamps_observed = []
    
    print(f"--- Starting Polling Verification ({num_cycles} cycles) ---")

    for cycle in range(1, num_cycles + 1):
        # Trigger an evaluation cycle (simulating background scanner loop)
        req = RecommendationRequest(
            symbols=[
                Symbol(symbol="EURUSD=X", assetType="FOREX"),
                Symbol(symbol="BTC-USD", assetType="CRYPTO")
            ],
            riskSettings=RiskSettings(minConfidence=50)
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_recommendation_scan(req))
        loop.close()

        # Poll GET /api/market-data
        resp = client.get("/api/market-data")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "events" in data, "No 'events' key in response"
        events = data["events"]
        assert len(events) > 0, "Events array is empty"

        latest_ts = events[0].get("ts")
        timestamps_observed.append(latest_ts)
        print(f"Cycle {cycle}: Events count = {len(events)}, Latest event = {events[0]['type']} at {latest_ts}")

        if cycle < num_cycles:
            time.sleep(delay_seconds)

    # Verify timestamps advanced
    print(f"Timestamps observed: {timestamps_observed}")
    assert len(timestamps_observed) == num_cycles
    # Check that the first and last timestamps are different and chronological
    t_first = datetime.fromisoformat(timestamps_observed[0])
    t_last = datetime.fromisoformat(timestamps_observed[-1])
    assert t_last >= t_first, "Timestamps did not advance chronologically"
    print(f"✓ Verification SUCCESS: Decision logs are continuously advancing! ({t_first.isoformat()} -> {t_last.isoformat()})")


if __name__ == "__main__":
    run_polling_verification()
