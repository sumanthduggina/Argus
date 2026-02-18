# Folder: firetiger-demo/agent/orchestrator.py
#
# The brain that coordinates all 5 agent steps.
# Called by the detector when a regression is confirmed.
# Runs steps sequentially, each building on the last.
#
# Flow:
# RegressionEvent → characterize → hypothesize → gather_evidence
#                → confirm → generate_fix → IncidentReport → actions

import logging
import time
from datetime import datetime
from ingestion.event_schema import RegressionEvent, IncidentReport
from agent.steps.characterize import characterize
from agent.steps.hypothesize import hypothesize
from agent.steps.gather_evidence import gather_evidence
from agent.steps.confirm import confirm_root_cause
from agent.steps.fix import generate_fix
from storage.hot_store import HotStore
from storage.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Coordinates the 5-step investigation pipeline.
    
    Each step receives the output of the previous step.
    If any step fails, the incident is logged and humans are notified.
    """
    
    def __init__(self, hot_store: HotStore, 
                 knowledge_graph: KnowledgeGraph,
                 action_handler=None):
        
        self.hot_store = hot_store
        self.kg = knowledge_graph
        # action_handler will call Slack, GitHub PR, etc.
        self.action_handler = action_handler
    
    def investigate(self, regression: RegressionEvent):
        """
        Main entry point. Called by detector.
        Runs all 5 steps and produces an IncidentReport.
        """
        start_time = time.time()
        
        logger.info(
            f"\n{'='*60}\n"
            f"🔍 INVESTIGATION STARTED\n"
            f"Incident: {regression.incident_id}\n"
            f"Endpoint: {regression.affected_endpoint}\n"
            f"Commit:   {regression.commit_sha}\n"
            f"{'='*60}"
        )
        
        # Save incident to knowledge graph immediately
        self.kg.save_incident({
            "incident_id": regression.incident_id,
            "endpoint": regression.affected_endpoint,
            "started_at": regression.detected_at.isoformat(),
            "commit_sha": regression.commit_sha,
            "affected_user_count": len(regression.affected_user_ids)
        })
        
        try:
            # ── Step 1: What is happening? ─────────────────────────────
            step_start = time.time()
            char = characterize(regression, self.hot_store)
            logger.info(f"Step 1 took {time.time()-step_start:.1f}s")
            
            # ── Step 2: Why might it be happening? ────────────────────
            step_start = time.time()
            hypotheses = hypothesize(char, self.kg)
            logger.info(f"Step 2 took {time.time()-step_start:.1f}s")
            
            # ── Step 3: Gather evidence for each hypothesis ───────────
            step_start = time.time()
            evidence = gather_evidence(
                hypotheses, regression.commit_sha, self.hot_store
            )
            logger.info(f"Step 3 took {time.time()-step_start:.1f}s")
            
            # ── Step 4: Confirm which hypothesis is correct ───────────
            step_start = time.time()
            root_cause = confirm_root_cause(hypotheses, evidence)
            logger.info(f"Step 4 took {time.time()-step_start:.1f}s")
            
            # ── Step 5: Generate the fix ──────────────────────────────
            step_start = time.time()
            fix = generate_fix(root_cause, char)
            logger.info(f"Step 5 took {time.time()-step_start:.1f}s")
            
            # ── Build final report ────────────────────────────────────
            total_time = time.time() - start_time
            report = IncidentReport(
                incident_id=regression.incident_id,
                regression=regression,
                characterization=char,
                hypotheses=hypotheses,
                root_cause=root_cause,
                fix=fix
            )
            
            logger.info(
                f"\n{'='*60}\n"
                f"✅ INVESTIGATION COMPLETE in {total_time:.1f}s\n"
                f"Root cause: {root_cause.confirmed_hypothesis_title}\n"
                f"Confidence: {root_cause.confidence_score:.0%}\n"
                f"Fix risk:   {fix.risk_level}\n"
                f"{'='*60}"
            )
            
            # ── Trigger action layer ──────────────────────────────────
            if self.action_handler:
                self.action_handler.handle(report)
            
            return report
            
        except Exception as e:
            logger.error(f"Investigation failed: {e}", exc_info=True)
            # Notify humans that automated investigation failed
            if self.action_handler:
                self.action_handler.handle_failure(regression, str(e))
            raise