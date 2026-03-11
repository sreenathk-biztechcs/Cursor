import logging
from typing import Any, Dict, Optional

from odoo import api, models

_logger = logging.getLogger(__name__)

ANTHROPIC_MODEL_DEFAULT_HAIKU = "claude-3-5-haiku-20241022"
ANTHROPIC_MODEL_DEFAULT_SONNET = "claude-3-5-sonnet-20241022"
ANTHROPIC_MODEL_DEFAULT_OPUS = "claude-3-opus-20240229"


class SalesAiMixin(models.AbstractModel):
    """
    Shared helper to call Claude via the Anthropic Python SDK.
    This is intentionally thin – all prompt design should live in the
    business models so we can adapt quickly without touching this core.
    """

    _name = "sales.ai.mixin"
    _description = "Sales AI Helper Mixin"

    @api.model
    def _get_claude_client(self):
        """Return an Anthropic client instance, or None if not configured."""
        try:
            from anthropic import Anthropic
        except Exception as exc:  # pragma: no cover - import-time guard
            _logger.error("Anthropic SDK not available: %s", exc)
            return None

        icp_settings = self.env["res.config.settings"].sudo().get_values()
        api_key = icp_settings.get("sales_ai_claude_api_key")
        if not api_key:
            _logger.warning("Claude API key not configured in Sales AI settings.")
            return None

        return Anthropic(api_key=api_key)

    @api.model
    def call_claude(
        self,
        user_content: str,
        *,
        system_prompt: str = "",
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Optional[str]:
        """
        Simple helper to call Claude and return the text content.
        All callers should assume this can return None on failure and
        implement safe fallbacks.
        """
        client = self._get_claude_client()
        if not client:
            return None

        model_name = model or ANTHROPIC_MODEL_DEFAULT_HAIKU

        messages = [
            {
                "role": "user",
                "content": user_content,
            }
        ]

        try:
            response = client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or None,
                messages=messages,
            )
        except Exception as exc:  # pragma: no cover - network / quota issues
            _logger.error("Claude API call failed: %s", exc, exc_info=True)
            return None

        try:
            # Anthropic v1 Messages API: content is a list of blocks.
            # We concatenate any text blocks we get back.
            parts = []
            for block in response.content:
                # block.type is often "text"
                text = getattr(block, "text", None) or getattr(block, "value", None)
                if text:
                    parts.append(text)
            return "\n".join(parts).strip() if parts else None
        except Exception as exc:  # pragma: no cover - defensive
            _logger.error("Failed to parse Claude response: %s", exc, exc_info=True)
            return None

