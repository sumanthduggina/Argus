# Folder: firetiger-demo/detection/detector.py
#
# The watchdog that runs every 10 seconds.
# Compares current metrics to baseline.
# Fires the agent when something looks wrong.
#
# Uses "3 strikes" rule to avoid false alarms:
# One slow second could be a fluke.
# Three consecutive slow readings = something is wrong.

import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Callable
from storage.hot_store import HotStore
from storage.knowledge_graph import KnowledgeGraph
from detection.baseline import BaselineEngine
from ingestion.event_schema import RegressionEvent
import config

logger = logging.getLogger(__name__)


class Detector:
    """
    Continuously monitors all endpoints for regressions.
    
    When a regression is confirmed (3 strikes), builds a RegressionEvent
    and calls the provided callback (which triggers the agent).
    """
    
    def __init__(self, hot_store: HotStore, 
                 knowledge_graph: KnowledgeGraph,
                 on_regression: Callable[[RegressionEvent], None]):
        
        self.hot_store = hot_store
        self.kg = knowledge_graph
        self.baseline_engine = BaselineEngine(
            # BaselineEngine needs cold store for historical data
            # We pass a lazy accessor here
            cold_store=None,  
            knowledge_graph=knowledge_graph
        )
        
        # Callback fired when regression confirmed
        # This will be agent_orchestrator.investigate()
        self.on_regression = on_regression
        
        # Track consecutive anomalous readings per endpoint
        # Format: {endpoint: strike_count}
        self.strikes: Dict[str, int] = {}
        
        # Track which endpoints are currently under investigation
        # Don't fire agent twice for same incident
        self.active_incidents: set = set()
        
        self.running = False
    
    def start(self):
        """Start the detection loop in a background thread"""
        self.running = True
        thread = threading.Thread(target=self._detection_loop, daemon=True)
        thread.start()
        logger.info("Detector started")
    
    def stop(self):
        self.running = False
    
    def mark_resolved(self, endpoint: str):
        """
        Called by verifier when an incident is confirmed resolved.
        Re-enables detection for this endpoint.
        """
        self.active_incidents.discard(endpoint)
        self.strikes[endpoint] = 0
        logger.info(f"Detection re-enabled for {endpoint}")
    
    def _detection_loop(self):
        """
        Main loop - runs every DETECTION_INTERVAL_SEC seconds.
        Checks all known endpoints.
        """
        while self.running:
            try:
                endpoints = self.hot_store.get_all_endpoints()
                
                for endpoint in endpoints:
                    # Skip endpoints currently being investigated
                    if endpoint in self.active_incidents:
                        continue
                    
                    self._check_endpoint(endpoint)
                    
            except Exception as e:
                logger.error(f"Detection loop error: {e}")
            
            time.sleep(config.DETECTION_INTERVAL_SEC)
    
    def _check_endpoint(self, endpoint: str):
        """
        Check one endpoint for anomalies.
        Implements the 3-strikes rule.
        """
        # Get current metrics (last 3 minutes average)
        current_latency = self.hot_store.get_recent_latency(endpoint, minutes=3)
        current_queries = self._get_current_query_avg(endpoint, minutes=3)
        
        if current_latency == 0:
            return  # No data yet
        
        # Get what's normal for this time of day
        baseline = self.baseline_engine.get_current_baseline(endpoint)
        baseline_latency = baseline["avg_latency_ms"]
        baseline_queries = baseline["avg_query_count"]
        
        # Compute anomaly scores
        # How many standard deviations away from normal?
        latency_anomaly = self._compute_anomaly_score(
            current_latency, baseline_latency
        )
        query_anomaly = self._compute_anomaly_score(
            current_queries, baseline_queries
        )
        
        # Take the worse of the two signals
        anomaly_score = max(latency_anomaly, query_anomaly)
        
        logger.debug(
            f"{endpoint} | latency: {current_latency:.1f}ms "
            f"(baseline: {baseline_latency:.1f}ms) | "
            f"score: {anomaly_score:.1f}"
        )
        
        if anomaly_score > config.ANOMALY_THRESHOLD:
            # This reading looks bad - add a strike
            self.strikes[endpoint] = self.strikes.get(endpoint, 0) + 1
            logger.warning(
                f"⚠️  {endpoint} anomaly score {anomaly_score:.1f} | "
                f"strike {self.strikes[endpoint]}/{config.CONSECUTIVE_STRIKES}"
            )
            
            # 3 strikes = confirmed regression, fire the agent
            if self.strikes[endpoint] >= config.CONSECUTIVE_STRIKES:
                self._fire_regression(
                    endpoint, anomaly_score,
                    current_latency, baseline_latency,
                    current_queries, baseline_queries
                )
        else:
            # Reading is normal - reset strikes
            if self.strikes.get(endpoint, 0) > 0:
                logger.info(f"✅ {endpoint} back to normal")
            self.strikes[endpoint] = 0
    
    def _fire_regression(self, endpoint: str, anomaly_score: float,
                          latency_after: float, latency_before: float,
                          queries_after: float, queries_before: float):
        """
        Confirmed regression - build RegressionEvent and call agent.
        """
        logger.error(
            f"🚨 REGRESSION CONFIRMED: {endpoint} | "
            f"score: {anomaly_score:.1f} | "
            f"latency: {latency_before:.1f}ms → {latency_after:.1f}ms"
        )
        
        # Mark as active to prevent duplicate investigations
        self.active_incidents.add(endpoint)
        self.strikes[endpoint] = 0
        
        # Get which users are affected
        affected_users = self.hot_store.get_affected_users(
            endpoint=endpoint,
            since=datetime.now() - timedelta(minutes=5),
            latency_threshold_ms=latency_before * 2
        )
        
        # Get the suspect commit
        recent_shas = self.hot_store.get_recent_commit_shas(endpoint)
        commit_sha = recent_shas[0] if recent_shas else "unknown"
        
        # Build the regression event for the agent
        regression = RegressionEvent(
            affected_endpoint=endpoint,
            anomaly_score=anomaly_score,
            latency_before_ms=latency_before,
            latency_after_ms=latency_after,
            query_count_before=queries_before,
            query_count_after=queries_after,
            commit_sha=commit_sha,
            affected_user_ids=affected_users[:50]  # cap at 50 for prompt size
        )
        
        # Fire callback in a separate thread so detector keeps running
        thread = threading.Thread(
            target=self.on_regression,
            args=(regression,),
            daemon=True
        )
        thread.start()
    
    def _get_current_query_avg(self, endpoint: str, minutes: int) -> float:
        """Get average DB query count per request for last N minutes"""
        trend = self.hot_store.get_query_count_trend(endpoint)
        if not trend:
            return 0.0
        recent = trend[-minutes:] if len(trend) >= minutes else trend
        return sum(r["avg_queries"] for r in recent) / len(recent)
    
    def _compute_anomaly_score(self, current: float, baseline: float) -> float:
        """
        Compute how anomalous current value is relative to baseline.
        Simple ratio-based scoring.
        Returns multiplier: 3.0 means 3x worse than normal.
        """
        if baseline == 0:
            return 0.0
        return current / baseline