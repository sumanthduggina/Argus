# Folder: firetiger-demo/detection/baseline.py
#
# Computes "normal" behavior for each endpoint.
# Reads historical Parquet data to establish baselines.
# Baselines are time-aware: 2pm Tuesday has different normal than 2am Sunday.

import logging
import statistics
from datetime import datetime
from typing import Optional
from storage.cold_store import ColdStore
from storage.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


class BaselineEngine:
    """
    Establishes what "normal" looks like for each endpoint.
    
    Without baselines, detector would fire on every traffic spike.
    With baselines, detector only fires when behavior is 
    statistically abnormal for that time of day.
    """
    
    def __init__(self, cold_store: ColdStore, knowledge_graph: KnowledgeGraph):
        self.cold_store = cold_store
        self.kg = knowledge_graph
    
    def compute_baseline(self, endpoint: str):
        """
        Reads 7 days of historical data and computes baselines
        grouped by hour_of_day and day_of_week.
        
        Called on startup and every hour.
        """
        logger.info(f"Computing baseline for {endpoint}")
        
        # Read 7 days of historical events
        historical = self.cold_store.read_historical(endpoint, hours_back=168)
        
        if len(historical) < 50:
            logger.warning(
                f"Not enough historical data for {endpoint} "
                f"({len(historical)} events). Using defaults."
            )
            self._set_default_baseline(endpoint)
            return
        
        # Group by hour and day of week
        groups = {}
        for event in historical:
            ts = datetime.fromisoformat(str(event["timestamp"]))
            key = (ts.hour, ts.weekday())
            
            if key not in groups:
                groups[key] = {"latencies": [], "query_counts": []}
            
            groups[key]["latencies"].append(event["latency_ms"])
            groups[key]["query_counts"].append(event["db_query_count"])
        
        # Compute stats for each time slot
        for (hour, day), data in groups.items():
            if len(data["latencies"]) < 5:
                continue
            
            latencies = sorted(data["latencies"])
            p95_index = int(len(latencies) * 0.95)
            
            self.kg.update_baseline(
                endpoint=endpoint,
                hour=hour,
                day_of_week=day,
                metrics={
                    "avg_latency_ms": statistics.mean(latencies),
                    "p95_latency_ms": latencies[p95_index],
                    "avg_query_count": statistics.mean(data["query_counts"]),
                    "sample_size": len(latencies)
                }
            )
        
        logger.info(f"Baseline updated for {endpoint}: "
                   f"{len(groups)} time slots")
    
    def get_current_baseline(self, endpoint: str) -> dict:
        """
        Get the baseline applicable RIGHT NOW for an endpoint.
        Looks up by current hour and day of week.
        Falls back to a simple default if no baseline exists.
        """
        now = datetime.now()
        baseline = self.kg.get_baseline(
            endpoint=endpoint,
            hour=now.hour,
            day_of_week=now.weekday()
        )
        
        if baseline:
            return baseline
        
        # No baseline yet - return conservative defaults
        # This happens on first run before data accumulates
        return {
            "avg_latency_ms": 50.0,
            "p95_latency_ms": 100.0,
            "avg_query_count": 3.0,
            "sample_size": 0
        }
    
    def _set_default_baseline(self, endpoint: str):
        """Set reasonable defaults when no historical data exists"""
        now = datetime.now()
        self.kg.update_baseline(
            endpoint=endpoint,
            hour=now.hour,
            day_of_week=now.weekday(),
            metrics={
                "avg_latency_ms": 50.0,
                "p95_latency_ms": 100.0,
                "avg_query_count": 3.0,
                "sample_size": 0
            }
        )