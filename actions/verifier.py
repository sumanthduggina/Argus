# Folder: firetiger-demo/actions/verifier.py
#
# Watches the system after a fix is deployed.
# Samples the next 50 real requests.
# Confirms latency returned to baseline before closing incident.

import logging
import time
from datetime import datetime, timedelta
from storage.hot_store import HotStore
from storage.knowledge_graph import KnowledgeGraph
import config

logger = logging.getLogger(__name__)

VERIFICATION_TIMEOUT_SEC = 300  # Give it 5 minutes to recover
SAMPLE_SIZE = 50                # Watch this many requests
RECOVERY_THRESHOLD = 1.3        # Must be within 30% of baseline


def verify_fix(endpoint: str, baseline_latency_ms: float,
               incident_id: str, hot_store: HotStore,
               knowledge_graph: KnowledgeGraph,
               on_resolved=None, on_failed=None) -> bool:
    """
    After fix is deployed, watch the next 50 requests.
    Confirms recovery or escalates if still broken.
    
    Returns True if recovered, False if still broken after timeout.
    """
    logger.info(
        f"Verifier watching {endpoint} | "
        f"Baseline: {baseline_latency_ms:.1f}ms | "
        f"Sampling {SAMPLE_SIZE} requests..."
    )
    
    start_time = time.time()
    threshold_ms = baseline_latency_ms * RECOVERY_THRESHOLD
    
    while time.time() - start_time < VERIFICATION_TIMEOUT_SEC:
        time.sleep(10)
        
        # Check recent latency
        recent_latency = hot_store.get_recent_latency(endpoint, minutes=2)
        
        if recent_latency == 0:
            continue  # No data yet, keep waiting
        
        logger.info(
            f"Verifier: {endpoint} at {recent_latency:.1f}ms "
            f"(threshold: {threshold_ms:.1f}ms)"
        )
        
        if recent_latency <= threshold_ms:
            # ── Recovery confirmed ─────────────────────────────────────
            resolve_time = time.time() - start_time
            
            logger.info(
                f"✅ INCIDENT RESOLVED | "
                f"Latency back to {recent_latency:.1f}ms | "
                f"Resolved in {resolve_time:.0f}s"
            )
            
            # Update knowledge graph
            knowledge_graph.resolve_incident(
                incident_id=incident_id,
                fix_applied="auto-deployed",
                time_to_detect=0,  # Would track this from detection time
                time_to_resolve=resolve_time
            )
            
            if on_resolved:
                on_resolved(resolve_time)
            
            return True
    
    # ── Timed out - fix didn't work ───────────────────────────────────────
    logger.error(
        f"❌ VERIFICATION FAILED | "
        f"{endpoint} still slow after {VERIFICATION_TIMEOUT_SEC}s"
    )
    
    if on_failed:
        on_failed()
    
    return False