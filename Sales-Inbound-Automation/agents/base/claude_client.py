"""
Singleton Anthropic client — import this everywhere instead of creating
a new client per agent call.
"""

import os
import anthropic

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    """Return the shared Anthropic client, initializing it on first call."""
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Add it to your Odoo server config or .env file."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client
