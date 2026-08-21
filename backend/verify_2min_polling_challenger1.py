"""
Empirical Challenger 1 Verification Suite
RUTE AI Trading Bot - 2-Minute Polling Verification for Decision Logs
Target: http://127.0.0.1:8001/api/market-data
"""

import sys
import os
import time
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Any

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_via_http_client(base_url="http://127.0.0.1:8001", duration_seconds=120, poll_interval=2.5):
    """
    Executes a 120-second live HTTP polling verification against a running server.
    """
    import urllib.request
    import urllib.error

    url = f"{base_url}/api/market-data"
    print(f"=== Starting 120-Second Live HTTP Polling Verification ===")
    print(f"Endpoint: {url}")
    print(f"Duration: {duration_seconds}s | Interval: {poll_interval}s")
    
    start_time = time.time()
    end_time = start_time + duration_seconds
    
    poll_records = []
    seen_event_signatures = set()
    timestamps_observed = []
    
    poll_count = 0
    failures = []
    
    while time.time() < end_time:
        poll_count += 1
        elapsed = round(time.time() - start_time, 2)
        t_req_start = time.perf_counter()
        
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "RUTE-Challenger1-Harness/1.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code = resp.getcode()
                raw_body = resp.read()
                latency_ms = round((time.perf_counter() - t_req_start) * 1000, 2)
                response_size = len(raw_body)
                
                if status_code != 200:
                    failures.append(f"Poll {poll_count} (T={elapsed}s): HTTP {status_code}")
                
                data = json.loads(raw_body.decode("utf-8"))
                events = data.get("events", [])
                
                if not isinstance(events, list):
                    failures.append(f"Poll {poll_count} (T={elapsed}s): 'events' is not a list")
                
                latest_ts = events[0].get("ts") if events else None
                latest_type = events[0].get("type") if events else None
                latest_msg = events[0].get("message", "")[:60] if events else ""
                
                for ev in events:
                    sig = f"{ev.get('ts')}_{ev.get('type')}_{ev.get('symbol')}"
                    seen_event_signatures.add(sig)
                
                if latest_ts:
                    timestamps_observed.append(latest_ts)
                
                record = {
                    "poll": poll_count,
                    "elapsed_sec": elapsed,
                    "timestamp": datetime.now().isoformat(),
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                    "response_size_bytes": response_size,
                    "events_count": len(events),
                    "distinct_events_cumulative": len(seen_event_signatures),
                    "latest_event_ts": latest_ts,
                    "latest_event_type": latest_type,
                    "latest_event_msg": latest_msg
                }
                poll_records.append(record)
                
                print(f"[{elapsed:5.1f}s | #{poll_count:02d}] HTTP {status_code} | Latency: {latency_ms:5.1f}ms | Size: {response_size:5d}B | Events: {len(events):2d} (Distinct: {len(seen_event_signatures):2d}) | Latest: {latest_type} @ {latest_ts}")
                
        except Exception as e:
            latency_ms = round((time.perf_counter() - t_req_start) * 1000, 2)
            failures.append(f"Poll {poll_count} (T={elapsed}s): Exception {str(e)}")
            print(f"[{elapsed:5.1f}s | #{poll_count:02d}] ERROR: {e}")
        
        time.sleep(poll_interval)
    
    return evaluate_results(poll_records, failures, start_time, duration_seconds)


def test_via_in_process_lifespan(duration_seconds=120, poll_interval=2.5):
    """
    Executes a 120-second in-process lifespan test with the autonomous background scanner
    and FastAPI TestClient, actively verifying advancing timestamps across the full duration.
    """
    from fastapi.testclient import TestClient
    from main import app, SCAN_LOG
    
    print(f"=== Starting 120-Second In-Process Lifespan Verification ===")
    print(f"Duration: {duration_seconds}s | Interval: {poll_interval}s")
    
    poll_records = []
    seen_event_signatures = set()
    timestamps_observed = []
    failures = []
    
    # Use TestClient as context manager to invoke FastAPI lifespan
    with TestClient(app) as client:
        start_time = time.time()
        end_time = start_time + duration_seconds
        poll_count = 0
        
        while time.time() < end_time:
            poll_count += 1
            elapsed = round(time.time() - start_time, 2)
            t_req_start = time.perf_counter()
            
            # Alternate GET and POST to verify both endpoint contracts
            if poll_count % 3 == 0:
                resp = client.post("/api/market-data", json={"symbols": ["EURUSD=X", "BTC-USD"]})
                method = "POST"
            else:
                resp = client.get("/api/market-data")
                method = "GET"
                
            latency_ms = round((time.perf_counter() - t_req_start) * 1000, 2)
            status_code = resp.status_code
            raw_body = resp.content
            response_size = len(raw_body)
            
            if status_code != 200:
                failures.append(f"Poll {poll_count} ({method} T={elapsed}s): HTTP {status_code}")
                
            data = resp.json()
            events = data.get("events", [])
            
            if not isinstance(events, list):
                failures.append(f"Poll {poll_count} (T={elapsed}s): 'events' is not a list")
                
            latest_ts = events[0].get("ts") if events else None
            latest_type = events[0].get("type") if events else None
            latest_msg = events[0].get("message", "")[:60] if events else ""
            
            for ev in events:
                sig = f"{ev.get('ts')}_{ev.get('type')}_{ev.get('symbol')}"
                seen_event_signatures.add(sig)
                
            if latest_ts:
                timestamps_observed.append(latest_ts)
                
            record = {
                "poll": poll_count,
                "method": method,
                "elapsed_sec": elapsed,
                "timestamp": datetime.now().isoformat(),
                "status_code": status_code,
                "latency_ms": latency_ms,
                "response_size_bytes": response_size,
                "events_count": len(events),
                "distinct_events_cumulative": len(seen_event_signatures),
                "latest_event_ts": latest_ts,
                "latest_event_type": latest_type,
                "latest_event_msg": latest_msg
            }
            poll_records.append(record)
            
            print(f"[{elapsed:5.1f}s | #{poll_count:02d} {method}] HTTP {status_code} | Latency: {latency_ms:5.1f}ms | Size: {response_size:5d}B | Events: {len(events):2d} (Distinct: {len(seen_event_signatures):2d}) | Latest: {latest_type} @ {latest_ts}")
            
            time.sleep(poll_interval)
            
    return evaluate_results(poll_records, failures, start_time, duration_seconds)


