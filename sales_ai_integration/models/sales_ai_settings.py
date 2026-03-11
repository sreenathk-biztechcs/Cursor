from odoo import api, fields, models, _
from odoo.exceptions import UserError


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
    stale_thresholds_json = fields.Char(
        string="Stale Deal Thresholds (JSON)",
        config_parameter="sales_ai.stale_thresholds_json",
        help="JSON mapping of stage names to days before a deal is considered stale, "
        'e.g. {"Qualified": 7, "Meeting": 10, "Proposal": 14}.',
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

    def action_generate_n8n_secret(self):
        """Generate a new random shared secret for n8n header/JWT auth."""
        import secrets

        ICP = self.env["ir.config_parameter"].sudo()
        new_secret = secrets.token_urlsafe(48)
        ICP.set_param("sales_ai.n8n_secret_token", new_secret)
        self.n8n_secret_token = new_secret
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "n8n Secret Generated",
                "type": "success",
                "message": "A new n8n header/JWT secret has been generated.",
                "sticky": False,
            },
        }

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
            n8n_secret_token=ICP.get_param(
                "sales_ai.n8n_secret_token", default=""
            ),
            n8n_hmac_secret=ICP.get_param(
                "sales_ai.n8n_hmac_secret", default=""
            ),
            stale_thresholds_json=ICP.get_param(
                "sales_ai.stale_thresholds_json", default="{}"
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
        """Test connectivity to n8n using the configured base URL and secret."""
        import requests

        self.ensure_one()
        base_url = (self.n8n_webhook_base_url or "").strip()
        secret = (self.n8n_secret_token or "").strip()

        if not base_url:
            raise UserError(_("Please set the n8n Webhook Base URL first."))
        if not secret:
            raise UserError(_("Please set or generate the n8n Header Auth Secret first."))

        # Simple GET to the base URL with the header; we only care if we reach n8n
        # and get a non-error HTTP status code.
        try:
            resp = requests.get(
                base_url,
                headers={"X-N8N-Secret": secret},
                timeout=5,
            )
            ok = resp.ok
            status = resp.status_code
        except Exception as exc:
            ok = False
            status = None
            msg = _("Failed to reach n8n: %s") % exc
        else:
            if ok:
                msg = _(
                    "Successfully reached n8n (HTTP %s). "
                    "If you have a specific webhook path, make sure it matches this base URL."
                ) % status
            else:
                msg = _(
                    "n8n responded with HTTP %s. Check that the URL and secret are correct."
                ) % status

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("n8n Connection Test"),
                "type": "success" if ok else "warning",
                "message": msg,
                "sticky": False,
            },
        }

