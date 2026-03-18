import json
import logging
from typing import Any, Dict, Optional, Union

from odoo import api, models

_logger = logging.getLogger("sales_ai")  # unified logger — grep 'sales_ai' in odoo.log


class ClaudeService(models.AbstractModel):
    """
    Central service for calling Anthropic Claude.

    Always use env['claude.service'].call(...) from business code.
    """

    _name = "claude.service"
    _description = "Claude AI Service"

    MODELS = {
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
        "opus": "claude-opus-4-6",
    }

    @api.model
    def _get_api_key(self) -> Optional[str]:
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("sales_ai.claude_api_key", default="")
        ) or None

    @api.model
    def _get_client(self):
        """Return an Anthropic client instance or None if not configured."""
        api_key = self._get_api_key()
        if not api_key:
            _logger.error(
                "sales_ai: [CONFIG ERROR] Claude API key is NOT set. "
                "Fix: Settings → Technical → System Parameters → sales_ai.claude_api_key. "
                "All AI classification, scoring, and email generation will be SKIPPED until this is set."
            )
            return None
        try:
            from anthropic import Anthropic
        except Exception as exc:  # pragma: no cover
            _logger.error("Anthropic SDK import failed: %s", exc)
            return None
        return Anthropic(api_key=api_key)

    @api.model
    def call(
        self,
        tier: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
        expect_json: bool = False,
        temperature: float = 0.2,
    ) -> Union[str, Dict[str, Any]]:
        """
        Call Claude with the given tier and prompts.

        :param tier: 'haiku', 'sonnet', or 'opus'
        :param system_prompt: system message
        :param user_message: user content text
        :param max_tokens: response token cap
        :param expect_json: if True, try to parse JSON and return dict
        :param temperature: sampling temperature
        :return: raw text or parsed JSON (dict) depending on expect_json
        """
        model_name = self.MODELS.get(tier)
        if not model_name:
            raise ValueError(f"Unsupported Claude tier: {tier}")

        client = self._get_client()
        if not client:
            return {} if expect_json else ""

        try:
            resp = client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or None,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:  # pragma: no cover - network / quota / auth
            _logger.error("Claude API error for tier %s: %s", tier, exc, exc_info=True)
            raise

        # Anthropic messages API: list of content blocks
        text_parts = []
        for block in resp.content:
            text = getattr(block, "text", None) or getattr(block, "value", None)
            if text:
                text_parts.append(text)

        raw = "\n".join(text_parts).strip()

        # Retry once if response is empty and JSON was expected (transient API issue)
        if not raw and expect_json:
            _logger.warning(
                "Claude returned empty response for tier=%s; retrying once...", tier
            )
            try:
                resp = client.messages.create(
                    model=model_name,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt or None,
                    messages=[{"role": "user", "content": user_message}],
                )
                text_parts = []
                for block in resp.content:
                    text = getattr(block, "text", None) or getattr(block, "value", None)
                    if text:
                        text_parts.append(text)
                raw = "\n".join(text_parts).strip()
            except Exception as retry_exc:
                _logger.error("Claude retry also failed: %s", retry_exc)

        if not expect_json:
            return raw

        # Strip ```json fences if present
        fenced = raw.strip()
        if fenced.startswith("```"):
            fenced = fenced.strip("`")
            if fenced.startswith("json"):
                fenced = fenced[4:]
        try:
            return json.loads(fenced)
        except Exception as exc:
            _logger.error("Failed to parse JSON from Claude response: %s", exc)
            _logger.debug("Raw JSON candidate (first 500 chars): %.500s", raw)
            return {}

    @api.model
    def call_vision(
        self,
        image_b64: str,
        media_type: str,
        prompt: str,
        max_tokens: int = 500,
    ) -> str:
        """
        Call Claude with an image (base64-encoded) for visual analysis.
        Used for describing image attachments on leads.

        :param image_b64: base64-encoded image data
        :param media_type: MIME type (e.g. image/jpeg, image/png)
        :param prompt: what to extract/describe
        :param max_tokens: response cap
        :return: text description
        """
        client = self._get_client()
        if not client:
            return ""

        try:
            resp = client.messages.create(
                model=self.MODELS["haiku"],  # vision with cheapest model
                max_tokens=max_tokens,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }],
            )
        except Exception as exc:
            _logger.error("Claude Vision API error: %s", exc, exc_info=True)
            return ""

        text_parts = []
        for block in resp.content:
            text = getattr(block, "text", None) or getattr(block, "value", None)
            if text:
                text_parts.append(text)
        return "\n".join(text_parts).strip()

