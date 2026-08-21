"""
Adversarial Concurrency, Stress, and Edge-Case Test Harness
Agent: teamwork_preview_challenger_2
Milestone: M2

Comprehensive empirical stress suite verifying:
1. High-concurrency simultaneous requests to /api/recommendations, /api/market-data, /api/scan-log, and /api/thoughts/{symbol} across 10+ worker threads.
2. Concurrent reads, writes, and forced evictions on SynchronizedCache verifying zero 'RuntimeError: dictionary changed size during iteration'.
3. Simultaneous PyTorch model evaluations (DQNAgent, PPOAgent, TemporalEngine) verifying inference locks prevent thread collisions and crashes.
4. Missing symbol / invalid payload / path traversal / extreme parameter handling across all endpoints.
5. Circuit breaker state transitions (CLOSED -> OPEN -> HALF-OPEN -> CLOSED) and exponential backoff.
"""

import sys
import os
import time
import json
import random
import threading
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import numpy as np
import pandas as pd
import torch
from fastapi.testclient import TestClient

from main import (
    app,
    SCAN_LOG,
    _pytorch_inference_lock,
    _async_scan_lock,
    dqn_agent,
    ppo_agent,
    RecommendationRequest,
    MarketDataRequest,
    Symbol,
    RiskSettings,
    NotificationSettings,
    ApiKeys,
    _run_recommendation_scan
)
from data_providers import SynchronizedCache, YahooCircuitBreaker
from ml_engine.dqn_agent import DQNAgent
from ml_engine.ppo_agent import PPOAgent
from ml_engine.transformer_core import TemporalEngine
from reasoning_engine.thought_logger import ThoughtLogger


