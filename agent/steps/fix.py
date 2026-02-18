# Folder: firetiger-demo/agent/steps/fix.py
#
# Step 5 of 5: Generate the fix.
# THIRD Claude API call.
#
# Takes the confirmed root cause + actual code.
# Returns a complete fix package ready to be turned into a PR.

import logging
import anthropic
from ingestion.event_schema import RootCause, Characterization, FixPackage
from agent.response_parser import parse_claude_response
import config

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def generate_fix(root_cause: RootCause,
                  char: Characterization) -> FixPackage:
    """
    Generate a production-safe fix with full context for review.
    """
    logger.info("[Step 5/5] Generating fix...")
    
    # Read the actual file that needs fixing
    file_content = _read_affected_file(root_cause.affected_code_location)
    
    prompt = f"""You are a senior backend engineer writing a production fix. Be precise and minimal. Do not refactor unrelated code.

═══════════════════════════════════════
CONFIRMED ROOT CAUSE
═══════════════════════════════════════
Issue:    {root_cause.confirmed_hypothesis_title}
Location: {root_cause.affected_code_location}
Confidence: {root_cause.confidence_score:.0%}

Evidence chain:
{chr(10).join(f'  {i+1}. {e}' for i, e in enumerate(root_cause.evidence_chain))}

The problematic code:
{root_cause.affected_code_snippet}

═══════════════════════════════════════
FULL FILE CONTENT
═══════════════════════════════════════
{file_content}

═══════════════════════════════════════
PERFORMANCE CONTEXT
═══════════════════════════════════════
Current:  {char.latency_after_ms:.0f}ms avg, {char.query_count_after:.0f} DB queries/request
Expected: {char.latency_before_ms:.0f}ms avg, {char.query_count_before:.0f} DB queries/request
Customers affected: {len(char.affected_user_ids)}

═══════════════════════════════════════
YOUR TASK
═══════════════════════════════════════
Write a minimal, targeted fix. Same function signatures. No new dependencies.

Respond in this exact JSON format only:

{{
  "fix_summary": "one sentence describing the fix",
  "original_code": "exact problematic code block to replace (copy verbatim from file content)",
  "fixed_code": "the replacement code block (same indentation)",
  "explanation": "technical explanation of why this fix works",
  "risk_level": "low",
  "risk_reasoning": "why this risk level",
  "side_effects": ["any side effects to watch for"],
  "rollback_instructions": "exact command to revert: git revert HEAD",
  "verification_checklist": [
    "Check /checkout returns in under 50ms",
    "Check DB query count per request is back to {char.query_count_before:.0f}",
    "Check no customers reporting errors in Slack"
  ],
  "pr_title": "fix: resolve N+1 query regression on {char.affected_endpoint}",
  "pr_description": "## Problem\\n\\nRegression introduced in commit {char.commit_sha}...\\n\\n## Root Cause\\n\\n...\\n\\n## Fix\\n\\n...\\n\\n## Verification\\n\\n..."
}}

Rules:
- original_code must be copied VERBATIM from the file content
- fixed_code must be a drop-in replacement with identical indentation
- pr_description should be thorough markdown that a reviewer can approve without other context
- risk_level for a simple query fix should be "low\""""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = response.content[0].text
    parsed = parse_claude_response(raw, "generate_fix")
    
    fix = FixPackage(**parsed)
    
    logger.info(
        f"[Step 5/5] Complete | "
        f"Fix: {fix.fix_summary} | "
        f"Risk: {fix.risk_level}"
    )
    
    return fix


def _read_affected_file(code_location: str) -> str:
    """
    Read the file mentioned in root cause.
    Tries to extract filename from location string like "app/db.py, get_checkout_total"
    """
    # Extract filename from location string
    parts = code_location.replace(",", " ").split()
    
    for part in parts:
        if ".py" in part:
            try:
                with open(part.strip(), "r") as f:
                    return f.read()
            except FileNotFoundError:
                pass
    
    # Fallback: read the most likely file
    try:
        with open("app/db.py", "r") as f:
            return f.read()
    except Exception:
        return "File content not available"