def evaluate_results(poll_records: List[Dict], failures: List[str], start_time: float, duration_seconds: float) -> Dict[str, Any]:
    total_polls = len(poll_records)
    if total_polls == 0:
        return {"verdict": "FAIL", "reason": "No polls completed", "failures": failures}
        
    status_codes = [r["status_code"] for r in poll_records]
    latencies = [r["latency_ms"] for r in poll_records]
    response_sizes = [r["response_size_bytes"] for r in poll_records]
    event_counts = [r["events_count"] for r in poll_records]
    latest_timestamps = [r["latest_event_ts"] for r in poll_records if r["latest_event_ts"]]
    
    # Assertions
    all_200 = all(code == 200 for code in status_codes)
    events_present_always = all(c > 0 for c in event_counts)
    
    # Check timestamp monotonicity and advancement
    parsed_ts = []
    for ts_str in latest_timestamps:
        try:
            parsed_ts.append(datetime.fromisoformat(ts_str))
        except Exception:
            pass
            
    timestamps_advancing = False
    if len(parsed_ts) >= 2:
        t_first = parsed_ts[0]
        t_last = parsed_ts[-1]
        time_delta_seconds = (t_last - t_first).total_seconds()
        timestamps_advancing = time_delta_seconds > 0
    else:
        time_delta_seconds = 0
        
    # Check for strict non-decreasing order of latest event timestamp over time
    is_monotonic = True
    for i in range(1, len(parsed_ts)):
        if parsed_ts[i] < parsed_ts[i-1]:
            is_monotonic = False
            failures.append(f"Timestamp regressed at poll {i}: {parsed_ts[i]} < {parsed_ts[i-1]}")
            
    distinct_events_total = poll_records[-1]["distinct_events_cumulative"] if poll_records else 0
    
    verdict = "APPROVE" if (all_200 and events_present_always and timestamps_advancing and is_monotonic and len(failures) == 0) else "FAIL"
    
    summary = {
        "verdict": verdict,
        "test_duration_actual_sec": round(time.time() - start_time, 2),
        "total_polls": total_polls,
        "all_status_200": all_200,
        "events_present_always": events_present_always,
        "timestamps_advancing": timestamps_advancing,
        "timestamp_span_seconds": time_delta_seconds,
        "is_monotonic": is_monotonic,
        "first_event_timestamp": latest_timestamps[0] if latest_timestamps else None,
        "last_event_timestamp": latest_timestamps[-1] if latest_timestamps else None,
        "distinct_events_observed": distinct_events_total,
        "latency_stats_ms": {
            "min": min(latencies) if latencies else 0,
            "max": max(latencies) if latencies else 0,
            "avg": round(sum(latencies) / len(latencies), 2) if latencies else 0
        },
        "response_size_bytes": {
            "min": min(response_sizes) if response_sizes else 0,
            "max": max(response_sizes) if response_sizes else 0,
            "avg": round(sum(response_sizes) / len(response_sizes), 2) if response_sizes else 0
        },
        "failures": failures,
        "poll_records": poll_records
    }
    
    return summary


def main():
    import urllib.request
    server_alive = False
    try:
        req = urllib.request.Request("http://127.0.0.1:8001/", headers={"User-Agent": "Probe"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.getcode() == 200:
                server_alive = True
    except Exception:
        server_alive = False
        
    if server_alive:
        print("Detected active server at http://127.0.0.1:8001! Running live HTTP verification.")
        summary = test_via_http_client(duration_seconds=120, poll_interval=2.5)
    else:
        print("No server on 127.0.0.1:8001 detected. Running in-process lifespan verification.")
        summary = test_via_in_process_lifespan(duration_seconds=120, poll_interval=2.5)
        
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "challenger1_2min_verification_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        
    print(f"\n================ VERIFICATION SUMMARY ================")
    print(f"VERDICT: {summary['verdict']}")
    print(f"Total Polls: {summary['total_polls']} in {summary['test_duration_actual_sec']}s")
    print(f"HTTP Status 200: {summary['all_status_200']}")
    print(f"Events Present: {summary['events_present_always']}")
    print(f"Timestamps Advancing: {summary['timestamps_advancing']} (Span: {summary['timestamp_span_seconds']}s)")
    print(f"Distinct Events Generated: {summary['distinct_events_observed']}")
    print(f"Latency (avg): {summary['latency_stats_ms']['avg']}ms (min: {summary['latency_stats_ms']['min']}ms, max: {summary['latency_stats_ms']['max']}ms)")
    print(f"Report saved to: {out_path}")
    print(f"======================================================\n")


if __name__ == "__main__":
    main()
