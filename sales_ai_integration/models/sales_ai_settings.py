import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError


_logger = logging.getLogger("sales_ai")

class SalesAiSettings(models.TransientModel):
    _inherit = "res.config.settings"

    claude_api_key = fields.Char(
        string="Claude API Key",
        config_parameter="sales_ai.claude_api_key",
    )
    marketing_user_id = fields.Many2one(
        "res.users",
        string="Marketing User for Junk/Marketing Leads",
        config_parameter="sales_ai.marketing_user_id",
    )
    icp_criteria_json = fields.Char(
        string="ICP Scoring Criteria (JSON)",
        config_parameter="sales_ai.icp_criteria_json",
        help="Ideal Customer Profile used by AI lead scoring. "
        "Provide valid JSON with keys like industries, sizes, tech_stack, etc.",
    )
    n8n_webhook_base_url = fields.Char(
        string="n8n Webhook Base URL",
        config_parameter="sales_ai.n8n_webhook_base_url",
        help="Base URL for n8n webhooks, e.g. https://n8n.internal/webhook",
    )
    n8n_environment = fields.Selection(
        [
            ("live", "Live"),
            ("test", "Test"),
        ],
        string="n8n Environment",
        config_parameter="sales_ai.n8n_environment",
        default="live",
        help="Controls whether Odoo calls the live or test n8n webhook endpoints.",
    )
    n8n_secret_token = fields.Char(
        string="n8n Header Auth Secret (Odoo → n8n)",
        config_parameter="sales_ai.n8n_secret_token",
        help=(
            "Static secret sent in the X-N8N-Secret header on every Odoo→n8n call. "
            "In n8n, configure a 'Header Auth' credential with Header Name='X-N8N-Secret' "
            "and Value equal to this token."
        ),
    )
    n8n_hmac_secret = fields.Char(
        string="n8n HMAC Signing Secret (Odoo → n8n)",
        config_parameter="sales_ai.n8n_hmac_secret",
        help=(
            "Used to sign every outbound n8n webhook payload with HMAC-SHA256. "
            "Odoo sends X-Odoo-Signature and X-Odoo-Timestamp headers. "
            "Verify in n8n with: createHmac('sha256', secret).update(rawBody).digest('hex'). "
            "Can be the same value as the Header Auth Secret or a separate one."
        ),
    )
    # --- Bidirectional handshake fields (n8n → Odoo callback) ---
    odoo_base_url = fields.Char(
        string="Odoo Base URL (for n8n callbacks)",
        config_parameter="sales_ai.odoo_base_url",
        help=(
            "The public URL of this Odoo instance that n8n will use to call back. "
            "e.g. https://myodoo.company.com  — n8n appends /api/sales_ai/* paths to this."
        ),
    )
    odoo_api_key = fields.Char(
        string="Odoo API Key (for n8n → Odoo)",
        config_parameter="sales_ai.odoo_api_key",
        help=(
            "Odoo API key that n8n uses in the Authorization: Bearer header "
            "when calling back into Odoo. Generate one from Settings → Technical → API Keys."
        ),
    )
    n8n_status = fields.Selection(
        [
            ("ok", "Connected"),
            ("error", "Error"),
            ("unknown", "Unknown"),
        ],
        string="n8n Connection Status",
        config_parameter="sales_ai.n8n_status",
        help="Last known connection status to n8n.",
        readonly=True,
    )
    n8n_last_ok = fields.Datetime(
        string="n8n Last Successful Handshake",
        config_parameter="sales_ai.n8n_last_ok",
        readonly=True,
    )
    n8n_last_error = fields.Char(
        string="n8n Last Error",
        config_parameter="sales_ai.n8n_last_error",
        readonly=True,
    )
    n8n_reverse_status = fields.Selection(
        [
            ("ok", "Connected"),
            ("error", "Error"),
            ("unknown", "Unknown"),
        ],
        string="n8n → Odoo Status",
        config_parameter="sales_ai.n8n_reverse_status",
        help="Whether n8n successfully verified the reverse connection to Odoo.",
        readonly=True,
    )
    stale_thresholds_json = fields.Char(
        string="Stale Deal Thresholds (JSON)",
        config_parameter="sales_ai.stale_thresholds_json",
        help="JSON mapping of stage names to days before a deal is considered stale, "
        'e.g. {"Qualified": 7, "Meeting": 10, "Proposal": 14}.',
    )
    public_holidays_json = fields.Char(
        string="Public Holidays (JSON list of YYYY-MM-DD)",
        config_parameter="sales_ai.public_holidays_json",
        help=(
            "List of public holidays used by Sales AI to skip non-working days "
            "when scheduling follow-ups. Example: "
            '["2026-01-01", "2026-01-26", "2026-08-15"].'
        ),
    )
    apollo_api_key = fields.Char(
        string="Apollo API Key",
        config_parameter="sales_ai.apollo_api_key",
        help="API key for Apollo REST API.",
    )
    apollo_api_base_url = fields.Char(
        string="Apollo API Base URL",
        config_parameter="sales_ai.apollo_api_base_url",
        help="Base URL for Apollo API, e.g. https://api.apollo.io",
    )
    claude_system_prompt = fields.Char(
        string="Claude Global System Prompt",
        config_parameter="sales_ai.claude_system_prompt",
        help="Optional global system prompt used for generic Claude tasks.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env["ir.config_parameter"].sudo()
        res.update(
            claude_api_key=ICP.get_param("sales_ai.claude_api_key", default=""),
            marketing_user_id=int(
                ICP.get_param("sales_ai.marketing_user_id", default="0") or 0
            )
            or False,
            icp_criteria_json=ICP.get_param(
                "sales_ai.icp_criteria_json", default="{}"
            ),
            n8n_webhook_base_url=ICP.get_param(
                "sales_ai.n8n_webhook_base_url", default=""
            ),
            n8n_environment=ICP.get_param(
                "sales_ai.n8n_environment", default="live"
            ),
            n8n_secret_token=ICP.get_param(
                "sales_ai.n8n_secret_token", default=""
            ),
            n8n_hmac_secret=ICP.get_param(
                "sales_ai.n8n_hmac_secret", default=""
            ),
            odoo_base_url=ICP.get_param(
                "sales_ai.odoo_base_url",
                default=ICP.get_param("web.base.url", default=""),
            ),
            odoo_api_key=ICP.get_param(
                "sales_ai.odoo_api_key", default=""
            ),
            n8n_status=ICP.get_param("sales_ai.n8n_status", default="unknown"),
            n8n_last_ok=ICP.get_param("sales_ai.n8n_last_ok", default=False),
            n8n_last_error=ICP.get_param("sales_ai.n8n_last_error", default=""),
            n8n_reverse_status=ICP.get_param(
                "sales_ai.n8n_reverse_status", default="unknown"
            ),
            stale_thresholds_json=ICP.get_param(
                "sales_ai.stale_thresholds_json", default="{}"
            ),
            public_holidays_json=ICP.get_param(
                "sales_ai.public_holidays_json", default="[]"
            ),
        )
        return res

    def action_generate_n8n_secret(self):
        """Generate a new random shared secret for n8n header/JWT auth."""
        import secrets

        self.ensure_one()
        ICP = self.env["ir.config_parameter"].sudo()
        new_secret = secrets.token_urlsafe(48)
        ICP.set_param("sales_ai.n8n_secret_token", new_secret)
        self.n8n_secret_token = new_secret
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("n8n Secret Generated"),
                "type": "success",
                "message": _(
                    "A new n8n header/JWT secret has been generated. "
                    "Copy this value into your n8n configuration."
                ),
                "sticky": False,
            },
        }

    def action_test_n8n_connection(self):
        """
        Bidirectional handshake: POST Odoo's callback credentials to n8n's
        connection_test webhook.  n8n stores them and (optionally) pings
        Odoo back at /api/sales_ai/ping to verify the reverse direction.

        Handshake payload sent to n8n:
        {
            "odoo_base_url":   "https://myodoo.com",
            "odoo_api_key":    "<Bearer token for n8n → Odoo>",
            "shared_secret":   "<X-N8N-Secret value>",
            "hmac_secret":     "<HMAC signing secret>",
            "endpoints": [     // available callback endpoints
                "/api/sales_ai/lead_intake_complete",
                "/api/sales_ai/ping",
                ...
            ]
        }

        Expected n8n response (JSON):
        {
            "status": "ok",
            "reverse_verified": true/false,  // did n8n successfully ping Odoo back?
            "n8n_version": "1.x.x",         // optional
            "registered_endpoints": [...]    // optional — which endpoints n8n stored
        }
        """
        import requests

        self.ensure_one()
        base_url = (self.n8n_webhook_base_url or "").strip()
        secret = (self.n8n_secret_token or "").strip()
        env_tag = (self.n8n_environment or "live").strip()
        odoo_url = (self.odoo_base_url or "").strip()
        odoo_key = (self.odoo_api_key or "").strip()

        ICP = self.env["ir.config_parameter"].sudo()

        # --- Validate required fields ---
        missing = []
        if not base_url:
            missing.append("n8n Webhook Base URL")
        if not secret:
            missing.append("n8n Header Auth Secret")
        if not odoo_url:
            missing.append("Odoo Base URL")
        if not odoo_key:
            missing.append("Odoo API Key")

        if missing:
            msg = _(
                "Please configure the following before testing: %s"
            ) % ", ".join(missing)
            _logger.warning(
                "sales_ai: [N8N-CONNECT] Missing fields: %s", ", ".join(missing)
            )
            ICP.set_param("sales_ai.n8n_status", "error")
            ICP.set_param("sales_ai.n8n_last_error", msg)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("n8n Connection"),
                    "type": "warning",
                    "message": msg,
                    "sticky": True,
                },
            }

        # --- Build handshake payload ---
        handshake_payload = {
            "odoo_base_url": odoo_url.rstrip("/"),
            "odoo_api_key": odoo_key,
            "shared_secret": secret,
            "hmac_secret": (self.n8n_hmac_secret or "").strip(),
            "endpoints": [
                "/api/sales_ai/ping",
                "/api/sales_ai/lead_intake_complete",
                "/api/sales_ai/receive_apollo_data",
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

        suffix = "webhook-test" if env_tag == "test" else "webhook"
        url = f"{base_url.rstrip('/')}/{suffix}/connection_test"
        headers = {
            "Content-Type": "application/json",
            "X-N8N-Secret": secret,
        }

        # --- Send handshake ---
        ok = False
        reverse_ok = False
        try:
            _logger.info(
                "sales_ai: [N8N-CONNECT] Bidirectional handshake POST %s (env=%s)",
                url, env_tag,
            )
            resp = requests.post(
                url, json=handshake_payload, headers=headers, timeout=90,
            )
            ok = resp.ok
            status = resp.status_code
        except Exception as exc:
            status = None
            msg = _("Failed to reach n8n: %s") % exc
            _logger.error(
                "sales_ai: [N8N-CONNECT] Handshake error: %s", exc, exc_info=True,
            )
        else:
            if ok:
                # Parse n8n response for reverse verification status
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                reverse_ok = body.get("reverse_verified", False)
                registered = body.get("registered_endpoints") or []
                n8n_version = body.get("n8n_version") or "unknown"

                ICP.set_param("sales_ai.n8n_status", "ok")
                ICP.set_param("sales_ai.n8n_last_ok", fields.Datetime.now())
                ICP.set_param("sales_ai.n8n_last_error", "")
                ICP.set_param(
                    "sales_ai.n8n_reverse_status", "ok" if reverse_ok else "unknown",
                )

                if reverse_ok:
                    msg = _(
                        "Bidirectional handshake OK (HTTP %s). "
                        "n8n verified reverse connection to Odoo. "
                        "n8n version: %s, registered %d endpoint(s)."
                    ) % (status, n8n_version, len(registered))
                else:
                    msg = _(
                        "Odoo → n8n connected (HTTP %s). "
                        "n8n did not confirm reverse ping to Odoo — "
                        "update your n8n connection_test workflow to verify the "
                        "reverse direction. n8n version: %s."
                    ) % (status, n8n_version)

                _logger.info(
                    "sales_ai: [N8N-CONNECT] Handshake OK (HTTP %s, reverse=%s, "
                    "n8n_version=%s, registered=%s)",
                    status, reverse_ok, n8n_version, registered,
                )
            else:
                msg = _(
                    "n8n responded with HTTP %s. "
                    "Check the URL, environment, and secret."
                ) % status
                _logger.warning(
                    "sales_ai: [N8N-CONNECT] Handshake failed (HTTP %s)", status,
                )
                ICP.set_param("sales_ai.n8n_status", "error")
                ICP.set_param("sales_ai.n8n_last_error", msg)
                ICP.set_param("sales_ai.n8n_reverse_status", "error")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("n8n Connection"),
                "type": "success" if ok else "warning",
                "message": msg,
                "sticky": not ok,
            },
        }

