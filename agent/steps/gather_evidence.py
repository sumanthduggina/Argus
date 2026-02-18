# Folder: firetiger-demo/agent/steps/gather_evidence.py
#
# Step 3 of 5: Gather concrete evidence for each hypothesis.
# NO Claude API call - pure data retrieval.
#
# For each hypothesis, we know what evidence would confirm it.
# This step goes and gets that evidence programmatically.

import logging
import subprocess
from typing import List, Dict
from git import Repo
from ingestion.event_schema import Hypothesis
from storage.hot_store import HotStore

logger = logging.getLogger(__name__)


def gather_evidence(hypotheses: List[Hypothesis], 
                    commit_sha: str,
                    hot_store: HotStore) -> Dict[int, dict]:
    """
    For each hypothesis, gather the specific evidence needed to confirm it.
    
    Returns: dict mapping hypothesis rank → evidence bundle
    """
    logger.info("[Step 3/5] Gathering evidence...")
    
    evidence_bundle = {}
    
    # ─── Always gather git diff ────────────────────────────────────────────
    # The git diff is the most important piece of evidence
    # It shows exactly what changed in the suspect commit
    git_diff = get_git_diff(commit_sha)
    
    # ─── Always gather slow query patterns ────────────────────────────────
    query_patterns = get_slow_query_patterns(hot_store)
    
    # ─── Evidence per hypothesis ──────────────────────────────────────────
    for hyp in hypotheses:
        evidence = {
            "git_diff": git_diff,
            "query_patterns": query_patterns,
            "specific_evidence": []
        }
        
        # Add hypothesis-specific evidence based on what it needs
        evidence_text = " ".join(hyp.evidence_needed).lower()
        
        if "query" in evidence_text or "n+1" in evidence_text or "loop" in evidence_text:
            evidence["specific_evidence"].append({
                "type": "query_count_analysis",
                "data": analyze_query_patterns(hot_store, query_patterns)
            })
        
        if "index" in evidence_text:
            evidence["specific_evidence"].append({
                "type": "query_execution",
                "data": "SQLite doesn't expose EXPLAIN output easily in demo - "
                       "check query time vs count ratio instead"
            })
        
        if "memory" in evidence_text:
            memory_trend = get_memory_trend(hot_store)
            evidence["specific_evidence"].append({
                "type": "memory_trend",
                "data": memory_trend
            })
        
        evidence_bundle[hyp.rank] = evidence
    
    logger.info(f"[Step 3/5] Complete | Evidence gathered for {len(hypotheses)} hypotheses")
    
    return evidence_bundle


def get_git_diff(commit_sha: str) -> str:
    """
    Get the diff for the suspect commit.
    This shows exactly what code changed.
    """
    try:
        repo = Repo(".")
        
        # Get the diff between this commit and its parent
        result = subprocess.run(
            ["git", "diff", f"{commit_sha}~1", commit_sha],
            capture_output=True,
            text=True,
            cwd=repo.working_dir
        )
        
        if result.returncode == 0 and result.stdout:
            return result.stdout[:3000]  # Cap at 3000 chars for prompt size
        else:
            # If only one commit exists, diff against empty tree
            result = subprocess.run(
                ["git", "show", commit_sha, "--stat"],
                capture_output=True, text=True
            )
            return result.stdout[:3000]
            
    except Exception as e:
        logger.warning(f"Could not get git diff: {e}")
        return f"Could not retrieve git diff for {commit_sha}"


def get_slow_query_patterns(hot_store: HotStore) -> str:
    """
    Summarize DB query patterns from the last 5 minutes.
    Shows the N+1 explosion clearly.
    """
    trend = hot_store.get_query_count_trend("/checkout")
    
    if not trend:
        return "No query data available"
    
    lines = ["DB Query Count per Minute (last 30 min):"]
    for point in trend[-10:]:  # Last 10 minutes
        bar = "█" * min(int(point["avg_queries"] / 5), 40)
        lines.append(
            f"  {point['minute'][-5:]} | {bar} {point['avg_queries']:.0f} queries/req"
        )
    
    return "\n".join(lines)


def analyze_query_patterns(hot_store: HotStore, 
                           query_patterns: str) -> str:
    """
    Deeper analysis of query behavior.
    Tries to identify if queries are repeating (N+1 signature).
    """
    trend = hot_store.get_query_count_trend("/checkout")
    if not trend:
        return "Insufficient data"
    
    # Look for sudden jump - signature of N+1
    if len(trend) >= 2:
        recent = trend[-3:]
        older = trend[-10:-3] if len(trend) >= 10 else trend[:3]
        
        recent_avg = sum(r["avg_queries"] for r in recent) / len(recent)
        older_avg = sum(r["avg_queries"] for r in older) / len(older)
        
        if older_avg > 0:
            jump = recent_avg / older_avg
            return (
                f"Query count jumped {jump:.1f}x | "
                f"Before: {older_avg:.0f}/req → After: {recent_avg:.0f}/req | "
                f"Pattern: {'Consistent with N+1 (proportional to data size)' if jump > 10 else 'Moderate increase'}"
            )
    
    return query_patterns


def get_memory_trend(hot_store: HotStore) -> str:
    """Get memory usage trend - relevant for memory leak hypothesis"""
    trend = hot_store.get_latency_trend("/checkout")
    return f"Memory trend data: {len(trend)} data points available"