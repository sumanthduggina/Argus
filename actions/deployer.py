# Folder: firetiger-demo/actions/deployer.py
#
# Automatically applies the fix and restarts the app.
# This closes the loop - no human needed to deploy.
#
# Only runs if:
# 1. Confidence score > AUTO_MERGE_CONFIDENCE (0.92)
# 2. Risk level is "low"
# 3. Fake CI checks pass

import logging
import os
import time
import subprocess
import requests
from ingestion.event_schema import FixPackage
import config

logger = logging.getLogger(__name__)

# PID file so we can kill and restart the Flask app
APP_PID_FILE = "app.pid"


def should_auto_deploy(fix: FixPackage, confidence: float) -> bool:
    """
    Gate that determines if it's safe to auto-deploy.
    All three conditions must be true.
    """
    conditions = {
        "confidence_high": confidence >= config.AUTO_MERGE_CONFIDENCE,
        "risk_low":        fix.risk_level == "low",
        "no_side_effects": len(fix.side_effects) == 0
    }
    
    failed = [k for k, v in conditions.items() if not v]
    
    if failed:
        logger.info(
            f"Auto-deploy blocked: {', '.join(failed)} | "
            f"Confidence: {confidence:.0%} | Risk: {fix.risk_level}"
        )
        return False
    
    logger.info("Auto-deploy conditions met ✅")
    return True


def run_ci_check() -> bool:
    """
    Fake CI: make 20 test requests and verify latency is acceptable.
    Returns True if app looks healthy, False if still broken.
    """
    logger.info("Running CI check (20 test requests)...")
    
    latencies = []
    errors = 0
    
    for i in range(20):
        try:
            start = time.time()
            resp = requests.get(
                f"http://localhost:{config.APP_PORT}/checkout",
                timeout=5
            )
            elapsed_ms = (time.time() - start) * 1000
            latencies.append(elapsed_ms)
            
            if resp.status_code >= 500:
                errors += 1
                
        except Exception:
            errors += 1
        
        time.sleep(0.2)
    
    if not latencies:
        logger.error("CI check: no responses received")
        return False
    
    avg_latency = sum(latencies) / len(latencies)
    error_rate = errors / 20
    
    passed = avg_latency < 200 and error_rate < 0.05
    
    logger.info(
        f"CI check: avg_latency={avg_latency:.1f}ms | "
        f"errors={errors}/20 | "
        f"{'✅ PASSED' if passed else '❌ FAILED'}"
    )
    
    return passed


def apply_fix_and_restart(fix: FixPackage, file_path: str = "app/db.py") -> bool:
    """
    Apply the code fix directly and restart the Flask app.
    Returns True if app comes back healthy.
    """
    logger.info(f"Applying fix to {file_path}...")
    
    # ── Read current file ─────────────────────────────────────────────────
    with open(file_path, "r") as f:
        current_content = f.read()
    
    # ── Apply the fix ─────────────────────────────────────────────────────
    if fix.original_code not in current_content:
        logger.error("Cannot apply fix: original code not found in file")
        return False
    
    new_content = current_content.replace(fix.original_code, fix.fixed_code, 1)
    
    with open(file_path, "w") as f:
        f.write(new_content)
    
    logger.info("Fix written to file ✅")
    
    # ── Commit the fix ────────────────────────────────────────────────────
    subprocess.run(["git", "add", file_path])
    subprocess.run([
        "git", "commit", "-m",
        f"fix: auto-applied by Firetiger agent - {fix.fix_summary}"
    ])
    
    # Clear commit SHA cache so new events get tagged with new SHA
    from app.middleware import clear_commit_cache
    clear_commit_cache()
    
    # ── Restart Flask app ─────────────────────────────────────────────────
    logger.info("Restarting Flask app...")
    
    # Kill existing process
    if os.path.exists(APP_PID_FILE):
        with open(APP_PID_FILE, "r") as f:
            old_pid = int(f.read().strip())
        try:
            os.kill(old_pid, 15)  # SIGTERM
            time.sleep(2)
        except ProcessLookupError:
            pass
    
    # Start new process
    proc = subprocess.Popen(
        ["python", "-m", "app.main"],
        stdout=open("logs/app.log", "a"),
        stderr=subprocess.STDOUT
    )
    
    with open(APP_PID_FILE, "w") as f:
        f.write(str(proc.pid))
    
    # Wait for app to come up
    logger.info("Waiting for app to restart...")
    for _ in range(10):
        time.sleep(2)
        try:
            resp = requests.get(
                f"http://localhost:{config.APP_PORT}/health",
                timeout=2
            )
            if resp.status_code == 200:
                logger.info("App restarted successfully ✅")
                return True
        except Exception:
            pass
    
    logger.error("App did not restart in time ❌")
    return False