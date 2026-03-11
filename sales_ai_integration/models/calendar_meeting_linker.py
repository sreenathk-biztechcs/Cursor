import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    x_is_presale_meeting = fields.Boolean("Is Presale Meeting", default=False)
    x_presale_ticket_ids = fields.Many2many(
        "project.task", string="Presale Tickets Discussed"
    )

    def action_link_to_leads(self):
        """
        Match meeting attendees to existing active leads and set opportunity_id.
        """
        Lead = self.env["crm.lead"].sudo()
        for event in self:
            emails = {
                (p.email or "").lower().strip()
                for p in event.partner_ids
                if p.email
            }
            if not emails:
                continue

            domain = [
                ("active", "=", True),
                ("email_from", "in", list(emails)),
            ]
            lead = Lead.search(domain, order="id desc", limit=1)
            if not lead:
                continue

            event.opportunity_id = lead.id
            lead.message_post(
                body=_("Meeting %s auto-linked to this lead.", event.name or ""),
                subtype_xmlid="mail.mt_note",
            )
            _logger.info(
                "Sales AI: calendar event %s auto-linked to lead %s",
                event.id,
                lead.id,
            )

    def _auto_flag_presale_meeting(self):
        """
        Flag events as presale meetings if all attendees are internal users.
        """
        Users = self.env["res.users"].sudo()
        for event in self:
            emails = [p.email for p in event.partner_ids if p.email]
            if not emails:
                event.x_is_presale_meeting = False
                continue
            internal = Users.search(
                [("email", "in", emails), ("share", "=", False)]
            )
            event.x_is_presale_meeting = len(internal) == len(emails)

    @api.model
    def create(self, vals):
        event = super().create(vals)
        event._auto_flag_presale_meeting()
        return event

    def write(self, vals):
        res = super().write(vals)
        if "partner_ids" in vals:
            self._auto_flag_presale_meeting()
        return res

