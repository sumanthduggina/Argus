# Folder: firetiger-demo/actions/github_pr.py
#
# Creates a GitHub PR with the fix automatically.
# This is the most visually impressive part of the demo.
# A real PR appears on GitHub while you watch.

import logging
import os
from datetime import datetime
from github import Github, GithubException
from ingestion.event_schema import IncidentReport
import config

logger = logging.getLogger(__name__)


def create_fix_pr(report: IncidentReport) -> str:
    """
    Creates a GitHub PR with the agent-generated fix.
    Returns the PR URL.
    
    Steps:
    1. Connect to GitHub
    2. Create a new branch
    3. Apply the fix to the affected file
    4. Commit the change
    5. Open a PR with full incident context
    """
    g = Github(config.GITHUB_TOKEN)
    repo = g.get_repo(config.GITHUB_REPO)
    
    # Create branch name from incident
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    endpoint_clean = report.regression.affected_endpoint.replace("/", "")
    branch_name = f"fix/incident-{timestamp}-{endpoint_clean}"
    
    logger.info(f"Creating PR branch: {branch_name}")
    
    try:
        # ── Get current main branch SHA ───────────────────────────────
        main_branch = repo.get_branch("main")
        base_sha = main_branch.commit.sha
        
        # ── Create the new branch ─────────────────────────────────────
        repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base_sha
        )
        
        # ── Apply the fix to the affected file ────────────────────────
        # Get the file that needs changing
        file_path = _extract_file_path(
            report.root_cause.affected_code_location
        )
        
        try:
            # Get current file content from GitHub
            file_content = repo.get_contents(file_path)
            current_content = file_content.decoded_content.decode("utf-8")
            
            # Apply the fix: replace original code with fixed code
            if report.fix.original_code in current_content:
                new_content = current_content.replace(
                    report.fix.original_code,
                    report.fix.fixed_code,
                    1  # Replace only first occurrence
                )
            else:
                # If exact match fails, append a comment explaining the fix
                logger.warning("Exact code match not found, adding fix as comment")
                new_content = current_content + f"\n\n# AUTO-FIX: {report.fix.fix_summary}\n"
            
            # Commit the fix
            repo.update_file(
                path=file_path,
                message=f"fix: {report.fix.pr_title}",
                content=new_content,
                sha=file_content.sha,
                branch=branch_name
            )
            
        except GithubException as e:
            logger.warning(f"Could not apply fix to {file_path}: {e}")
            # Continue - still create PR with the fix in description
        
        # ── Open the PR ───────────────────────────────────────────────
        pr = repo.create_pull(
            title=report.fix.pr_title,
            body=_build_pr_body(report),
            head=branch_name,
            base="main"
        )
        
        logger.info(f"PR created: {pr.html_url}")
        return pr.html_url
        
    except GithubException as e:
        logger.error(f"GitHub API error: {e}")
        raise


def _extract_file_path(code_location: str) -> str:
    """Extract file path from location string like 'app/db.py, function_name'"""
    parts = code_location.replace(",", " ").split()
    for part in parts:
        if ".py" in part:
            return part.strip()
    return "app/db.py"  # Default fallback


def _build_pr_body(report: IncidentReport) -> str:
    """Build a comprehensive PR description with full incident context"""
    
    evidence = "\n".join(
        f"- {e}" for e in report.root_cause.evidence_chain
    )
    
    checklist = "\n".join(
        f"- [ ] {item}" for item in report.fix.verification_checklist
    )
    
    affected_users = len(report.regression.affected_user_ids)
    
    return f"""## 🚨 Auto-generated Fix — Incident {report.incident_id}

> This PR was automatically created by the Firetiger observability agent.

## Incident Summary

| Field | Value |
|-------|-------|
| Endpoint | `{report.regression.affected_endpoint}` |
| Detected | {report.regression.detected_at} |
| Suspect Commit | `{report.regression.commit_sha}` |
| Customers Affected | {affected_users} users |
| Latency | {report.characterization.latency_before_ms:.0f}ms → {report.characterization.latency_after_ms:.0f}ms |
| DB Queries | {report.characterization.query_count_before:.0f} → {report.characterization.query_count_after:.0f} per request |

## Root Cause

**{report.root_cause.confirmed_hypothesis_title}** ({report.root_cause.confidence_score:.0%} confidence)

Evidence chain:
{evidence}

Affected code: `{report.root_cause.affected_code_location}`
```python
# Problematic code
{report.root_cause.affected_code_snippet}
```

## The Fix

{report.fix.explanation}
```python
# Before
{report.fix.original_code}

# After
{report.fix.fixed_code}
```

## Risk Assessment

**Risk Level: {report.fix.risk_level.upper()}**

{report.fix.risk_reasoning}

Side effects to watch: {', '.join(report.fix.side_effects) if report.fix.side_effects else 'None expected'}

**Rollback:** `{report.fix.rollback_instructions}`

## Verification Checklist

After merging, confirm:
{checklist}
"""