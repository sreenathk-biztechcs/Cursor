import hashlib
import hmac
import json
import logging
import time

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)


class SalesAiN8N(models.AbstractModel):
    """
    Helper for posting events to n8n.

    Use env['sales.ai.n8n'].post(endpoint, payload_dict)
    to trigger external flows (WBS, proposal, Teams notifications, etc.).

    Authentication (Odoo → n8n):
        Every outbound call is signed with HMAC-SHA256 using sales_ai.n8n_hmac_secret.
        n8n verifies the signature via its "Header Auth" credential check or a
        Code node:  verify = createHmac('sha256', secret).update(rawBody).digest('hex')
        Header sent: X-Odoo-Signature: sha256=<hex>
        Header sent: X-Odoo-Timestamp: <unix_ts>   (n8n rejects if >5 min old)

    The static X-N8N-Secret header is kept for backward-compatibility
    with existing n8n Header Auth credentials already configured.
    """

    _name = "sales.ai.n8n"
    _description = "Sales AI n8n Webhook Helper"

    @api.model
    def _get_base_url(self) -> str:
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("sales_ai.n8n_webhook_base_url", default="")
            .rstrip("/")
        )

    @api.model
    def _get_secret(self) -> str:
        """Static secret sent as X-N8N-Secret (n8n Header Auth verification)."""
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("sales_ai.n8n_secret_token", default="")
        )

    @api.model
    def _get_hmac_secret(self) -> str:
        """HMAC signing secret for payload integrity (Odoo → n8n direction)."""
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("sales_ai.n8n_hmac_secret", default="")
        )

    @api.model
    def _sign_payload(self, body_bytes: bytes, hmac_secret: str) -> str:
        """Return sha256=<hex> HMAC signature of the raw JSON body."""
        return "sha256=" + hmac.new(
            hmac_secret.encode(), body_bytes, hashlib.sha256
        ).hexdigest()

    @api.model
    def post(self, endpoint: str, payload: dict):
        """
        POST JSON payload to n8n endpoint.

        :param endpoint: path segment appended to base URL, e.g. 'proposal_request'
        :param payload: dict payload to send as JSON
        """
        base = self._get_base_url()
        if not base:
            _logger.warning("n8n base URL not configured; skipping call to %s", endpoint)
            return

        url = f"{base.rstrip('/')}/webhook/{endpoint.lstrip('/')}"
        ts = str(int(time.time()))
        body_bytes = json.dumps(payload, ensure_ascii=False).encode()

        headers = {
            "Content-Type": "application/json",
            "X-Odoo-Timestamp": ts,
        }

        # Static header (n8n Header Auth credential — backward-compatible)
        secret = self._get_secret()
        if secret:
            headers["X-N8N-Secret"] = secret

        # HMAC signature for payload integrity
        hmac_secret = self._get_hmac_secret()
        if hmac_secret:
            headers["X-Odoo-Signature"] = self._sign_payload(body_bytes, hmac_secret)

        try:
            resp = requests.post(url, data=body_bytes, headers=headers, timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            _logger.error("n8n POST to %s failed: %s", url, exc, exc_info=True)

