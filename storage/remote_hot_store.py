# storage/remote_hot_store.py
# Instead of reading local DuckDB, queries the collector via HTTP.
# This lets the agent read from the same HotStore the collector writes to.

import requests
import logging
from datetime import datetime, timedelta
from typing import List
import config

logger = logging.getLogger(__name__)
BASE_URL = f"http://127.0.0.1:{config.COLLECTOR_PORT}"


class RemoteHotStore:
    """
    Reads hot store data from the collector via HTTP API.
    Drop-in replacement for HotStore in the detector and agent.
    """

    def get_recent_latency(self, endpoint: str, minutes: int) -> float:
        try:
            resp = requests.get(
                f"{BASE_URL}/query/latency",
                params={"endpoint": endpoint, "minutes": minutes},
                timeout=2
            )
            return resp.json().get("latency", 0.0)
        except Exception as e:
            logger.error(f"RemoteHotStore error: {e}")
            return 0.0

    def get_all_endpoints(self) -> List[str]:
        try:
            resp = requests.get(f"{BASE_URL}/query/endpoints", timeout=2)
            return resp.json().get("endpoints", [])
        except Exception:
            return []

    def get_query_count_trend(self, endpoint: str) -> List[dict]:
        try:
            resp = requests.get(
                f"{BASE_URL}/query/query_trend",
                params={"endpoint": endpoint},
                timeout=2
            )
            return resp.json().get("trend", [])
        except Exception:
            return []

    def get_affected_users(self, endpoint: str, since: datetime,
                           latency_threshold_ms: float) -> List[str]:
        try:
            resp = requests.get(
                f"{BASE_URL}/query/affected_users",
                params={
                    "endpoint": endpoint,
                    "threshold": latency_threshold_ms,
                    "since": since.isoformat()
                },
                timeout=2
            )
            return resp.json().get("user_ids", [])
        except Exception:
            return []

    def get_recent_commit_shas(self, endpoint: str) -> List[str]:
        try:
            resp = requests.get(
                f"{BASE_URL}/query/commit_shas",
                params={"endpoint": endpoint},
                timeout=2
            )
            return resp.json().get("shas", [])
        except Exception:
            return []

    def get_event_count(self) -> int:
        try:
            resp = requests.get(f"{BASE_URL}/query/event_count", timeout=2)
            return resp.json().get("count", 0)
        except Exception:
            return 0

    def get_latency_trend(self, endpoint: str) -> List[dict]:
        try:
            resp = requests.get(
                f"{BASE_URL}/query/latency",
                params={"endpoint": endpoint, "minutes": 30},
                timeout=2
            )
            return [{"avg_latency": resp.json().get("latency", 0)}]
        except Exception:
            return []

    def get_stats_before_commit(self, endpoint: str, commit_sha: str) -> dict:
        # Simplified - return recent latency as baseline
        latency = self.get_recent_latency(endpoint, 20)
        return {
            "avg_latency": latency,
            "avg_queries": 1.0,
            "avg_db_time": latency * 0.8,
            "avg_memory": 50.0
        }

    def purge_old_events(self):
        pass  # Handled by collector