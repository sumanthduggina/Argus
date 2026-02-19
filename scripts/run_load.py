# Folder: firetiger-demo/scripts/run_load.py
# Generates continuous realistic traffic.
# Run this BEFORE the demo to build up baseline data.
# Keep running throughout the demo.

import requests
import time
import random
import uuid
import statistics

# 50 fake user IDs that make requests repeatedly
USER_POOL = [str(uuid.uuid4()) for _ in range(50)]

# Track latencies for reporting
latency_history = {"checkout": [], "products": [], "health": []}
request_count = 0
start_time = time.time()


def make_request(endpoint: str, user_id: str):
    """Make one request and return latency"""
    try:
        start = time.time()
        response = requests.get(
            f"http://127.0.0.1:5000{endpoint}",
            headers={
                "X-User-ID": user_id,
                "X-Session-ID": f"sess-{user_id[:8]}"
            },
            timeout=10
        )
        elapsed_ms = (time.time() - start) * 1000
        return elapsed_ms, response.status_code
    except Exception:
        return None, 0


def print_stats():
    """Print rolling stats every 30 seconds"""
    global request_count
    
    runtime = time.time() - start_time
    
    print(f"\n{'─'*50}")
    print(f"Runtime: {runtime:.0f}s | Total requests: {request_count}")
    
    for endpoint, latencies in latency_history.items():
        if latencies:
            recent = latencies[-20:]  # Last 20 readings
            avg = statistics.mean(recent)
            
            # Visual indicator
            if avg < 50:
                indicator = "✅"
            elif avg < 200:
                indicator = "⚠️ "
            else:
                indicator = "🚨"
            
            print(f"{indicator} /{endpoint}: {avg:.1f}ms avg (last 20 requests)")
    
    print(f"{'─'*50}")


batch_counter = 0
while True:
    user_id = random.choice(USER_POOL)
    
    # Traffic mix: checkout most important, others less frequent
    endpoints_this_batch = [
        ("/checkout", 5),    # 5 checkout requests per batch
        ("/products", 3),    # 3 products requests
        ("/health", 1),      # 1 health check
    ]
    
    for endpoint, count in endpoints_this_batch:
        for _ in range(count):
            latency, status = make_request(endpoint, user_id)
            if latency:
                key = endpoint.strip("/")
                latency_history[key].append(latency)
                # Keep last 100 readings per endpoint
                if len(latency_history[key]) > 100:
                    latency_history[key] = latency_history[key][-100:]
                request_count += 1
    
    # Print stats every 30 seconds
    batch_counter += 1
    if batch_counter % 10 == 0:
        print_stats()
    
    time.sleep(random.uniform(0.8, 1.2))  # ~1 second between batches