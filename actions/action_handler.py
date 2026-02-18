# Folder: firetiger-demo/actions/action_handler.py
#
# Coordinates all actions after investigation completes.
# Called by the orchestrator with the full IncidentReport.
#
# Decides: auto-deploy vs human review based on confidence + risk.

import logging
import threading
from ingestion.event_schema import IncidentReport, RegressionEvent
from actions.slack_notifier import (
    send_incident_alert, send_resolution_message, send_failure_alert
)
from actions.github_pr import create_fix_pr
from actions.deployer import should_auto_deploy, run_ci_check, apply_fix_and_restart
from actions.verifier import verify_fix
from storage.hot_store import HotStore
from storage.knowledge_graph import KnowledgeGraph
import config

logger = logging.getLogger(__name__)


class ActionHandler:
    
    def __init__(self, hot_store: HotStore, 
                 knowledge_graph: KnowledgeGraph,
                 detector=None):
        self.hot_store = hot_store
        self.kg = knowledge_graph
        self.detector = detector  # For calling mark_resolved after fix
    
    def handle(self, report: IncidentReport):
        """
        Called by orchestrator after investigation completes.
        Runs in background thread - doesn't block detection.
        """
        logger.info(f"Action handler starting for incident {report.incident_id}")
        
        pr_url = None
        
        # ── Step 1: Always create a PR ────────────────────────────────────
        try:
            pr_url = create_fix_pr(report)
            logger.info(f"PR created: {pr_url}")
        except Exception as e:
            logger.error(f"PR creation failed: {e}")
        
        # ── Step 2: Always send Slack alert ───────────────────────────────
        send_incident_alert(report, pr_url=pr_url)
        
        # ── Step 3: Decide auto-deploy vs wait for human ──────────────────
        if should_auto_deploy(report.fix, report.root_cause.confidence_score):
            # Run CI check first
            if run_ci_check():
                logger.info("CI passed - proceeding with auto-deploy")
                self._auto_deploy(report)
            else:
                logger.warning("CI failed - waiting for human review")
                # Slack already sent, human will review PR
        else:
            logger.info(
                f"Confidence {report.root_cause.confidence_score:.0%} or "
                f"risk {report.fix.risk_level} requires human review. "
                f"PR created, waiting for merge."
            )
    
    def _auto_deploy(self, report: IncidentReport):
        """Apply fix automatically and verify recovery"""
        
        success = apply_fix_and_restart(report.fix)
        
        if not success:
            logger.error("Auto-deploy failed")
            send_failure_alert(
                report.regression, 
                "App failed to restart after fix"
            )
            return
        
        # Start verifier in background
        def on_resolved(resolve_time):
            send_resolution_message(
                report.incident_id,
                report.regression.affected_endpoint,
                resolve_time
            )
            if self.detector:
                self.detector.mark_resolved(
                    report.regression.affected_endpoint
                )
        
        def on_failed():
            send_failure_alert(
                report.regression,
                "Fix deployed but latency did not recover"
            )
        
        threading.Thread(
            target=verify_fix,
            args=(
                report.regression.affected_endpoint,
                report.characterization.latency_before_ms,
                report.incident_id,
                self.hot_store,
                self.kg,
                on_resolved,
                on_failed
            ),
            daemon=True
        ).start()
    
    def handle_failure(self, regression: RegressionEvent, error: str):
        """Called when investigation itself fails"""
        send_failure_alert(regression, error)