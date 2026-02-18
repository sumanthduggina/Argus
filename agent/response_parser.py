# Folder: firetiger-demo/agent/response_parser.py
#
# Safely parses Claude's JSON responses.
# Claude sometimes wraps JSON in markdown code fences.
# This handles that and validates the response structure.

import json
import re
import logging
from typing import Type
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def parse_claude_response(raw_response: str, 
                           step_name: str) -> dict:
    """
    Parses Claude's response into a Python dict.
    
    Handles:
    - Raw JSON
    - JSON wrapped in ```json ... ``` fences
    - JSON with extra whitespace
    
    Always logs the raw response for debugging prompt issues.
    """
    logger.debug(f"[{step_name}] Raw Claude response:\n{raw_response}")
    
    # Try 1: Direct JSON parse
    try:
        return json.loads(raw_response.strip())
    except json.JSONDecodeError:
        pass
    
    # Try 2: Strip markdown code fences
    # Claude sometimes wraps JSON in ```json ... ```
    fence_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    match = re.search(fence_pattern, raw_response)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try 3: Find outermost { } block
    start = raw_response.find("{")
    end = raw_response.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(raw_response[start:end+1])
        except json.JSONDecodeError:
            pass
    
    # All parsing failed
    logger.error(
        f"[{step_name}] Failed to parse Claude response.\n"
        f"Raw response: {raw_response[:500]}"
    )
    raise ValueError(
        f"Claude response for {step_name} could not be parsed as JSON. "
        f"Check your prompt. Raw: {raw_response[:200]}"
    )