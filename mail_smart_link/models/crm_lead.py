import logging
import email.utils

from odoo import api, models

_logger = logging.getLogger(__name__)


class CrmLeadSmartLink(models.Model):
    _inherit = "crm.lead"

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """
        Smart-link incoming emails from known customers to existing active leads.

        If a partner + active lead already exists for the sender's email, route
        the message to that lead instead of creating a duplicate.
        Otherwise, fall back to default behaviour (new lead).
        """
        email_from = msg_dict.get("email_from") or msg_dict.get("from") or ""
        _, sender_email = email.utils.parseaddr(email_from)
        sender_email = (sender_email or "").lower().strip()

        if not sender_email:
            return super().message_new(msg_dict, custom_values=custom_values)

        Partner = self.env["res.partner"].sudo()
        partner = Partner.search([("email", "=ilike", sender_email)], limit=1)

        Lead = self.env["crm.lead"].sudo()
        domain = [("active", "=", True)]
        if partner:
            domain = [
                "|",
                ("partner_id", "=", partner.id),
                ("email_from", "=ilike", sender_email),
                ("active", "=", True),
            ]
        else:
            domain = [("email_from", "=ilike", sender_email), ("active", "=", True)]

        leads = Lead.search(domain, order="id desc", limit=1)

        if leads:
            target = leads[0]
            _logger.info(
                "mail_smart_link: Email from %s routed to existing lead %s (id=%s)",
                sender_email,
                target.name,
                target.id,
            )
            # Attach the email to existing lead as a new message
            if custom_values is None:
                custom_values = {}
            custom_values.setdefault("partner_id", partner.id if partner else False)
            return target

        # Fallback: create new lead using default behaviour
        return super().message_new(msg_dict, custom_values=custom_values)

