# Folder: firetiger-demo/app/middleware.py
#
# This is the auto-instrumentation layer.
# Wraps EVERY Flask request transparently.
# Routes don't need any changes - this captures everything automatically.
#
# Flow:
# Request arrives → before_request fires (start timer, reset counters)
# Route handler runs (DB queries tracked by db.py decorators)  
# after_request fires → build EventSchema → send to collector

import time
import psutil
import os
import uuid
import requests as http_requests
import logging
from flask import request, g
from datetime import datetime
from git import Repo
from ingestion.event_schema import EventSchema
import config

logger = logging.getLogger(__name__)

# Cache the git SHA so we don't call git on every single request
_cached_commit_sha = None


def get_current_commit_sha() -> str:
    """
    Gets the current git HEAD SHA.
    Cached after first call since it only changes on deploy.
    The post-commit hook clears this cache when new code is deployed.
    """
    global _cached_commit_sha
    
    if _cached_commit_sha is None:
        try:
            repo = Repo(".")
            _cached_commit_sha = repo.head.commit.hexsha[:8]
        except Exception:
            _cached_commit_sha = "unknown"
    
    return _cached_commit_sha


def clear_commit_cache():
    """Called by the post-commit hook after a new deploy"""
    global _cached_commit_sha
    _cached_commit_sha = None


def register_middleware(app):
    """
    Call this in your Flask app factory.
    Registers before/after request hooks on the app.
    """
    
    @app.before_request
    def before_request():
        """
        Runs before every route handler.
        Sets up timing and resets DB query counter.
        """
        # Store start time in flask's per-request context (g object)
        g.start_time = time.time()
        g.start_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        
        # Reset the DB query counter for this request
        from app.db import query_counter
        query_counter["count"] = 0
        query_counter["total_time_ms"] = 0.0
    
    @app.after_request
    def after_request(response):
        """
        Runs after every route handler.
        Builds EventSchema and sends to collector.
        """
        try:
            # Calculate how long the request took
            latency_ms = (time.time() - g.start_time) * 1000
            
            # Get memory usage change
            current_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
            
            # Read how many DB queries fired during this request
            from app.db import query_counter
            
            # Get user ID from header (our load script sends this)
            # Fall back to a random UUID if not provided
            user_id = request.headers.get("X-User-ID", str(uuid.uuid4()))
            session_id = request.headers.get("X-Session-ID", str(uuid.uuid4()))
            
            # Build the event - this is what flows through the entire system
            event = EventSchema(
                timestamp=datetime.now(),
                endpoint=request.path,
                method=request.method,
                status_code=response.status_code,
                latency_ms=round(latency_ms, 2),
                db_query_count=query_counter["count"],
                db_query_time_ms=round(query_counter["total_time_ms"], 2),
                user_id=user_id,
                session_id=session_id,
                memory_mb=round(current_memory, 2),
                commit_sha=get_current_commit_sha(),
                error_message=None
            )
            
            # Fire and forget - send to collector async
            # We don't want this to slow down the actual response
            send_event_to_collector(event)
            
        except Exception as e:
            # Never let instrumentation break the actual app
            logger.error(f"Middleware error: {e}")
        
        return response
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        """
        Captures errors and includes them in the event.
        This way the agent can investigate 500 errors too.
        """
        from app.db import query_counter
        latency_ms = (time.time() - g.start_time) * 1000
        
        event = EventSchema(
            timestamp=datetime.now(),
            endpoint=request.path,
            method=request.method,
            status_code=500,
            latency_ms=round(latency_ms, 2),
            db_query_count=query_counter["count"],
            db_query_time_ms=round(query_counter["total_time_ms"], 2),
            user_id=request.headers.get("X-User-ID", "unknown"),
            session_id=request.headers.get("X-Session-ID", "unknown"),
            memory_mb=0.0,
            commit_sha=get_current_commit_sha(),
            error_message=str(e)
        )
        
        send_event_to_collector(event)
        return {"error": "Internal server error"}, 500


def send_event_to_collector(event: EventSchema):
    """
    Sends the event to the collector service running on port 8001.
    Uses a short timeout so it never blocks the main app.
    """
    try:
        http_requests.post(
            f"http://localhost:{config.COLLECTOR_PORT}/ingest",
            json=event.model_dump(mode="json"),
            timeout=0.1   # 100ms timeout - drop it if collector is slow
        )
    except Exception:
        # Silently drop if collector is down
        # We never want instrumentation to break the app
        pass