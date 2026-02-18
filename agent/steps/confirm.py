# Folder: firetiger-demo/agent/steps/confirm.py
#
# Step 4 of 5: Confirm the root cause.
# SECOND Claude API call.
#
# Takes all evidence and asks Claude to make a final determination.
# This is where we go from "probably N+1" to "definitely N+1, here's the proof"

import logging
import anthropic
from typing import List, Dict
from ingestion.event_schema import Hypothesis, RootCause
from agent.response_parser import parse_claude_response
import config

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def confirm_root_cause(hypotheses: List[Hypothesis],
                        evidence_bundle: Dict[int, dict]) -> RootCause:
    """
    Present all hypotheses + their evidence to Claude.
    Ask Claude to make a final determination with reasoning chain.
    """
    logger.info("[Step 4/5] Confirming root cause...")
    
    # Format hypotheses for the prompt
    hypotheses_text = ""
    for hyp in hypotheses:
        hypotheses_text += f"""
HYPOTHESIS {hyp.rank} (confidence: {hyp.confidence_score:.0%}):
Title: {hyp.title}
Description: {hyp.description}
Supporting signals: {', '.join(hyp.supporting_signals)}
"""
    
    # Format evidence for each hypothesis
    evidence_text = ""
    for rank, evidence in evidence_bundle.items():
        evidence_text += f"""
─── EVIDENCE FOR HYPOTHESIS {rank} ───────────────────
Query Patterns:
{evidence['query_patterns']}

Specific Evidence:
{chr(10).join(str(e) for e in evidence['specific_evidence'])}
"""
    
    # Get git diff (same for all hypotheses)
    git_diff = evidence_bundle.get(1, {}).get("git_diff", "Not available")
    
    prompt = f"""You are a senior backend engineer making a final root cause determination for a production incident. You have hypotheses and concrete evidence. Make a definitive call.

═══════════════════════════════════════
THE HYPOTHESES
═══════════════════════════════════════
{hypotheses_text}

═══════════════════════════════════════
EVIDENCE GATHERED
═══════════════════════════════════════
{evidence_text}

═══════════════════════════════════════
GIT DIFF (the suspect commit)
═══════════════════════════════════════
{git_diff}

═══════════════════════════════════════
YOUR TASK
═══════════════════════════════════════
Analyze all evidence and confirm the root cause. Be definitive.

Respond in this exact JSON format only:

{{
  "confirmed_hypothesis_rank": 1,
  "confirmed_hypothesis_title": "exact title from above",
  "confidence_score": 0.0,
  "evidence_chain": [
    "Observation 1: what you see in the evidence",
    "Connection 1: how that observation proves the hypothesis",
    "Observation 2: corroborating evidence",
    "Conclusion: why alternatives are less likely"
  ],
  "affected_code_location": "filename and function name from git diff",
  "affected_code_snippet": "the specific lines causing the problem (copy from git diff)"
}}

Rules:
- confidence_score should be > 0.90 if git diff clearly shows the problem
- evidence_chain must be logical step-by-step reasoning (4-6 steps)
- affected_code_snippet must come verbatim from the git diff shown above
- if git diff is unclear, lower confidence accordingly"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = response.content[0].text
    parsed = parse_claude_response(raw, "confirm_root_cause")
    
    root_cause = RootCause(
        confirmed_hypothesis_title=parsed["confirmed_hypothesis_title"],
        confidence_score=parsed["confidence_score"],
        evidence_chain=parsed["evidence_chain"],
        affected_code_location=parsed["affected_code_location"],
        affected_code_snippet=parsed["affected_code_snippet"]
    )
    
    logger.info(
        f"[Step 4/5] Complete | "
        f"Root cause: '{root_cause.confirmed_hypothesis_title}' | "
        f"Confidence: {root_cause.confidence_score:.0%}"
    )
    
    return root_cause