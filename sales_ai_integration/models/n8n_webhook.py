import hashlib
import hmac
import json
import logging
import time

import requests

from odoo import api, models, fields

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
    def _ensure_connected(self):
        """
        Best-effort background handshake to keep n8n status fresh.

        Sends the same bidirectional payload as action_test_n8n_connection
        so n8n always has up-to-date Odoo callback credentials.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        base_root = (ICP.get_param("sales_ai.n8n_webhook_base_url", default="") or "").strip()
        secret = ICP.get_param("sales_ai.n8n_secret_token", default="") or ""
        if not base_root or not secret:
            _logger.debug(
                "sales_ai: [N8N-HEALTH] Skipping healthcheck (missing base URL or secret)."
            )
            return

        env_tag = (ICP.get_param("sales_ai.n8n_environment", default="live") or "live").strip()
        suffix = "webhook-test" if env_tag == "test" else "webhook"
        url = f"{base_root.rstrip('/')}/{suffix}/connection_test"

        # Prefer explicit Sales AI Odoo base URL; fall back to global web.base.url
        odoo_url = (
            ICP.get_param("sales_ai.odoo_base_url", default="")
            or ICP.get_param("web.base.url", default="")
        ).strip()
        odoo_key = (ICP.get_param("sales_ai.odoo_api_key", default="") or "").strip()
        hmac_secret = ICP.get_param("sales_ai.n8n_hmac_secret", default="") or ""

        handshake_payload = {
            "odoo_base_url": odoo_url.rstrip("/") if odoo_url else "",
            "odoo_api_key": odoo_key,
            "shared_secret": secret,
            "hmac_secret": hmac_secret,
            "endpoints": [
                "/api/sales_ai/ping",
                "/api/sales_ai/lead_intake_complete",
                "/api/sales_ai/receive_transcript",
                "/api/sales_ai/enrichment_structured",
                "/api/sales_ai/proposal_ready",
                "/api/sales_ai/wbs_ready",
                "/api/sales_ai/presale_mom_posted",
                "/api/sales_ai/stale_deals",
                "/api/sales_ai/calendar_event_create",
                "/api/sales_ai/meeting_done",
                "/api/sales_ai/meeting_no_show",
                "/api/sales_ai/presale_transcript",
                "/api/enrich_lead",
                "/api/create_mom_activity",
            ],
        }

        headers = {
            "Content-Type": "application/json",
            "X-N8N-Secret": secret,
        }

        try:
            _logger.debug("sales_ai: [N8N-HEALTH] Healthcheck POST %s (env=%s)", url, env_tag)
            resp = requests.post(
                url, json=handshake_payload, headers=headers, timeout=5,
            )
            if resp.ok:
                _logger.info(
                    "sales_ai: [N8N-HEALTH] Healthcheck OK (HTTP %s)", resp.status_code
                )
                ICP.set_param("sales_ai.n8n_status", "ok")
                ICP.set_param("sales_ai.n8n_last_ok", fields.Datetime.now())
                ICP.set_param("sales_ai.n8n_last_error", "")
                # Check reverse verification from n8n response
                try:
                    body = resp.json()
                    if body.get("reverse_verified"):
                        ICP.set_param("sales_ai.n8n_reverse_status", "ok")
                except Exception:
                    pass
            else:
                _logger.warning(
                    "sales_ai: [N8N-HEALTH] Healthcheck failed (HTTP %s)", resp.status_code
                )
                ICP.set_param("sales_ai.n8n_status", "error")
                ICP.set_param(
                    "sales_ai.n8n_last_error",
                    f"Handshake HTTP {resp.status_code}",
                )
        except Exception as exc:
            _logger.error("sales_ai: [N8N-HEALTH] Healthcheck error: %s", exc, exc_info=True)
            ICP.set_param("sales_ai.n8n_status", "error")
            ICP.set_param("sales_ai.n8n_last_error", str(exc))

    @api.model
    def _get_base_url(self) -> str:
        ICP = self.env["ir.config_parameter"].sudo()
        base = (ICP.get_param("sales_ai.n8n_webhook_base_url", default="") or "").rstrip(
            "/"
        )
        env_tag = (ICP.get_param("sales_ai.n8n_environment", default="live") or "live").strip()
        # For test environment, use /webhook-test/ path to hit n8n's test URL.
        suffix = "webhook-test" if env_tag == "test" else "webhook"
        if not base:
            return ""
        return f"{base}/{suffix}"

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

        url = f"{base.rstrip('/')}/{endpoint.lstrip('/')}"
        _logger.info("sales_ai: [N8N-POST] POST %s payload_keys=%s", url, list(payload.keys()))

        ts_int = int(time.time())
        ts = str(ts_int)

        # Envelope the business payload with Odoo callback metadata so that
        # n8n always knows how to call back (base URL, API key, shared secret).
        ICP = self.env["ir.config_parameter"].sudo()
        odoo_url = (ICP.get_param("sales_ai.odoo_base_url", default="") or "").strip()
        odoo_key = (ICP.get_param("sales_ai.odoo_api_key", default="") or "").strip()

        shared_secret = self._get_secret() or ""
        hmac_secret = self._get_hmac_secret() or ""

        envelope = {
            "odoo_base_url": odoo_url.rstrip("/") if odoo_url else "",
            "odoo_api_key": odoo_key,
            "shared_secret": shared_secret,
            "hmac_secret": hmac_secret,
            "odoo_db": self.env.cr.dbname,
            "endpoint": endpoint,
            "payload": payload,
        }

        body_bytes = json.dumps(envelope, ensure_ascii=False).encode()

        headers = {
            "Content-Type": "application/json",
            "X-Odoo-Timestamp": ts,
        }

        # Static header (n8n Header Auth credential) – always send the raw shared secret
        if shared_secret:
            headers["X-N8N-Secret"] = shared_secret

        # HMAC signature for payload integrity (sign the full envelope body)
        if hmac_secret:
            headers["X-Odoo-Signature"] = self._sign_payload(body_bytes, hmac_secret)

        try:
            resp = requests.post(url, data=body_bytes, headers=headers,
                                 timeout=90)
            status = resp.status_code
            text_preview = (resp.text or "")[:1000]
            _logger.info(
                "sales_ai: [N8N-RESP] HTTP %s from %s — body=%s",
                status,
                url,
                text_preview,
            )
            resp.raise_for_status()
        except Exception as exc:
            # Log both the transport error and any HTTP response body we got back
            body = ""
            try:
                body = resp.text[:1000] if "resp" in locals() and resp is not None else ""
            except Exception:
                body = ""
            _logger.error(
                "n8n POST to %s failed: %s, response_body=%s",
                url,
                exc,
                body,
                exc_info=True,
            )
            # IMPORTANT: propagate failures so callers can stop the pipeline and log correctly.
            raise

        # Try to return parsed JSON so callers (e.g. lead intake) can react
        try:
            return resp.json()
        except Exception:
            return None

