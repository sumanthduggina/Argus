# Folder: firetiger-demo/agent/steps/fix.py

import logging
import anthropic
from ingestion.event_schema import RootCause, Characterization, FixPackage
from agent.response_parser import parse_claude_response
import config

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def generate_fix(root_cause: RootCause,
                 char: Characterization) -> FixPackage:
    logger.info("[Step 5/5] Generating fix...")

    file_snippet = _read_affected_function(
        root_cause.affected_code_location
    )

    prompt = f"""You are a senior backend engineer writing a production fix for a Python Flask/SQLite app.

IMPORTANT CONTEXT:
- This app uses RAW SQLITE, not SQLAlchemy or any ORM
- The file is app/db.py
- The function get_checkout_total has TWO paths:
  - SLOW path: triggered when config.USE_SLOW_QUERY is True, loops and fires N+1 queries
  - FAST path: single JOIN query, fires 1 query
- The fix must be specific to THIS codebase

ROOT CAUSE:
{root_cause.confirmed_hypothesis_title}
Confidence: {root_cause.confidence_score:.0%}
Location: {root_cause.affected_code_location}

EVIDENCE:
{chr(10).join(root_cause.evidence_chain)}

PERFORMANCE IMPACT:
Latency:  {char.latency_before_ms:.0f}ms -> {char.latency_after_ms:.0f}ms
Queries:  {char.query_count_before:.0f} -> {char.query_count_after:.0f} per request
Endpoint: {char.affected_endpoint}

ACTUAL CODE FROM app/db.py:
{file_snippet}

YOUR TASK:
Write a minimal fix for THIS specific codebase.
Generate a clear PR title and description explaining what happened and what you fixed.

Respond with ONLY raw JSON, absolutely no markdown fences, no backticks, no extra text:

{{
  "fix_summary": "your generated summary here",
  "original_code": "if config.USE_SLOW_QUERY:",
  "fixed_code": "if False:  # Argus fix: always use fast JOIN path",
  "explanation": "your detailed technical explanation here",
  "risk_level": "low",
  "risk_reasoning": "your risk reasoning here",
  "side_effects": ["your side effects here"],
  "rollback_instructions": "git revert HEAD",
  "verification_checklist": [
    "your verification step 1",
    "your verification step 2",
    "your verification step 3"
  ],
  "pr_title": "your generated PR title here",
  "pr_description": "your generated detailed PR description here explaining the incident, root cause, and fix"
}}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if Claude added them despite instructions
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]).strip()
    if raw.startswith("json"):
        raw = raw[4:].strip()

    parsed = parse_claude_response(raw, "generate_fix")
    fix = FixPackage(**parsed)

    logger.info(
        f"[Step 5/5] Complete | "
        f"Fix: {fix.fix_summary} | "
        f"Risk: {fix.risk_level}"
    )

    return fix


def _read_affected_function(code_location: str) -> str:
    """Read only the affected function from the file"""
    try:
        file_path = "app/db.py"
        for part in code_location.replace(",", " ").split():
            if ".py" in part:
                file_path = part.strip()
                break

        with open(file_path, "r") as f:
            content = f.read()

        # Extract just the get_checkout_total function
        start = content.find("def get_checkout_total")
        if start != -1:
            return content[start:start+1000]

        return content[:1000]

    except Exception:
        return "File not available"

