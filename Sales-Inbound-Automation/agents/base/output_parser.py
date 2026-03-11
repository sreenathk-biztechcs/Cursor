"""
Output parser helpers — extract and validate structured data from Claude responses.
"""

import json
import re
from typing import Any


def extract_json(text: str) -> dict | list:
    """
    Extract the first valid JSON object or array from a Claude response.
    Handles cases where Claude wraps JSON in markdown code fences.
    """
    # Strip markdown fences if present
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the outermost { } or [ ]
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        end   = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"No valid JSON found in response:\n{text[:500]}")


def get_text(response: Any) -> str:
    """Extract plain text from an Anthropic Message response object."""
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


def usage(response: Any) -> tuple[int, int]:
    """Return (input_tokens, output_tokens) from a response."""
    return response.usage.input_tokens, response.usage.output_tokens
