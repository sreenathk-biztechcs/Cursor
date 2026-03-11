"""
Audit logger — appends one JSON line per agent call to the audit log.
Used for debugging, token tracking, and compliance.
"""

import json
import os
from datetime import datetime, timezone

from agents.config import AUDIT_LOG_PATH


def log_call(
    agent_name: str,
    model: str,
    lead_id: int | str,
    input_tokens: int,
    output_tokens: int,
    success: bool,
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    """Append one audit record to the JSONL log file."""
    record = {
        "ts":            datetime.now(timezone.utc).isoformat(),
        "agent":         agent_name,
        "model":         model,
        "lead_id":       lead_id,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "success":       success,
        "error":         error,
    }
    if extra:
        record.update(extra)

    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
