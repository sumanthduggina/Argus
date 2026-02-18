# Folder: firetiger-demo/storage/knowledge_graph.py
#
# SQLite database that accumulates wisdom over time.
# Three tables: baselines, incidents, patterns
#
# This is what makes the agent smarter over time.
# First incident: no context, agent starts from scratch.
# Second similar incident: agent sees the pattern, 
#   confirms faster, more confident fix.

import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, List
import config

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """
    Persistent memory of past incidents and learned patterns.
    
    Baselines: "checkout normally runs in 12ms between 2-4pm"
    Incidents: "last time checkout was slow it was N+1, fixed in 4 min"
    Patterns:  "commits touching db.py have caused 3 N+1 incidents"
    """
    
    def __init__(self):
        self.conn = sqlite3.connect(config.KNOWLEDGE_DB_PATH, 
                                     check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info("KnowledgeGraph initialized")
    
    def _create_tables(self):
        """Create all three tables if they don't exist"""
        
        self.conn.executescript("""
            -- Normal performance for each endpoint by time of day
            -- Used to compute anomaly score in detector
            CREATE TABLE IF NOT EXISTS baselines (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint        TEXT NOT NULL,
                hour_of_day     INTEGER NOT NULL,   -- 0-23
                day_of_week     INTEGER NOT NULL,   -- 0=Monday, 6=Sunday
                avg_latency_ms  REAL NOT NULL,
                p95_latency_ms  REAL NOT NULL,
                avg_query_count REAL NOT NULL,
                sample_size     INTEGER NOT NULL,
                last_updated    TEXT NOT NULL,
                UNIQUE(endpoint, hour_of_day, day_of_week)
            );
            
            -- Full record of every incident
            -- Agent reads this to see if it's seen this before
            CREATE TABLE IF NOT EXISTS incidents (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id             TEXT UNIQUE,
                endpoint                TEXT NOT NULL,
                started_at              TEXT NOT NULL,
                resolved_at             TEXT,
                root_cause              TEXT,           -- e.g. "N+1 Query"
                fix_applied             TEXT,           -- the actual fix code
                confidence_score        REAL,
                affected_user_count     INTEGER,
                time_to_detect_sec      REAL,
                time_to_resolve_sec     REAL,
                commit_sha              TEXT,
                resolved                INTEGER DEFAULT 0   -- 0=no, 1=yes
            );
            
            -- Patterns learned about specific files
            -- "db.py changes often cause N+1 issues"
            CREATE TABLE IF NOT EXISTS patterns (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path       TEXT UNIQUE NOT NULL,
                incident_count  INTEGER DEFAULT 0,
                common_root_cause TEXT,
                common_fix      TEXT,
                last_seen       TEXT
            );
        """)
        self.conn.commit()
    
    def get_baseline(self, endpoint: str, hour: int, 
                     day_of_week: int) -> Optional[dict]:
        """
        Get normal performance for an endpoint at a specific time.
        Returns None if no baseline established yet.
        """
        row = self.conn.execute("""
            SELECT * FROM baselines
            WHERE endpoint = ? AND hour_of_day = ? AND day_of_week = ?
        """, [endpoint, hour, day_of_week]).fetchone()
        
        return dict(row) if row else None
    
    def update_baseline(self, endpoint: str, hour: int, 
                        day_of_week: int, metrics: dict):
        """
        Update or create baseline for an endpoint/time combination.
        Called hourly by baseline engine.
        """
        self.conn.execute("""
            INSERT INTO baselines 
                (endpoint, hour_of_day, day_of_week, avg_latency_ms, 
                 p95_latency_ms, avg_query_count, sample_size, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(endpoint, hour_of_day, day_of_week) 
            DO UPDATE SET
                avg_latency_ms  = excluded.avg_latency_ms,
                p95_latency_ms  = excluded.p95_latency_ms,
                avg_query_count = excluded.avg_query_count,
                sample_size     = excluded.sample_size,
                last_updated    = excluded.last_updated
        """, [
            endpoint, hour, day_of_week,
            metrics["avg_latency_ms"],
            metrics["p95_latency_ms"],
            metrics["avg_query_count"],
            metrics["sample_size"],
            datetime.now().isoformat()
        ])
        self.conn.commit()
    
    def get_similar_incidents(self, endpoint: str) -> List[dict]:
        """
        Past incidents on the same endpoint.
        Agent uses this to say "I've seen this before, it was probably X"
        """
        rows = self.conn.execute("""
            SELECT * FROM incidents
            WHERE endpoint = ? AND resolved = 1
            ORDER BY started_at DESC
            LIMIT 5
        """, [endpoint]).fetchall()
        
        return [dict(r) for r in rows]
    
    def get_patterns_for_files(self, file_paths: List[str]) -> List[dict]:
        """
        Check if changed files have caused incidents before.
        If db.py has caused 3 N+1 issues, that's a strong signal.
        """
        placeholders = ",".join(["?" for _ in file_paths])
        rows = self.conn.execute(f"""
            SELECT * FROM patterns
            WHERE file_path IN ({placeholders})
            ORDER BY incident_count DESC
        """, file_paths).fetchall()
        
        return [dict(r) for r in rows]
    
    def save_incident(self, incident_data: dict) -> int:
        """Save a new incident record. Returns the incident ID."""
        cursor = self.conn.execute("""
            INSERT INTO incidents 
                (incident_id, endpoint, started_at, root_cause, 
                 confidence_score, affected_user_count, commit_sha)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            incident_data["incident_id"],
            incident_data["endpoint"],
            incident_data["started_at"],
            incident_data.get("root_cause"),
            incident_data.get("confidence_score"),
            incident_data.get("affected_user_count", 0),
            incident_data.get("commit_sha")
        ])
        self.conn.commit()
        return cursor.lastrowid
    
    def resolve_incident(self, incident_id: str, fix_applied: str,
                          time_to_detect: float, time_to_resolve: float):
        """Mark an incident as resolved with timing data"""
        self.conn.execute("""
            UPDATE incidents SET
                resolved = 1,
                resolved_at = ?,
                fix_applied = ?,
                time_to_detect_sec = ?,
                time_to_resolve_sec = ?
            WHERE incident_id = ?
        """, [
            datetime.now().isoformat(),
            fix_applied,
            time_to_detect,
            time_to_resolve,
            incident_id
        ])
        self.conn.commit()
    
    def update_pattern(self, file_path: str, root_cause: str, fix: str):
        """
        Update or create a pattern for a file.
        Called after each resolved incident.
        """
        self.conn.execute("""
            INSERT INTO patterns 
                (file_path, incident_count, common_root_cause, common_fix, last_seen)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                incident_count    = incident_count + 1,
                common_root_cause = excluded.common_root_cause,
                common_fix        = excluded.common_fix,
                last_seen         = excluded.last_seen
        """, [
            file_path, root_cause, fix, datetime.now().isoformat()
        ])
        self.conn.commit()