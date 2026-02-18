# Folder: firetiger-demo/agent/steps/characterize.py
#
# Step 1 of 5: Characterize the regression.
# Pure data collection - NO Claude API call here.
# We want to know WHAT is happening before asking WHY.
#
# Output: Characterization object with all the facts.

import logging
from datetime import datetime, timedelta
from ingestion.event_schema import RegressionEvent, Characterization
from storage.hot_store import HotStore

logger = logging.getLogger(__name__)


def characterize(regression: RegressionEvent, 
                 hot_store: HotStore) -> Characterization:
    """
    Build a complete picture of the anomaly using only data queries.
    No Claude involved - this is just facts.
    
    Key questions answered:
    - Is it just this one endpoint or all endpoints? (infra vs code issue)
    - Which specific users are affected?
    - When exactly did it start?
    - What changed in the metrics (latency, queries, memory)?
    """
    logger.info(f"[Step 1/5] Characterizing regression on {regression.affected_endpoint}")
    
    endpoint = regression.affected_endpoint
    commit_sha = regression.commit_sha
    
    # ─── Check if other endpoints are also affected ───────────────────────
    # If YES: probably infra issue (server overload, DB down)
    # If NO:  probably code issue in this specific endpoint
    all_endpoints = hot_store.get_all_endpoints()
    other_endpoints_anomalous = []
    
    for ep in all_endpoints:
        if ep == endpoint:
            continue
        other_latency = hot_store.get_recent_latency(ep, minutes=3)
        other_baseline_latency = hot_store.get_recent_latency(ep, minutes=20)
        
        if other_baseline_latency > 0:
            ratio = other_latency / other_baseline_latency
            if ratio > 2.0:  # Also 2x slower
                other_endpoints_anomalous.append(ep)
    
    all_endpoints_affected = len(other_endpoints_anomalous) > 0
    
    # ─── Get stats BEFORE the suspect commit ──────────────────────────────
    before_stats = hot_store.get_stats_before_commit(endpoint, commit_sha)
    
    # ─── Get CURRENT stats (since the new commit appeared) ────────────────
    current_latency = hot_store.get_recent_latency(endpoint, minutes=3)
    current_trend = hot_store.get_query_count_trend(endpoint)
    current_queries = current_trend[-1]["avg_queries"] if current_trend else 0
    current_db_time = hot_store.get_recent_latency(endpoint, minutes=3)
    
    # ─── Find when regression started ─────────────────────────────────────
    # It started when we first saw the new commit SHA
    regression_start = datetime.now() - timedelta(minutes=15)  # Approximate
    
    # ─── Get affected users ───────────────────────────────────────────────
    affected_users = hot_store.get_affected_users(
        endpoint=endpoint,
        since=regression_start,
        latency_threshold_ms=before_stats["avg_latency"] * 2 
                             if before_stats["avg_latency"] > 0 else 100
    )
    
    # ─── Compute multipliers for the agent to reason about ────────────────
    latency_multiplier = (
        current_latency / before_stats["avg_latency"] 
        if before_stats["avg_latency"] > 0 else 1.0
    )
    query_multiplier = (
        current_queries / before_stats["avg_queries"]
        if before_stats["avg_queries"] > 0 else 1.0
    )
    
    char = Characterization(
        affected_endpoint=endpoint,
        all_endpoints_affected=all_endpoints_affected,
        affected_user_ids=affected_users,
        regression_start_time=regression_start,
        commit_sha=commit_sha,
        
        latency_before_ms=before_stats["avg_latency"],
        latency_after_ms=current_latency,
        latency_multiplier=round(latency_multiplier, 1),
        
        query_count_before=before_stats["avg_queries"],
        query_count_after=current_queries,
        query_multiplier=round(query_multiplier, 1),
        
        db_time_before_ms=before_stats["avg_db_time"],
        db_time_after_ms=current_db_time,
        
        memory_before_mb=before_stats["avg_memory"],
        memory_after_mb=before_stats["avg_memory"]  # simplified
    )
    
    logger.info(
        f"[Step 1/5] Complete | "
        f"Latency: {char.latency_before_ms:.1f}ms → {char.latency_after_ms:.1f}ms "
        f"({char.latency_multiplier}x) | "
        f"Queries: {char.query_count_before:.0f} → {char.query_count_after:.0f} "
        f"({char.query_multiplier}x) | "
        f"All endpoints affected: {all_endpoints_affected}"
    )
    
    return char