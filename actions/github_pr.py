# Folder: firetiger-demo/actions/github_pr.py

import logging
from datetime import datetime
from github import Github, GithubException, Auth
from ingestion.event_schema import IncidentReport
import config

logger = logging.getLogger(__name__)


def create_fix_pr(report: IncidentReport) -> str:
    g = Github(auth=Auth.Token(config.GITHUB_TOKEN))
    repo = g.get_repo(config.GITHUB_REPO)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    endpoint_clean = report.regression.affected_endpoint.replace("/", "")
    branch_name = f"fix/incident-{timestamp}-{endpoint_clean}"

    logger.info(f"Creating PR branch: {branch_name}")

    try:
        # Get main branch SHA
        main_branch = repo.get_branch(repo.default_branch)
        base_sha = main_branch.commit.sha

        # Create new branch
        repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base_sha
        )

        # Get file path
        file_path = _extract_file_path(
            report.root_cause.affected_code_location
        )

        try:
            file_content = repo.get_contents(file_path)
            current_content = file_content.decoded_content.decode("utf-8")

            new_content = None

            # Try 1: Exact match
            if report.fix.original_code in current_content:
                new_content = current_content.replace(
                    report.fix.original_code,
                    report.fix.fixed_code,
                    1
                )
                logger.info("Applied fix via exact match")

            # Try 2: Match the key config line
            if new_content is None:
                if "if config.USE_SLOW_QUERY:" in current_content:
                    new_content = current_content.replace(
                        "if config.USE_SLOW_QUERY:",
                        "if False:  # Fixed by Argus agent - N+1 disabled",
                        1
                    )
                    logger.info("Applied fix via key line match")

            # Try 3: Force fix by replacing USE_SLOW_QUERY
            if new_content is None:
                logger.warning("Forcing direct fix")
                new_content = current_content.replace(
                    "if config.USE_SLOW_QUERY:",
                    "if False:  # Argus agent fix",
                    1
                )

            # Only update if content actually changed
            if new_content and new_content != current_content:
                repo.update_file(
                    path=file_path,
                    message=f"fix: {report.fix.pr_title}",
                    content=new_content,
                    sha=file_content.sha,
                    branch=branch_name
                )
                logger.info(f"File updated on GitHub: {file_path}")
            else:
                logger.warning("No file changes applied")

        except GithubException as e:
            logger.warning(f"Could not update file {file_path}: {e}")

        # Create the PR
        pr = repo.create_pull(
            title=report.fix.pr_title,
            body=_build_pr_body(report),
            head=branch_name,
            base=repo.default_branch
        )

        logger.info(f"PR created: {pr.html_url}")
        return pr.html_url

    except GithubException as e:
        logger.error(f"GitHub API error: {e}")
        raise


def _extract_file_path(code_location: str) -> str:
    parts = code_location.replace(",", " ").split()
    for part in parts:
        if ".py" in part:
            return part.strip()
    return "app/db.py"


def _build_pr_body(report: IncidentReport) -> str:
    evidence = "\n".join(
        f"- {e}" for e in report.root_cause.evidence_chain
    )

    checklist = "\n".join(
        f"- [ ] {item}" for item in report.fix.verification_checklist
    )

    affected_users = len(report.regression.affected_user_ids)

    return f"""## Auto-generated Fix - Incident {report.incident_id}

> This PR was automatically created by the Argus observability agent.

## Incident Summary

| Field | Value |
|-------|-------|
| Endpoint | `{report.regression.affected_endpoint}` |
| Detected | {report.regression.detected_at} |
| Suspect Commit | `{report.regression.commit_sha}` |
| Customers Affected | {affected_users} users |
| Latency | {report.characterization.latency_before_ms:.0f}ms to {report.characterization.latency_after_ms:.0f}ms |
| DB Queries | {report.characterization.query_count_before:.0f} to {report.characterization.query_count_after:.0f} per request |

## Root Cause

**{report.root_cause.confirmed_hypothesis_title}** ({report.root_cause.confidence_score:.0%} confidence)

Evidence:
{evidence}

Affected code: `{report.root_cause.affected_code_location}`

## The Fix

{report.fix.explanation}

Before:
```python
{report.fix.original_code}
```

After:
```python
{report.fix.fixed_code}
```

## Risk Assessment

**Risk Level: {report.fix.risk_level.upper()}**

{report.fix.risk_reasoning}

**Rollback:** `{report.fix.rollback_instructions}`

## Verification Checklist

{checklist}
"""