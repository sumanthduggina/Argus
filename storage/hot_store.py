# Folder: firetiger-demo/storage/hot_store.py
#
# DuckDB in-memory store for the last 30 minutes of events.
# This is what the detector queries constantly.
# Fast analytical queries on recent data.
#
# Think of this as the "live view" of what's happening right now.

import duckdb
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from ingestion.event_schema import EventSchema
import config

logger = logging.getLogger(__name__)


class HotStore:
    """
    In-memory DuckDB database holding last 30 minutes of events.
    
    Why DuckDB?
    - Columnar storage = fast aggregation queries
    - In-memory = no disk I/O latency
    - SQL interface = easy to write detection queries
    - Perfect for "average latency in last 5 minutes" type queries
    """
    
    def __init__(self):
        # In-memory DuckDB - data lives only while process is running
        self.conn = duckdb.connect(":memory:")
        self._create_table()
        logger.info("HotStore initialized")
    
    def _create_table(self):
        """
        Create the events table matching EventSchema exactly.
        Every field in EventSchema becomes a column here.
        """
        self.conn.execute("""
            CREATE TABLE events (
                timestamp        TIMESTAMP,
                endpoint         VARCHAR,
                method           VARCHAR,
                status_code      INTEGER,
                latency_ms       DOUBLE,
                db_query_count   INTEGER,
                db_query_time_ms DOUBLE,
                user_id          VARCHAR,
                session_id       VARCHAR,
                memory_mb        DOUBLE,
                commit_sha       VARCHAR,
                error_message    VARCHAR
            )
        """)
    
    def insert(self, event: EventSchema):
        """
        Insert one event. Called by collector for every request.
        This is the hot path - needs to be fast.
        """
        self.conn.execute("""
            INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            event.timestamp,
            event.endpoint,
            event.method,
            event.status_code,
            event.latency_ms,
            event.db_query_count,
            event.db_query_time_ms,
            event.user_id,
            event.session_id,
            event.memory_mb,
            event.commit_sha,
            event.error_message
        ])
    
    def get_recent_latency(self, endpoint: str, minutes: int) -> float:
        """
        Average latency for an endpoint in the last N minutes.
        Used by detector to compare current vs baseline.
        """
        result = self.conn.execute("""
            SELECT AVG(latency_ms) as avg_latency
            FROM events
            WHERE endpoint = ?
              AND timestamp > NOW() - INTERVAL (?) MINUTE
              AND status_code < 500
        """, [endpoint, minutes]).fetchone()
        
        return result[0] if result[0] else 0.0
    
    def get_latency_trend(self, endpoint: str) -> List[dict]:
        """
        Latency per minute for the last 30 minutes.
        Used by detector for trend analysis and dashboard charting.
        
        Returns list of: {minute, avg_latency, p95_latency, request_count}
        """
        rows = self.conn.execute("""
            SELECT 
                DATE_TRUNC('minute', timestamp) as minute,
                AVG(latency_ms) as avg_latency,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency,
                COUNT(*) as request_count
            FROM events
            WHERE endpoint = ?
              AND timestamp > NOW() - INTERVAL 30 MINUTE
            GROUP BY DATE_TRUNC('minute', timestamp)
            ORDER BY minute ASC
        """, [endpoint]).fetchall()
        
        return [
            {
                "minute": str(r[0]),
                "avg_latency": round(r[1], 2),
                "p95_latency": round(r[2], 2),
                "request_count": r[3]
            }
            for r in rows
        ]
    
    def get_query_count_trend(self, endpoint: str) -> List[dict]:
        """
        DB query count per minute for last 30 minutes.
        Key signal for N+1 detection - sudden jump = new loop added.
        """
        rows = self.conn.execute("""
            SELECT 
                DATE_TRUNC('minute', timestamp) as minute,
                AVG(db_query_count) as avg_queries,
                MAX(db_query_count) as max_queries
            FROM events
            WHERE endpoint = ?
              AND timestamp > NOW() - INTERVAL 30 MINUTE
            GROUP BY DATE_TRUNC('minute', timestamp)
            ORDER BY minute ASC
        """, [endpoint]).fetchall()
        
        return [
            {
                "minute": str(r[0]),
                "avg_queries": round(r[1], 1),
                "max_queries": r[2]
            }
            for r in rows
        ]
    
    def get_affected_users(self, endpoint: str, since: datetime, 
                           latency_threshold_ms: float) -> List[str]:
        """
        Which specific user IDs are experiencing slow responses.
        This is the customer-level tracking Firetiger emphasizes.
        """
        rows = self.conn.execute("""
            SELECT DISTINCT user_id
            FROM events
            WHERE endpoint = ?
              AND timestamp > ?
              AND latency_ms > ?
        """, [endpoint, since, latency_threshold_ms]).fetchall()
        
        return [r[0] for r in rows]
    
    def get_recent_commit_shas(self, endpoint: str) -> List[str]:
        """
        Recent commit SHAs seen in events, newest first.
        Used to identify which deploy introduced a regression.
        A new SHA appearing = a deploy happened.
        """
        rows = self.conn.execute("""
            SELECT DISTINCT commit_sha, MIN(timestamp) as first_seen
            FROM events
            WHERE endpoint = ?
              AND timestamp > NOW() - INTERVAL 30 MINUTE
            GROUP BY commit_sha
            ORDER BY first_seen DESC
        """, [endpoint]).fetchall()
        
        return [r[0] for r in rows]
    
    def get_stats_before_commit(self, endpoint: str, 
                                 commit_sha: str) -> dict:
        """
        Gets baseline stats from BEFORE a specific commit appeared.
        Used by characterize step to establish the "before" picture.
        """
        result = self.conn.execute("""
            SELECT 
                AVG(latency_ms) as avg_latency,
                AVG(db_query_count) as avg_queries,
                AVG(db_query_time_ms) as avg_db_time,
                AVG(memory_mb) as avg_memory
            FROM events
            WHERE endpoint = ?
              AND commit_sha != ?
              AND timestamp > NOW() - INTERVAL 30 MINUTE
        """, [endpoint, commit_sha]).fetchone()
        
        return {
            "avg_latency": result[0] or 0.0,
            "avg_queries": result[1] or 0.0,
            "avg_db_time": result[2] or 0.0,
            "avg_memory": result[3] or 0.0
        }
    
    def get_all_endpoints(self) -> List[str]:
        """All endpoints seen in last 30 minutes"""
        rows = self.conn.execute("""
            SELECT DISTINCT endpoint 
            FROM events 
            WHERE timestamp > NOW() - INTERVAL 30 MINUTE
        """).fetchall()
        return [r[0] for r in rows]
    
    def purge_old_events(self):
        """
        Delete events older than HOT_STORE_WINDOW_MIN.
        Called every 5 minutes to keep memory usage bounded.
        """
        deleted = self.conn.execute("""
            DELETE FROM events 
            WHERE timestamp < NOW() - INTERVAL (?) MINUTE
        """, [config.HOT_STORE_WINDOW_MIN]).rowcount
        
        if deleted > 0:
            logger.info(f"Purged {deleted} old events from hot store")
    
    def get_event_count(self) -> int:
        """Total events currently in hot store"""
        return self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]