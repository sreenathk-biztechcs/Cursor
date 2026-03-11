import logging

from odoo import models

_logger = logging.getLogger(__name__)

_FOLLOWUP_XMLID = "sales_ai_integration.activity_type_followup_email"


class MailActivity(models.Model):
    """
    When a follow-up email activity is marked done, increment x_followup_stage
    on the related CRM lead so the system tracks which follow-up the rep just sent.
    """

    _inherit = "mail.activity"

    def action_feedback(self, feedback=False):
        # Capture follow-up activities before super() unlinks them
        followup_type = self.env.ref(_FOLLOWUP_XMLID, raise_if_not_found=False)
        followup_acts = (
            self.filtered(
                lambda a: followup_type and a.activity_type_id == followup_type
                and a.res_model == "crm.lead"
            )
            if followup_type
            else self.env["mail.activity"]
        )
        lead_ids = followup_acts.mapped("res_id")

        res = super().action_feedback(feedback=feedback)

        # Increment stage counter on the related leads
        if lead_ids:
            leads = self.env["crm.lead"].sudo().browse(lead_ids).exists()
            for lead in leads:
                try:
                    lead.x_followup_stage = (lead.x_followup_stage or 0) + 1
                except Exception:
                    _logger.warning(
                        "Failed to increment x_followup_stage on lead %s", lead.id
                    )
        return res

