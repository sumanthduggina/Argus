# app/middleware.py - Simplified version with no blocking calls

import threading
import logging
import time
import uuid
import http.client
import json
import subprocess
from flask import request, g
from datetime import datetime
from ingestion.event_schema import EventSchema
import config

logger = logging.getLogger(__name__)

# Cache commit SHA - only read git once
_commit_sha = None

def get_commit_sha():
    global _commit_sha
    if _commit_sha is None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=2
            )
            _commit_sha = result.stdout.strip() or "unknown"
        except Exception:
            _commit_sha = "unknown"
    return _commit_sha

def clear_commit_cache():
    global _commit_sha
    _commit_sha = None

def register_middleware(app):

    @app.before_request
    def before_request():
        g.start_time = time.time()
        from app.db import query_counter
        query_counter["count"] = 0
        query_counter["total_time_ms"] = 0.0

    @app.after_request
    def after_request(response):
        try:
            latency_ms = (time.time() - g.start_time) * 1000
            from app.db import query_counter

            event = {
                "timestamp": datetime.now().isoformat(),
                "endpoint": request.path,
                "method": request.method,
                "status_code": response.status_code,
                "latency_ms": round(latency_ms, 2),
                "db_query_count": query_counter["count"],
                "db_query_time_ms": round(query_counter["total_time_ms"], 2),
                "user_id": request.headers.get("X-User-ID", str(uuid.uuid4())),
                "session_id": request.headers.get("X-Session-ID", "default"),
                "memory_mb": 0.0,
                "commit_sha": get_commit_sha(),
                "error_message": None
            }

            # Fire and forget in background thread
            threading.Thread(
                target=_send,
                args=(event,),
                daemon=True
            ).start()

        except Exception as e:
            logger.error(f"Middleware error: {e}")

        return response


def _send(event_data: dict):
    """Non-blocking send using raw http.client"""
    try:
        body = json.dumps(event_data, default=str)
        conn = http.client.HTTPConnection(
            "127.0.0.1",
            config.COLLECTOR_PORT,
            timeout=1
        )
        conn.request(
            "POST",
            "/ingest",
            body=body,
            headers={"Content-Type": "application/json"}
        )
        conn.getresponse()
        conn.close()
    except Exception:
        pass