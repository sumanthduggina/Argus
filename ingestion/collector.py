# Folder: firetiger-demo/ingestion/collector.py
#
# Separate Flask app running on port 8001.
# Receives events from the main app's middleware.
# Writes to hot store immediately.
# Flushes to cold store every 5 minutes.
#
# Why separate process?
# - Keeps instrumentation isolated from main app
# - Can restart independently
# - Mirrors real-world collector architecture (Datadog agent, etc.)

from flask import Flask, request, jsonify
from ingestion.event_schema import EventSchema
from storage.hot_store import HotStore
from storage.cold_store import ColdStore
import schedule
import threading
import logging
import time
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [COLLECTOR] %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Shared storage instances
hot_store = HotStore()
cold_store = ColdStore()

# Buffer events here before flushing to cold store
# Flushed every 5 minutes
_flush_buffer = []
_buffer_lock = threading.Lock()


@app.route("/ingest", methods=["POST"])
def ingest():
    """
    Main ingestion endpoint.
    Receives one EventSchema per request from the main app.
    
    Flow:
    1. Validate incoming JSON as EventSchema
    2. Write to hot store immediately (for real-time detection)
    3. Add to flush buffer (for cold store write later)
    """
    try:
        # Validate the incoming event matches our schema
        data = request.get_json()
        event = EventSchema(**data)
        
        # Write to hot store immediately - detector reads this
        hot_store.insert(event)
        
        # Add to buffer for cold store flush
        with _buffer_lock:
            _flush_buffer.append(event)
        
        logger.info(f"{event.endpoint} | {event.latency_ms}ms | "
                   f"{event.db_query_count} queries | {event.commit_sha}")
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.error(f"Ingest error: {e}")
        return jsonify({"error": str(e)}), 400


@app.route("/deploy", methods=["POST"])
def deploy_notification():
    """
    Called by post-commit hook when new code is deployed.
    Logs the deploy event so we can correlate it with regressions.
    """
    data = request.get_json()
    commit_sha = data.get("commit_sha", "unknown")
    logger.info(f"🚀 New deploy: {commit_sha}")
    
    # Log to a deploys file for the agent to read
    with open("deploys.log", "a") as f:
        f.write(f"{time.time()},{commit_sha}\n")
    
    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "hot_store_events": hot_store.get_event_count(),
        "buffer_size": len(_flush_buffer)
    })


def flush_to_cold_store():
    """
    Runs every 5 minutes.
    Takes everything in the buffer and writes to Parquet.
    Clears the buffer after writing.
    """
    global _flush_buffer
    
    with _buffer_lock:
        if not _flush_buffer:
            return
        
        to_flush = _flush_buffer.copy()
        _flush_buffer = []
    
    cold_store.flush(to_flush)
    logger.info(f"Flushed {len(to_flush)} events to cold store")


def purge_hot_store():
    """Runs every 5 minutes. Removes events older than 30 minutes."""
    hot_store.purge_old_events()


def run_scheduler():
    """Background thread running scheduled tasks"""
    schedule.every(5).minutes.do(flush_to_cold_store)
    schedule.every(5).minutes.do(purge_hot_store)
    
    while True:
        schedule.run_pending()
        time.sleep(10)


# Start scheduler in background thread when collector starts
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()
@app.route("/query/latency", methods=["GET"])
def query_latency():
    endpoint = request.args.get("endpoint", "/checkout")
    minutes = int(request.args.get("minutes", 5))
    result = hot_store.get_recent_latency(endpoint, minutes)
    return jsonify({"latency": result})

@app.route("/query/endpoints", methods=["GET"])
def query_endpoints():
    result = hot_store.get_all_endpoints()
    return jsonify({"endpoints": result})

@app.route("/query/query_trend", methods=["GET"])
def query_trend():
    endpoint = request.args.get("endpoint", "/checkout")
    result = hot_store.get_query_count_trend(endpoint)
    return jsonify({"trend": result})

@app.route("/query/affected_users", methods=["GET"])
def query_affected_users():
    endpoint = request.args.get("endpoint", "/checkout")
    threshold = float(request.args.get("threshold", 100))
    since_str = request.args.get("since")
    from datetime import datetime, timedelta
    since = datetime.fromisoformat(since_str) if since_str else datetime.now() - timedelta(minutes=10)
    result = hot_store.get_affected_users(endpoint, since, threshold)
    return jsonify({"user_ids": result})

@app.route("/query/commit_shas", methods=["GET"])
def query_commit_shas():
    endpoint = request.args.get("endpoint", "/checkout")
    result = hot_store.get_recent_commit_shas(endpoint)
    return jsonify({"shas": result})

@app.route("/query/event_count", methods=["GET"])
def query_event_count():
    return jsonify({"count": hot_store.get_event_count()})
if __name__ == "__main__":
    logger.info(f"Collector starting on port {config.COLLECTOR_PORT}")
    app.run(host="127.0.0.1", port=config.COLLECTOR_PORT, debug=False)