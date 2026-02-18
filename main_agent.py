# Root folder: firetiger-demo/main_agent.py
#
# Starts everything:
# 1. Initializes all storage layers
# 2. Starts collector subprocess
# 3. Starts detector loop
# 4. Wires everything together

import logging
import os
import subprocess
import sys
import time
import threading
import schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/agent.log")
    ]
)

logger = logging.getLogger(__name__)

# ── Ensure directories exist ──────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
os.makedirs("data/events", exist_ok=True)


def main():
    logger.info("="*60)
    logger.info("🔥 FIRETIGER AGENT STARTING")
    logger.info("="*60)
    
    # ── Initialize storage ────────────────────────────────────────────────
    from storage.hot_store import HotStore
    from storage.cold_store import ColdStore
    from storage.knowledge_graph import KnowledgeGraph
    
    hot_store = HotStore()
    cold_store = ColdStore()
    knowledge_graph = KnowledgeGraph()
    
    logger.info("✅ Storage initialized")
    
    # ── Initialize action handler ─────────────────────────────────────────
    from actions.action_handler import ActionHandler
    action_handler = ActionHandler(hot_store, knowledge_graph)
    
    # ── Initialize orchestrator ───────────────────────────────────────────
    from agent.orchestrator import AgentOrchestrator
    orchestrator = AgentOrchestrator(
        hot_store=hot_store,
        knowledge_graph=knowledge_graph,
        action_handler=action_handler
    )
    
    # ── Initialize detector ───────────────────────────────────────────────
    from detection.detector import Detector
    detector = Detector(
        hot_store=hot_store,
        knowledge_graph=knowledge_graph,
        on_regression=orchestrator.investigate
    )
    
    # Wire detector back into action handler for mark_resolved
    action_handler.detector = detector
    
    logger.info("✅ Agent components initialized")
    
    # ── Start collector subprocess ────────────────────────────────────────
    collector_proc = subprocess.Popen(
        [sys.executable, "-m", "ingestion.collector"],
        stdout=open("logs/collector.log", "a"),
        stderr=subprocess.STDOUT
    )
    logger.info(f"✅ Collector started (PID: {collector_proc.pid})")
    time.sleep(2)  # Wait for collector to be ready
    
    # ── Start detector ────────────────────────────────────────────────────
    detector.start()
    logger.info("✅ Detector started")
    
    # ── Schedule background tasks ─────────────────────────────────────────
    def recompute_baselines():
        """Recompute baselines hourly as more data accumulates"""
        from detection.baseline import BaselineEngine
        engine = BaselineEngine(cold_store, knowledge_graph)
        for endpoint in ["/checkout", "/products", "/health"]:
            try:
                engine.compute_baseline(endpoint)
            except Exception as e:
                logger.warning(f"Baseline computation failed for {endpoint}: {e}")
    
    schedule.every(1).hours.do(recompute_baselines)
    
    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(30)
    
    threading.Thread(target=run_scheduler, daemon=True).start()
    
    logger.info("\n" + "="*60)
    logger.info("🟢 ALL SYSTEMS RUNNING")
    logger.info("   App:       http://localhost:5000")
    logger.info("   Collector: http://localhost:8001")
    logger.info("   Dashboard: run 'streamlit run dashboard/app.py'")
    logger.info("   Logs:      tail -f logs/agent.log")
    logger.info("="*60 + "\n")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        detector.stop()
        collector_proc.terminate()


if __name__ == "__main__":
    main()