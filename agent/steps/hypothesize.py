# Folder: firetiger-demo/agent/steps/hypothesize.py
#
# Step 2 of 5: Generate hypotheses for what caused the regression.
# FIRST Claude API call in the investigation chain.
#
# Takes the characterization (what) + knowledge graph context (history)
# Returns 3 ranked hypotheses with confidence scores.

import logging
import anthropic
from typing import List
from ingestion.event_schema import Characterization, Hypothesis
from storage.knowledge_graph import KnowledgeGraph
from agent.response_parser import parse_claude_response
import config

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def hypothesize(char: Characterization, 
                kg: KnowledgeGraph) -> List[Hypothesis]:
    """
    Ask Claude to generate 3 ranked hypotheses for the root cause.
    
    Context fed to Claude:
    1. The characterization data (what changed)
    2. Similar past incidents (has this happened before?)
    3. Patterns for changed files (is db.py often the culprit?)
    """
    logger.info("[Step 2/5] Generating hypotheses...")
    
    # ─── Pull context from knowledge graph ────────────────────────────────
    past_incidents = kg.get_similar_incidents(char.affected_endpoint)
    
    # Format past incidents for the prompt
    past_incidents_text = "None on record."
    if past_incidents:
        lines = []
        for inc in past_incidents:
            lines.append(
                f"- Incident {inc['id']}: {inc['root_cause']} | "
                f"Fix: {inc['fix_applied'][:100] if inc['fix_applied'] else 'unknown'} | "
                f"Resolved in {inc['time_to_resolve_sec']:.0f}s"
            )
        past_incidents_text = "\n".join(lines)
    
    # ─── Build the prompt ─────────────────────────────────────────────────
    prompt = f"""You are a senior backend engineer at a fintech company investigating a production regression. You have deep experience with database performance, ORM patterns, and distributed systems.

═══════════════════════════════════════
ANOMALY SUMMARY
═══════════════════════════════════════
Endpoint:          {char.affected_endpoint}
Detected at:       {char.regression_start_time}
Suspect commit:    {char.commit_sha}

Performance change:
  Latency:         {char.latency_before_ms:.1f}ms  →  {char.latency_after_ms:.1f}ms  ({char.latency_multiplier}x slower)
  DB queries/req:  {char.query_count_before:.0f}    →  {char.query_count_after:.0f}     ({char.query_multiplier}x more queries)
  DB time/req:     {char.db_time_before_ms:.1f}ms  →  {char.db_time_after_ms:.1f}ms
  Memory:          {char.memory_before_mb:.1f}MB   →  {char.memory_after_mb:.1f}MB

Affected customers: {len(char.affected_user_ids)} users
Other endpoints affected: {"YES - possible infra issue" if char.all_endpoints_affected else "NO - likely code issue in this endpoint"}

═══════════════════════════════════════
PAST INCIDENTS ON THIS ENDPOINT
═══════════════════════════════════════
{past_incidents_text}

═══════════════════════════════════════
YOUR TASK
═══════════════════════════════════════
Generate exactly 3 hypotheses for the root cause, ranked by probability.
The DB query explosion ({char.query_count_before:.0f} → {char.query_count_after:.0f} queries) is your primary signal.

Respond in this exact JSON format only, no text outside the JSON:

{{
  "hypotheses": [
    {{
      "rank": 1,
      "title": "short name for this hypothesis",
      "description": "detailed explanation of what is causing this and why it produces these exact symptoms",
      "confidence_score": 0.0,
      "supporting_signals": ["signal 1 from the data above", "signal 2"],
      "evidence_needed": ["specific queryable data that would confirm this"],
      "similar_past_incident_id": null
    }},
    {{
      "rank": 2,
      "title": "...",
      "description": "...",
      "confidence_score": 0.0,
      "supporting_signals": [],
      "evidence_needed": [],
      "similar_past_incident_id": null
    }},
    {{
      "rank": 3,
      "title": "...",
      "description": "...",
      "confidence_score": 0.0,
      "supporting_signals": [],
      "evidence_needed": [],
      "similar_past_incident_id": null
    }}
  ]
}}

Rules:
- confidence_scores across all 3 must sum to exactly 1.0
- rank 1 should reflect the most likely cause given the query explosion
- if past incidents match, reference their ID in similar_past_incident_id
- evidence_needed must be specific (e.g. "git diff showing loop added" not "check the code")"""

    # ─── Call Claude ───────────────────────────────────────────────────────
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = response.content[0].text
    parsed = parse_claude_response(raw, "hypothesize")
    
    # Convert to Hypothesis objects
    hypotheses = [
        Hypothesis(**h) for h in parsed["hypotheses"]
    ]
    
    logger.info(
        f"[Step 2/5] Complete | "
        f"Top hypothesis: '{hypotheses[0].title}' "
        f"({hypotheses[0].confidence_score:.0%} confidence)"
    )
    
    return hypotheses