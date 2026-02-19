# agent/response_parser.py

import json
import re
import logging

logger = logging.getLogger(__name__)


def parse_claude_response(raw_response: str, step_name: str) -> dict:
    """
    Parses Claude's JSON response handling all edge cases.
    """
    # Log raw response for debugging
    logger.debug(f"[{step_name}] Raw response length: {len(raw_response)}")

    # Clean the response
    text = raw_response.strip()

    # Try 1: Direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try 2: Extract from ```json ... ``` fences
    fence_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    matches = re.findall(fence_pattern, text)
    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # Try 3: Find outermost { } block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass

    # Try 4: Fix truncated JSON by finding last complete object
    # Sometimes Claude response gets cut off
    if start != -1:
        # Try progressively smaller substrings
        subset = text[start:]
        for i in range(len(subset), 0, -1):
            try:
                return json.loads(subset[:i])
            except json.JSONDecodeError:
                continue

    # All failed
    logger.error(
        f"[{step_name}] Failed to parse. "
        f"Raw start: {raw_response[:300]}"
    )
    raise ValueError(
        f"Could not parse Claude response for {step_name}. "
        f"Raw: {raw_response[:200]}"
    )