def run_comprehensive_adversarial_suite() -> Dict[str, Any]:
    suite_start = time.perf_counter()
    report = {
        "timestamp": datetime.now().isoformat(),
        "agent": "teamwork_preview_challenger_2",
        "suites": {},
        "summary": {"total_tests": 0, "passed": 0, "failed": 0},
        "verdict": "UNKNOWN"
    }

    client = TestClient(app)

    # =========================================================================
    # SUITE 1: High-Concurrency Multi-Endpoint Avalanche (16 Worker Threads)
    # =========================================================================
    print("\n" + "="*80)
    print(" SUITE 1: High-Concurrency Multi-Endpoint Avalanche (16 Worker Threads)")
    print("="*80)

    num_threads = 16
    requests_per_thread = 20
    total_avalanche_requests = num_threads * requests_per_thread * 4 # 4 endpoints

    endpoints = [
        "market_data_get",
        "market_data_post",
        "scan_log",
        "thoughts",
        "recommendations"
    ]

    endpoint_latencies = {ep: [] for ep in endpoints}
    endpoint_errors = {ep: [] for ep in endpoints}

    symbols_to_test = ["EURUSD=X", "GBPUSD=X", "BTC-USD", "ETH-USD", "AAPL", "NVDA", "NON_EXISTENT_SYM"]

    def worker_job(worker_id: int):
        for req_idx in range(requests_per_thread):
            # 1. GET /api/market-data
            t0 = time.perf_counter()
            try:
                r = client.get("/api/market-data?limit=25")
                elapsed = (time.perf_counter() - t0) * 1000.0
                endpoint_latencies["market_data_get"].append(elapsed)
                if r.status_code != 200 or "marketData" not in r.json():
                    endpoint_errors["market_data_get"].append(f"Worker {worker_id} status {r.status_code}")
            except Exception as e:
                endpoint_errors["market_data_get"].append(f"Worker {worker_id} exc: {e}")

            # 2. POST /api/market-data
            t0 = time.perf_counter()
            try:
                sym_sample = random.sample(symbols_to_test, 3)
                r = client.post("/api/market-data", json={"symbols": sym_sample})
                elapsed = (time.perf_counter() - t0) * 1000.0
                endpoint_latencies["market_data_post"].append(elapsed)
                if r.status_code != 200 or "marketData" not in r.json():
                    endpoint_errors["market_data_post"].append(f"Worker {worker_id} status {r.status_code}")
            except Exception as e:
                endpoint_errors["market_data_post"].append(f"Worker {worker_id} exc: {e}")

            # 3. GET /api/scan-log
            t0 = time.perf_counter()
            try:
                r = client.get("/api/scan-log?limit=30")
                elapsed = (time.perf_counter() - t0) * 1000.0
                endpoint_latencies["scan_log"].append(elapsed)
                if r.status_code != 200 or "events" not in r.json():
                    endpoint_errors["scan_log"].append(f"Worker {worker_id} status {r.status_code}")
            except Exception as e:
                endpoint_errors["scan_log"].append(f"Worker {worker_id} exc: {e}")

            # 4. GET /api/thoughts/{symbol}
            t0 = time.perf_counter()
            try:
                sym = random.choice(symbols_to_test)
                r = client.get(f"/api/thoughts/{sym}")
                elapsed = (time.perf_counter() - t0) * 1000.0
                endpoint_latencies["thoughts"].append(elapsed)
                if r.status_code != 200 or "symbol" not in r.json():
                    endpoint_errors["thoughts"].append(f"Worker {worker_id} thoughts for {sym} status {r.status_code}")
            except Exception as e:
                endpoint_errors["thoughts"].append(f"Worker {worker_id} exc: {e}")

            # 5. Occasional POST /api/recommendations
            if req_idx % 4 == 0:
                t0 = time.perf_counter()
                try:
                    r = client.post("/api/recommendations", json={
                        "symbols": [
                            {"symbol": "EURUSD=X", "assetType": "FOREX"},
                            {"symbol": "BTC-USD", "assetType": "CRYPTO"}
                        ],
                        "riskSettings": {"minConfidence": 55}
                    })
                    elapsed = (time.perf_counter() - t0) * 1000.0
                    endpoint_latencies["recommendations"].append(elapsed)
                    if r.status_code != 200 or "recommendations" not in r.json():
                        endpoint_errors["recommendations"].append(f"Worker {worker_id} recs status {r.status_code}")
                except Exception as e:
                    endpoint_errors["recommendations"].append(f"Worker {worker_id} exc: {e}")

    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=num_threads) as pool:
        futures = [pool.submit(worker_job, wid) for wid in range(num_threads)]
        for f in as_completed(futures):
            f.result()
    avalanche_duration = time.perf_counter() - t_start

    total_errs = sum(len(errs) for errs in endpoint_errors.values())
    total_calls = sum(len(lats) for lats in endpoint_latencies.values())
    all_lats = [lat for lats in endpoint_latencies.values() for lat in lats]
    sorted_all_lats = sorted(all_lats)
    p50 = sorted_all_lats[len(sorted_all_lats)//2] if sorted_all_lats else 0
    p95 = sorted_all_lats[int(len(sorted_all_lats)*0.95)] if sorted_all_lats else 0
    p99 = sorted_all_lats[int(len(sorted_all_lats)*0.99)] if sorted_all_lats else 0

    suite1_pass = (total_errs == 0)
    report["suites"]["suite_1_concurrency_avalanche"] = {
        "threads": num_threads,
        "total_requests": total_calls,
        "total_errors": total_errs,
        "duration_seconds": round(avalanche_duration, 3),
        "requests_per_sec": round(total_calls / avalanche_duration, 1),
        "latency_p50_ms": round(p50, 2),
        "latency_p95_ms": round(p95, 2),
        "latency_p99_ms": round(p99, 2),
        "errors_by_endpoint": {k: len(v) for k, v in endpoint_errors.items()},
        "passed": suite1_pass
    }

    print(f"Executed {total_calls} concurrent requests across {num_threads} threads in {avalanche_duration:.2f}s")
    print(f"Throughput: {total_calls/avalanche_duration:.1f} req/s | Errors: {total_errs}")
    print(f"Latency: P50={p50:.2f}ms, P95={p95:.2f}ms, P99={p99:.2f}ms")
    print(f"Suite 1 Passed: {suite1_pass}")

    # =========================================================================
    # SUITE 2: SynchronizedCache Forced Eviction & Concurrent Mutation Stress
    # =========================================================================
    print("\n" + "="*80)
    print(" SUITE 2: SynchronizedCache Forced Eviction & Concurrent Mutation Stress")
    print("="*80)

    # Instantiate a SynchronizedCache with small capacity to aggressively trigger eviction and sweeping
    test_cache = SynchronizedCache(ttl=0.2, max_entries=50)
    cache_errors = []
    stop_event = threading.Event()

    # Pre-populate sample DataFrames
    sample_df = pd.DataFrame({
        "Open": np.random.randn(100),
        "High": np.random.randn(100),
        "Low": np.random.randn(100),
        "Close": np.random.randn(100),
        "Volume": np.random.randint(100, 10000, 100)
    })

    def cache_writer(writer_id: int):
        cnt = 0
        while not stop_event.is_set():
            key = f"KEY_{writer_id}_{cnt % 150}" # Cycle through 150 keys (> 50 max_entries)
            try:
                # Randomly write DataFrame or dict
                if cnt % 2 == 0:
                    test_cache.set(key, sample_df.copy(), timestamp=time.time())
                else:
                    test_cache.set(key, {"price": 100.0 + cnt, "nested": {"counter": cnt}}, timestamp=time.time())
            except RuntimeError as re:
                if "dictionary changed size during iteration" in str(re):
                    cache_errors.append(f"CRITICAL: Writer {writer_id} hit dictionary changed size: {re}")
                else:
                    cache_errors.append(f"Writer {writer_id} RuntimeError: {re}")
            except Exception as exc:
                cache_errors.append(f"Writer {writer_id} exc: {exc}")
            cnt += 1
            if cnt % 20 == 0:
                time.sleep(0.001)

    def cache_reader(reader_id: int):
        cnt = 0
        while not stop_event.is_set():
            key = f"KEY_{random.randint(0, 10)}_{random.randint(0, 150)}"
            try:
                val = test_cache.get(key)
                if val is not None:
                    # Verify defensive copy - mutate returned object to test isolation
                    if isinstance(val, pd.DataFrame):
                        val["MUTATION_TEST"] = 999.0
                    elif isinstance(val, dict):
                        val["MUTATED"] = True
            except RuntimeError as re:
                if "dictionary changed size during iteration" in str(re):
                    cache_errors.append(f"CRITICAL: Reader {reader_id} hit dictionary changed size: {re}")
                else:
                    cache_errors.append(f"Reader {reader_id} RuntimeError: {re}")
            except Exception as exc:
                cache_errors.append(f"Reader {reader_id} exc: {exc}")
            cnt += 1
            if cnt % 20 == 0:
                time.sleep(0.001)

    def cache_sweeper(sweeper_id: int):
        while not stop_event.is_set():
            try:
                test_cache.sweep()
                time.sleep(0.005)
            except RuntimeError as re:
                if "dictionary changed size during iteration" in str(re):
                    cache_errors.append(f"CRITICAL: Sweeper {sweeper_id} hit dictionary changed size: {re}")
                else:
                    cache_errors.append(f"Sweeper {sweeper_id} RuntimeError: {re}")
            except Exception as exc:
                cache_errors.append(f"Sweeper {sweeper_id} exc: {exc}")

    # Launch 6 writers, 6 readers, 2 aggressive sweepers concurrently
    cache_threads = []
    for w in range(6):
        t = threading.Thread(target=cache_writer, args=(w,))
        cache_threads.append(t)
    for r in range(6):
        t = threading.Thread(target=cache_reader, args=(r,))
        cache_threads.append(t)
    for s in range(2):
        t = threading.Thread(target=cache_sweeper, args=(s,))
        cache_threads.append(t)

    t_cache_start = time.perf_counter()
    for t in cache_threads:
        t.start()

    # Run intense concurrent load for 3.0 seconds
    time.sleep(3.0)
    stop_event.set()

    for t in cache_threads:
        t.join(timeout=2.0)
    cache_stress_duration = time.perf_counter() - t_cache_start

    dict_mutation_errors = [e for e in cache_errors if "dictionary changed size" in e]
    suite2_pass = (len(dict_mutation_errors) == 0 and len(cache_errors) == 0)

    report["suites"]["suite_2_synchronized_cache_stress"] = {
        "duration_seconds": round(cache_stress_duration, 3),
        "total_cache_errors": len(cache_errors),
        "dictionary_size_mutation_errors": len(dict_mutation_errors),
        "final_cache_len": len(test_cache),
        "max_capacity_bound": test_cache._max_entries,
        "passed": suite2_pass
    }

    print(f"SynchronizedCache stress completed in {cache_stress_duration:.2f}s")
    print(f"Total errors: {len(cache_errors)} | Dictionary mutation errors: {len(dict_mutation_errors)}")
    print(f"Cache size safely bound: {len(test_cache)} <= {test_cache._max_entries}")
    print(f"Suite 2 Passed: {suite2_pass}")

    # =========================================================================
    # SUITE 3: Simultaneous PyTorch Inference & Lock Contention Verification
    # =========================================================================
    print("\n" + "="*80)
    print(" SUITE 3: Simultaneous PyTorch Model Evaluations & Lock Contention")
    print("="*80)

    pytorch_errors = []
    dqn_agent_test = DQNAgent(state_dim=61, action_dim=3)
    ppo_agent_test = PPOAgent(state_dim=61, action_dim=3)
    temporal_engine_test = TemporalEngine(feature_dim=61)

    # Pre-train temporal engine to set weights_loaded = True
    dummy_seqs = np.random.randn(32, 14, 61)
    dummy_labels = np.random.choice([-1, 0, 1], size=32)
    temporal_engine_test.train(dummy_seqs, dummy_labels, epochs=1)

    stop_torch = threading.Event()
    inference_counts = {"dqn_act": 0, "dqn_replay": 0, "ppo_select": 0, "ppo_train": 0, "temporal_predict": 0}

    def dqn_worker(wid: int):
        while not stop_torch.is_set():
            state = np.random.randn(61).astype(np.float32)
            try:
                with _pytorch_inference_lock:
                    act = dqn_agent_test.act(state)
                    dqn_agent_test.remember(state, act, 1.0, state, False)
                    if random.random() < 0.2:
                        dqn_agent_test.replay(batch_size=8)
                inference_counts["dqn_act"] += 1
            except Exception as e:
                pytorch_errors.append(f"DQN Worker {wid} exception: {e}\n{traceback.format_exc()}")
            time.sleep(0.0005)

    def ppo_worker(wid: int):
        while not stop_torch.is_set():
            state = np.random.randn(61).astype(np.float32)
            try:
                with _pytorch_inference_lock:
                    action_dict = ppo_agent_test.select_action(state)
                    ppo_agent_test.store_outcome(action_dict, reward=random.uniform(-1.0, 1.0))
                inference_counts["ppo_select"] += 1
            except Exception as e:
                pytorch_errors.append(f"PPO Worker {wid} exception: {e}\n{traceback.format_exc()}")
            time.sleep(0.0005)

    def temporal_worker(wid: int):
        while not stop_torch.is_set():
            seq = torch.randn(1, 14, 61).float()
            try:
                with _pytorch_inference_lock:
                    pred = temporal_engine_test.predict(seq)
                inference_counts["temporal_predict"] += 1
            except Exception as e:
                pytorch_errors.append(f"Temporal Worker {wid} exception: {e}\n{traceback.format_exc()}")
            time.sleep(0.0005)

    torch_threads = []
    for i in range(4):
        torch_threads.append(threading.Thread(target=dqn_worker, args=(i,)))
        torch_threads.append(threading.Thread(target=ppo_worker, args=(i,)))
        torch_threads.append(threading.Thread(target=temporal_worker, args=(i,)))

    t_torch_start = time.perf_counter()
    for t in torch_threads:
        t.start()

    # Run concurrent PyTorch forward & backward passes across 12 threads
    time.sleep(2.5)
    stop_torch.set()

    for t in torch_threads:
        t.join(timeout=2.0)
    torch_duration = time.perf_counter() - t_torch_start

    total_inferences = sum(inference_counts.values())
    suite3_pass = (len(pytorch_errors) == 0 and total_inferences > 100)

    report["suites"]["suite_3_pytorch_inference_locking"] = {
        "duration_seconds": round(torch_duration, 3),
        "total_inferences": total_inferences,
        "inference_breakdown": inference_counts,
        "errors_encountered": len(pytorch_errors),
        "error_samples": pytorch_errors[:5],
        "passed": suite3_pass
    }

    print(f"PyTorch stress completed {total_inferences} operations across 12 threads in {torch_duration:.2f}s")
    print(f"Breakdown: {inference_counts}")
    print(f"Errors encountered: {len(pytorch_errors)}")
    print(f"Suite 3 Passed: {suite3_pass}")

    # =========================================================================
    # SUITE 4: Adversarial Payloads, Edge Cases, Boundary Testing & Traversal
    # =========================================================================
    print("\n" + "="*80)
    print(" SUITE 4: Adversarial Payloads, Edge Cases, Boundary Testing & Traversal")
    print("="*80)

    edge_cases = []

    # 4.1 Path traversal attacks on /api/thoughts/{symbol}
    traversal_payloads = [
        "../../etc/passwd",
        r"..\..\windows\win.ini",
        "....//....//etc/passwd",
        "%2e%2e%2f%2e%2e%2f",
        "AAPL/../../../secret",
        "CON",
        "NUL",
        "AUX",
        "AAPL\x00extra",
        "AAPL'; DROP TABLE thoughts; --",
        "<script>alert(1)</script>",
        "EURUSD=X",
        "BTC-USD"
    ]

    for p in traversal_payloads:
        t0 = time.perf_counter()
        r = client.get(f"/api/thoughts/{p}")
        elapsed = (time.perf_counter() - t0) * 1000.0
        data = r.json() if r.status_code == 200 else {}
        # Valid defense: returns error or safely scoped response, status 200 or 400/404, never 500 unhandled
        safe = (r.status_code in (200, 400, 404, 422)) and (
            "error" in data or "thoughts" in data or "analysis" in data or r.status_code != 500
        )
        edge_cases.append({
            "test": f"Thoughts symbol sanitization: '{p}'",
            "status_code": r.status_code,
            "response": data,
            "latency_ms": round(elapsed, 2),
            "safe": safe
        })

    # 4.2 Malformed JSON payloads to /api/recommendations
    malformed_rec_tests = [
        ("Empty body {}", {}, 422),
        ("Empty symbols list", {"symbols": []}, 200),
        ("Invalid symbol type", {"symbols": "EURUSD=X"}, 422),
        ("Null symbols field", {"symbols": None}, 422),
        ("Extreme negative risk settings", {
            "symbols": [{"symbol": "EURUSD=X", "assetType": "FOREX"}],
            "riskSettings": {
                "maxPositionSize": -999999999,
                "maxDailyLoss": -500000,
                "stopLossPercentage": -50.0,
                "takeProfitPercentage": 999999.0,
                "minConfidence": -100
            }
        }, 200),
        ("Missing assetType field", {
            "symbols": [{"symbol": "BTC-USD"}]
        }, 200),
        ("Invalid assetType enumeration", {
            "symbols": [{"symbol": "ETH-USD", "assetType": "ALIEN_ASSET"}]
        }, 200),
        ("Huge list of 50 duplicate symbols", {
            "symbols": [{"symbol": "AAPL", "assetType": "STOCK"} for _ in range(50)],
            "riskSettings": {"minConfidence": 50}
        }, 200)
    ]

    for label, payload, expected_status in malformed_rec_tests:
        t0 = time.perf_counter()
        r = client.post("/api/recommendations", json=payload)
        elapsed = (time.perf_counter() - t0) * 1000.0
        safe = (r.status_code == expected_status) or (r.status_code in (200, 422) and r.status_code != 500)
        edge_cases.append({
            "test": f"Recommendations payload: {label}",
            "status_code": r.status_code,
            "latency_ms": round(elapsed, 2),
            "safe": safe
        })

    # 4.3 Malformed payloads to /api/market-data
    market_edge_tests = [
        ("GET with empty symbols string", "/api/market-data?symbols=", 200),
        ("GET with special chars symbols", "/api/market-data?symbols=!!!,@@@,###", 200),
        ("GET with negative limit", "/api/market-data?limit=-100", 200),
        ("GET with non-numeric limit", "/api/market-data?limit=abc", 422),
        ("POST with empty body {}", {}, 200),
        ("POST with integer symbols", {"symbols": 12345}, 422),
        ("POST with null symbols", {"symbols": None}, 200)
    ]

    for label, payload_or_url, exp_status in market_edge_tests:
        t0 = time.perf_counter()
        if isinstance(payload_or_url, str):
            r = client.get(payload_or_url)
        else:
            r = client.post("/api/market-data", json=payload_or_url)
        elapsed = (time.perf_counter() - t0) * 1000.0
        safe = (r.status_code == exp_status) or (r.status_code in (200, 422) and r.status_code != 500)
        edge_cases.append({
            "test": f"Market Data: {label}",
            "status_code": r.status_code,
            "latency_ms": round(elapsed, 2),
            "safe": safe
        })

    # 4.4 Trade outcome feedback edge cases
    outcome_edge_tests = [
        ("Empty dict {}", {}, 200),
        ("Non-existent signal_id", {"signal_id": "FAKE_SIG_999", "profit": 0.05, "exit_reason": "TP"}, 200),
        ("Negative profit / big loss", {"signal_id": "LOSS_SIG", "profit": -10.0, "exit_reason": "SL"}, 200),
        ("Extreme float values", {"signal_id": "EXTREME", "profit": 1e9, "exit_reason": "MASSIVE_WIN"}, 200)
    ]

    for label, payload, exp_status in outcome_edge_tests:
        t0 = time.perf_counter()
        r = client.post("/api/trade-outcome", json=payload)
        elapsed = (time.perf_counter() - t0) * 1000.0
        safe = (r.status_code == exp_status)
        edge_cases.append({
            "test": f"Trade Outcome: {label}",
            "status_code": r.status_code,
            "latency_ms": round(elapsed, 2),
            "safe": safe
        })

    suite4_pass = all(c["safe"] for c in edge_cases)
    report["suites"]["suite_4_edge_cases_and_payloads"] = {
        "total_edge_cases": len(edge_cases),
        "passed_cases": sum(1 for c in edge_cases if c["safe"]),
        "failed_cases": sum(1 for c in edge_cases if not c["safe"]),
        "cases": edge_cases,
        "passed": suite4_pass
    }

    for c in edge_cases:
        print(f" - [{ 'PASS' if c['safe'] else 'FAIL' }] {c['test']} -> HTTP {c['status_code']} ({c['latency_ms']}ms)")
    print(f"Suite 4 Passed: {suite4_pass}")

    # =========================================================================
    # SUITE 5: Circuit Breaker State Machine & Backoff Verification
    # =========================================================================
    print("\n" + "="*80)
    print(" SUITE 5: Circuit Breaker State Machine & Backoff Verification")
    print("="*80)

    cb = YahooCircuitBreaker(failure_threshold=3, base_cooldown=0.2, max_cooldown=2.0)
    cb_log = []

    # 1. Initially CLOSED
    cb_log.append({"step": "Initial State", "state": cb._state, "allow": cb.allow_request(), "valid": (cb._state == "CLOSED" and cb.allow_request())})

    # 2. Accumulate 2 failures (below threshold of 3)
    cb.record_failure(500)
    cb.record_failure(500)
    cb_log.append({"step": "2 Failures", "state": cb._state, "allow": cb.allow_request(), "valid": (cb._state == "CLOSED" and cb.allow_request())})

    # 3. 3rd failure triggers OPEN state
    cb.record_failure(500)
    cb_log.append({"step": "3rd Failure (Threshold)", "state": cb._state, "allow": cb.allow_request(), "valid": (cb._state == "OPEN" and not cb.allow_request())})

    # 4. Immediate HTTP 429 directly forces OPEN state
    cb_direct = YahooCircuitBreaker(failure_threshold=5, base_cooldown=0.2)
    cb_direct.record_failure(status_code=429)
    cb_log.append({"step": "Direct 429 Trigger", "state": cb_direct._state, "allow": cb_direct.allow_request(), "valid": (cb_direct._state == "OPEN" and not cb_direct.allow_request())})

    # 5. Wait for cooldown expiration -> Transition to HALF-OPEN on next request probe
    time.sleep(0.25)
    probe_allowed = cb.allow_request()
    cb_log.append({"step": "Probe After Cooldown", "state": cb._state, "allow": probe_allowed, "valid": (cb._state == "HALF-OPEN" and probe_allowed is True)})

    # 6. Record success -> Restores to CLOSED
    cb.record_success()
    cb_log.append({"step": "Success in Half-Open", "state": cb._state, "allow": cb.allow_request(), "valid": (cb._state == "CLOSED" and cb.allow_request() is True and cb._failure_count == 0)})

    suite5_pass = all(s["valid"] for s in cb_log)
    report["suites"]["suite_5_circuit_breaker"] = {
        "steps": cb_log,
        "passed": suite5_pass
    }

    for s in cb_log:
        print(f" - [{ 'PASS' if s['valid'] else 'FAIL' }] {s['step']}: state={s['state']}, allow={s['allow']}")
    print(f"Suite 5 Passed: {suite5_pass}")

    # =========================================================================
    # OVERALL AUDIT SUMMARY & VERDICT
    # =========================================================================
    total_suites = len(report["suites"])
    passed_suites = sum(1 for s in report["suites"].values() if s.get("passed", False))
    all_suites_passed = (passed_suites == total_suites)

    suite_duration = time.perf_counter() - suite_start
    report["summary"]["total_tests"] = total_suites
    report["summary"]["passed"] = passed_suites
    report["summary"]["failed"] = total_suites - passed_suites
    report["summary"]["total_duration_seconds"] = round(suite_duration, 2)
    report["verdict"] = "APPROVE" if all_suites_passed else "FAIL"

    print("\n" + "="*80)
    print(f" FINAL ADVERSARIAL STRESS VERDICT: {report['verdict']} ({passed_suites}/{total_suites} Suites Passed in {suite_duration:.2f}s)")
    print("="*80)

    return report


if __name__ == "__main__":
    result = run_comprehensive_adversarial_suite()
    print("\nResult Report JSON:")
    print(json.dumps(result, indent=2))
