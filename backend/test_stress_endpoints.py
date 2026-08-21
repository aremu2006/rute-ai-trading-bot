"""
Stress Testing & Adversarial Verification Suite for RUTE AI Trading Bot Backend Endpoints
Challenger 2 Verification Suite

Covers:
1. High concurrency polling against GET and POST /api/market-data simultaneously.
2. Concurrent calls to POST /api/recommendations while background scanner runs actively.
3. Edge cases, malformed payloads, empty/invalid symbols, extreme parameters.
4. SCAN_LOG bounded memory (maxlen=1000), chronological ordering, and thread safety.
5. Response latency benchmarking (<200ms target).
"""

import sys
import os
import asyncio
import time
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from typing import Dict, List, Any

# Ensure backend path is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from main import (
    app,
    SCAN_LOG,
    _run_recommendation_scan,
    _async_scan_lock,
    RecommendationRequest,
    MarketDataRequest,
    Symbol,
    RiskSettings
)


def run_all_stress_tests() -> Dict[str, Any]:
    """Execute complete stress test suite and return detailed metrics report."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "suites": {},
        "summary": {"total_tests": 0, "passed": 0, "failed": 0},
        "verdict": "UNKNOWN"
    }

    client = TestClient(app)

    # =========================================================================
    # Suite 1: High Concurrency Polling against GET and POST /api/market-data
    # =========================================================================
    print("\n" + "="*70)
    print(" SUITE 1: High Concurrency Polling (GET & POST /api/market-data)")
    print("="*70)
    
    suite1_results = {}
    concurrency = 100
    latencies = []
    errors = []

    def poll_get(i):
        t0 = time.perf_counter()
        try:
            resp = client.get(f"/api/market-data?limit=20")
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)
            if resp.status_code != 200:
                errors.append(f"GET poll {i} failed with status {resp.status_code}")
            data = resp.json()
            if "marketData" not in data or "events" not in data or data.get("status") != "active":
                errors.append(f"GET poll {i} invalid schema: {data.keys()}")
        except Exception as e:
            errors.append(f"GET poll {i} exception: {e}")

    def poll_post(i):
        t0 = time.perf_counter()
        try:
            resp = client.post("/api/market-data", json={"symbols": ["EURUSD=X", "BTC-USD", "AAPL"]})
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)
            if resp.status_code != 200:
                errors.append(f"POST poll {i} failed with status {resp.status_code}")
            data = resp.json()
            if "marketData" not in data or "events" not in data or data.get("status") != "active":
                errors.append(f"POST poll {i} invalid schema: {data.keys()}")
        except Exception as e:
            errors.append(f"POST poll {i} exception: {e}")

    # Launch 50 GET and 50 POST concurrent requests
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = []
        for i in range(concurrency // 2):
            futures.append(pool.submit(poll_get, i))
            futures.append(pool.submit(poll_post, i))
        for f in futures:
            f.result()

    sorted_latencies = sorted(latencies)
    p50 = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0
    p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)] if sorted_latencies else 0
    p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)] if sorted_latencies else 0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    suite1_results["total_requests"] = concurrency
    suite1_results["error_count"] = len(errors)
    suite1_results["avg_latency_ms"] = round(avg_latency, 2)
    suite1_results["p50_latency_ms"] = round(p50, 2)
    suite1_results["p95_latency_ms"] = round(p95, 2)
    suite1_results["p99_latency_ms"] = round(p99, 2)
    suite1_results["min_latency_ms"] = round(min(latencies), 2) if latencies else 0
    suite1_results["max_latency_ms"] = round(max(latencies), 2) if latencies else 0
    suite1_results["passed"] = (len(errors) == 0 and p95 < 200.0)

    print(f"Total Requests: {concurrency} (50 GET, 50 POST)")
    print(f"Errors: {len(errors)}")
    print(f"Latency: Avg={avg_latency:.2f}ms, P50={p50:.2f}ms, P95={p95:.2f}ms, P99={p99:.2f}ms")
    print(f"Suite 1 Passed: {suite1_results['passed']}")
    results["suites"]["suite_1_high_concurrency_polling"] = suite1_results

    # =========================================================================
    # Suite 2: Concurrent POST /api/recommendations with Background Scanner Active
    # =========================================================================
    print("\n" + "="*70)
    print(" SUITE 2: Concurrent Recommendations & Background Scanner Simulation")
    print("="*70)

    suite2_results = {}
    rec_errors = []
    background_iterations = 5

    async def async_scanner_simulation():
        """Simulate autonomous background scanner runs while concurrent API calls arrive."""
        scan_req = RecommendationRequest(
            symbols=[
                Symbol(symbol="EURUSD=X", assetType="FOREX"),
                Symbol(symbol="BTC-USD", assetType="CRYPTO")
            ],
            riskSettings=RiskSettings(minConfidence=50)
        )

        async def bg_worker():
            for _ in range(background_iterations):
                async with _async_scan_lock:
                    await _run_recommendation_scan(scan_req)
                await asyncio.sleep(0.05)

        async def api_caller(call_id):
            client_req = RecommendationRequest(
                symbols=[
                    Symbol(symbol="GBPUSD=X", assetType="FOREX"),
                    Symbol(symbol="ETH-USD", assetType="CRYPTO")
                ],
                riskSettings=RiskSettings(minConfidence=60)
            )
            try:
                async with _async_scan_lock:
                    res = await _run_recommendation_scan(client_req)
                if not res or "recommendations" not in res or "marketAnalysis" not in res:
                    rec_errors.append(f"Call {call_id} returned invalid structure: {res}")
            except Exception as exc:
                rec_errors.append(f"Call {call_id} raised exception: {exc}")

        # Run background loop and 8 concurrent client recommendation scans
        tasks = [asyncio.create_task(bg_worker())]
        for c in range(8):
            tasks.append(asyncio.create_task(api_caller(c)))

        await asyncio.gather(*tasks, return_exceptions=True)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    t0 = time.perf_counter()
    loop.run_until_complete(async_scanner_simulation())
    loop.close()
    elapsed_rec_test = time.perf_counter() - t0

    suite2_results["background_cycles"] = background_iterations
    suite2_results["concurrent_api_calls"] = 8
    suite2_results["error_count"] = len(rec_errors)
    suite2_results["total_time_seconds"] = round(elapsed_rec_test, 3)
    suite2_results["passed"] = (len(rec_errors) == 0)

    print(f"Completed in {elapsed_rec_test:.2f}s with {len(rec_errors)} errors")
    print(f"Suite 2 Passed: {suite2_results['passed']}")
    results["suites"]["suite_2_concurrent_recommendations_lock"] = suite2_results

    # =========================================================================
    # Suite 3: Malformed Payloads, Edge Cases, and Boundary Limits
    # =========================================================================
    print("\n" + "="*70)
    print(" SUITE 3: Malformed Payloads, Edge Cases & Error Handling")
    print("="*70)

    suite3_cases = []

    # Case 3.1: GET with empty symbols param
    r = client.get("/api/market-data?symbols=")
    suite3_cases.append({
        "case": "GET market-data empty symbols string",
        "status_code": r.status_code,
        "valid": (r.status_code == 200 and "marketData" in r.json())
    })

    # Case 3.2: GET with comma-only symbols param
    r = client.get("/api/market-data?symbols=,,")
    suite3_cases.append({
        "case": "GET market-data comma-only symbols",
        "status_code": r.status_code,
        "valid": (r.status_code == 200 and "marketData" in r.json())
    })

    # Case 3.3: GET with limit boundary values (limit=0, limit=-5, limit=100000)
    r_lim0 = client.get("/api/market-data?limit=0")
    r_lim_neg = client.get("/api/market-data?limit=-5")
    r_lim_huge = client.get("/api/market-data?limit=100000")
    suite3_cases.append({
        "case": "GET market-data limit boundaries (0, -5, 100000)",
        "status_code": (r_lim0.status_code, r_lim_neg.status_code, r_lim_huge.status_code),
        "valid": (r_lim0.status_code == 200 and r_lim_neg.status_code == 200 and r_lim_huge.status_code == 200)
    })

    # Case 3.4: GET with non-integer limit (422 validation)
    r = client.get("/api/market-data?limit=invalid_number")
    suite3_cases.append({
        "case": "GET market-data invalid limit type",
        "status_code": r.status_code,
        "valid": (r.status_code == 422)
    })

    # Case 3.5: POST /api/market-data empty payload
    r = client.post("/api/market-data", json={})
    suite3_cases.append({
        "case": "POST market-data empty object {}",
        "status_code": r.status_code,
        "valid": (r.status_code == 200 and "marketData" in r.json())
    })

    # Case 3.6: POST /api/market-data empty symbols list
    r = client.post("/api/market-data", json={"symbols": []})
    suite3_cases.append({
        "case": "POST market-data empty symbols array []",
        "status_code": r.status_code,
        "valid": (r.status_code == 200 and "marketData" in r.json())
    })

    # Case 3.7: POST /api/market-data non-existent / malformed symbols
    r = client.post("/api/market-data", json={"symbols": ["INVALID_TICKER_9999", "!@#$%", ""]})
    suite3_cases.append({
        "case": "POST market-data invalid symbols",
        "status_code": r.status_code,
        "valid": (r.status_code == 200 and "marketData" in r.json())
    })

    # Case 3.8: POST /api/market-data malformed type (symbols=12345)
    r = client.post("/api/market-data", json={"symbols": 12345})
    suite3_cases.append({
        "case": "POST market-data malformed type (symbols: int)",
        "status_code": r.status_code,
        "valid": (r.status_code == 422)
    })

    # Case 3.9: POST /api/recommendations empty payload {} -> 422
    r = client.post("/api/recommendations", json={})
    suite3_cases.append({
        "case": "POST recommendations missing required symbols field",
        "status_code": r.status_code,
        "valid": (r.status_code == 422)
    })

    # Case 3.10: POST /api/recommendations empty symbols array [] -> returns empty recs
    r = client.post("/api/recommendations", json={"symbols": []})
    suite3_cases.append({
        "case": "POST recommendations empty symbols array",
        "status_code": r.status_code,
        "valid": (r.status_code == 200 and r.json().get("recommendations") == [])
    })

    # Case 3.11: POST /api/recommendations with extreme risk settings
    r = client.post("/api/recommendations", json={
        "symbols": [{"symbol": "EURUSD=X", "assetType": "FOREX"}],
        "riskSettings": {
            "maxPositionSize": -5000,
            "maxDailyLoss": -1000,
            "stopLossPercentage": 99999.0,
            "takeProfitPercentage": -10.0,
            "minConfidence": -100
        }
    })
    suite3_cases.append({
        "case": "POST recommendations extreme risk settings",
        "status_code": r.status_code,
        "valid": (r.status_code == 200)
    })

    suite3_passed = all(c["valid"] for c in suite3_cases)
    for c in suite3_cases:
        print(f" - {c['case']}: status={c['status_code']}, valid={c['valid']}")

    results["suites"]["suite_3_edge_cases_and_malformed_payloads"] = {
        "cases": suite3_cases,
        "passed": suite3_passed
    }

    # =========================================================================
    # Suite 4: SCAN_LOG Bounded Memory (maxlen=1000) & Ordering Invariant
    # =========================================================================
    print("\n" + "="*70)
    print(" SUITE 4: SCAN_LOG Memory Bounds (maxlen) & Chronological Ordering")
    print("="*70)

    initial_len = len(SCAN_LOG)
    # Flood SCAN_LOG with 2500 entries to test circular buffer retention
    for i in range(2500):
        SCAN_LOG.appendleft({
            "ts": datetime.now().isoformat(),
            "type": "stress_test_event",
            "index": i,
            "message": f"Stress test event {i}"
        })

    bounded_len = len(SCAN_LOG)
    is_bounded = (bounded_len == 1000)

    # Check ordering: SCAN_LOG[0] must have highest index (latest added)
    latest_event = SCAN_LOG[0]
    oldest_event = SCAN_LOG[-1]
    is_ordered = (latest_event.get("index") == 2499 and oldest_event.get("index") == 1500)

    # Concurrent read-write test on deque
    deque_errors = []
    def deque_writer():
        for i in range(500):
            SCAN_LOG.appendleft({"ts": datetime.now().isoformat(), "type": "rw_test", "i": i})
            time.sleep(0.0001)

    def deque_reader():
        for _ in range(500):
            try:
                snapshot = list(SCAN_LOG)[:50]
                if len(snapshot) > 50:
                    deque_errors.append("Snapshot exceeded slice limit")
            except Exception as e:
                deque_errors.append(f"Concurrent deque read error: {e}")
            time.sleep(0.0001)

    with ThreadPoolExecutor(max_workers=4) as pool:
        f1 = pool.submit(deque_writer)
        f2 = pool.submit(deque_reader)
        f3 = pool.submit(deque_reader)
        f1.result()
        f2.result()
        f3.result()

    suite4_passed = is_bounded and is_ordered and len(deque_errors) == 0
    suite4_results = {
        "initial_len": initial_len,
        "flooded_entries": 2500,
        "final_len": bounded_len,
        "max_capacity": SCAN_LOG.maxlen,
        "is_strictly_bounded": is_bounded,
        "is_ordered_lifo_latest_first": is_ordered,
        "concurrent_rw_errors": len(deque_errors),
        "passed": suite4_passed
    }

    print(f"Buffer size after 2,500 inserts: {bounded_len} (maxlen={SCAN_LOG.maxlen})")
    print(f"Ordering check: Newest index={latest_event.get('index')}, Oldest index={oldest_event.get('index')}")
    print(f"Concurrent Read/Write errors: {len(deque_errors)}")
    print(f"Suite 4 Passed: {suite4_passed}")
    results["suites"]["suite_4_scan_log_bounds_and_order"] = suite4_results

    # =========================================================================
    # Suite 5: Response Latency Benchmarking (< 200ms)
    # =========================================================================
    print("\n" + "="*70)
    print(" SUITE 5: Response Latency Benchmarking (Target: < 200ms)")
    print("="*70)

    benchmark_runs = 200
    bench_latencies = []

    for _ in range(benchmark_runs):
        t0 = time.perf_counter()
        resp = client.get("/api/market-data")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if resp.status_code == 200:
            bench_latencies.append(elapsed_ms)

    bench_sorted = sorted(bench_latencies)
    b_p50 = bench_sorted[len(bench_sorted) // 2]
    b_p95 = bench_sorted[int(len(bench_sorted) * 0.95)]
    b_p99 = bench_sorted[int(len(bench_sorted) * 0.99)]
    b_avg = sum(bench_latencies) / len(bench_latencies)
    b_max = max(bench_latencies)

    suite5_passed = (b_p95 < 200.0)
    suite5_results = {
        "total_benchmark_requests": benchmark_runs,
        "avg_latency_ms": round(b_avg, 2),
        "p50_latency_ms": round(b_p50, 2),
        "p95_latency_ms": round(b_p95, 2),
        "p99_latency_ms": round(b_p99, 2),
        "max_latency_ms": round(b_max, 2),
        "target_p95_ms": 200.0,
        "passed": suite5_passed
    }

    print(f"Benchmark: {benchmark_runs} calls | Avg: {b_avg:.2f}ms | P50: {b_p50:.2f}ms | P95: {b_p95:.2f}ms | P99: {b_p99:.2f}ms | Max: {b_max:.2f}ms")
    print(f"Suite 5 Passed (P95 < 200ms): {suite5_passed}")
    results["suites"]["suite_5_response_latency_benchmark"] = suite5_results

    # =========================================================================
    # Overall Verdict
    # =========================================================================
    all_passed = (
        suite1_results["passed"] and
        suite2_results["passed"] and
        suite3_passed and
        suite4_passed and
        suite5_passed
    )

    results["verdict"] = "APPROVE" if all_passed else "FAIL"
    print("\n" + "="*70)
    print(f" OVERALL VERDICT: {results['verdict']}")
    print("="*70)

    return results


if __name__ == "__main__":
    res = run_all_stress_tests()
    print("\nResult Summary JSON:")
    print(json.dumps(res, indent=2))
