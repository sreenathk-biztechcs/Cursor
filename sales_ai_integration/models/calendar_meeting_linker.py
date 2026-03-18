import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    x_is_presale_meeting = fields.Boolean("Is Presale Meeting", default=False)
    x_presale_refs = fields.Char(
        "Presale References",
        help="Comma-separated presale references (e.g. PST-42, PST-43) discussed in this meeting.",
    )
    x_transcript_requested = fields.Boolean(
        "Transcript Requested",
        default=False,
        help="Set to True once Odoo has asked n8n to fetch the meeting transcript.",
    )

    # ------------------------------------------------------------------
    # Lead linking
    # ------------------------------------------------------------------

    def action_link_to_leads(self):
        """
        Match meeting attendees to existing active leads and set opportunity_id.
        Searches email_from, x_direct_email, and partner_id.email for robust matching.
        """
        Lead = self.env["crm.lead"].sudo()
        Activity = self.env["mail.activity"].sudo()
        stage_meeting = self.env.ref(
            "sales_ai_integration.stage_meeting", raise_if_not_found=False
        )
        activity_type_meeting = self.env.ref(
            "mail.mail_activity_data_meeting", raise_if_not_found=False
        )

        for event in self:
            if event.opportunity_id:
                continue

            emails = {
                (p.email or "").lower().strip()
                for p in event.partner_ids
                if p.email
            }
            if not emails:
                continue

            email_list = list(emails)
            domain = [
                ("active", "=", True),
                "|", "|",
                ("email_from", "in", email_list),
                ("x_direct_email", "in", email_list),
                ("partner_id.email", "in", email_list),
            ]
            lead = Lead.search(domain, order="id desc", limit=1)
            if not lead:
                continue

            event.opportunity_id = lead.id
            lead.message_post(
                body=_("Meeting '%s' auto-linked to this lead (calendar sync).", event.name or ""),
                subtype_xmlid="mail.mt_note",
            )
            _logger.info(
                "Sales AI: calendar event %s auto-linked to lead %s",
                event.id, lead.id,
            )

            if stage_meeting and lead.stage_id and lead.stage_id.sequence < stage_meeting.sequence:
                lead.stage_id = stage_meeting
                _logger.info(
                    "Sales AI: lead %s moved to Meeting stage via calendar link", lead.id,
                )

            # Create a 'Meeting' activity on the lead so it appears in the rep's
            # activity list, aligned with the auto-linked calendar event.
            if activity_type_meeting and lead.user_id:
                existing = Activity.search(
                    [
                        ("res_model", "=", "crm.lead"),
                        ("res_id", "=", lead.id),
                        ("activity_type_id", "=", activity_type_meeting.id),
                        ("date_deadline", "=", (event.start or fields.Datetime.now()).date()),
                    ],
                    limit=1,
                )
                if not existing:
                    Activity.create(
                        {
                            "res_model_id": self.env.ref("crm.model_crm_lead").id,
                            "res_id": lead.id,
                            "user_id": lead.user_id.id,
                            "activity_type_id": activity_type_meeting.id,
                            "summary": _("Client meeting: %s", event.name or lead.name or ""),
                            "date_deadline": (event.start or fields.Datetime.now()).date(),
                        }
                    )

            lead._cancel_pending_followups()

            try:
                self.env["sales.ai.n8n"].post("meeting_booked_notification", {
                    "lead_id": lead.id,
                    "lead_name": lead.name,
                    "company": lead.partner_name or "",
                    "contact_name": lead.contact_name or "",
                    "contact_email": lead.email_from or "",
                    "rep_name": lead.user_id.name if lead.user_id else "",
                    "rep_email": lead.user_id.email if lead.user_id else "",
                    "lead_stage": lead.stage_id.name if lead.stage_id else "",
                    "lead_url": f"/web#id={lead.id}&model=crm.lead&view_type=form",
                    "meeting_id": event.id,
                    "meeting_name": event.name or "",
                    "meeting_start": str(event.start) if event.start else "",
                    "meeting_stop": str(event.stop) if event.stop else "",
                    "calendar_owner": event.user_id.name if event.user_id else "",
                    "calendar_owner_email": event.user_id.email if event.user_id else "",
                    "source": "calendar_sync",
                })
            except Exception:
                _logger.error(
                    "Sales AI: n8n meeting_booked notification failed for lead %s",
                    lead.id, exc_info=True,
                )

    # ------------------------------------------------------------------
    # Presale flag
    # ------------------------------------------------------------------

    def _auto_flag_presale_meeting(self):
        """Flag events as presale meetings if all attendees are internal users."""
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

    # ------------------------------------------------------------------
    # CRUD overrides
    # ------------------------------------------------------------------

    @api.model
    def create(self, vals):
        event = super().create(vals)
        event._auto_flag_presale_meeting()
        try:
            event.action_link_to_leads()
        except Exception:
            _logger.error(
                "Sales AI: Meeting-lead auto-link failed for event %s",
                event.id, exc_info=True,
            )
        return event

    def write(self, vals):
        pre_write_starts = {}
        if "start" in vals or "stop" in vals:
            for event in self:
                if event.opportunity_id:
                    pre_write_starts[event.id] = event.start

        res = super().write(vals)

        if "partner_ids" in vals:
            self._auto_flag_presale_meeting()
            for event in self:
                if not event.opportunity_id:
                    try:
                        event.action_link_to_leads()
                    except Exception:
                        _logger.error(
                            "Sales AI: Meeting-lead re-link failed for event %s on attendee change",
                            event.id, exc_info=True,
                        )

        if pre_write_starts:
            for event in self:
                if event.id in pre_write_starts and event.opportunity_id:
                    old_start = pre_write_starts[event.id]
                    if old_start != event.start:
                        self._handle_meeting_rescheduled(event, old_start)

        return res

    def unlink(self):
        for event in self:
            if event.opportunity_id:
                self._handle_meeting_cancelled(event)
        return super().unlink()

    # ------------------------------------------------------------------
    # Reschedule / cancel handling
    # ------------------------------------------------------------------

    def _handle_meeting_rescheduled(self, event, old_start):
        """Notify lead and n8n when a linked meeting's time changes."""
        lead = event.opportunity_id
        lead.message_post(
            body=_(
                "Meeting '%s' rescheduled from %s to %s.",
                event.name or "", str(old_start), str(event.start),
            ),
            subtype_xmlid="mail.mt_note",
        )
        _logger.info(
            "Sales AI: Meeting %s (lead %s) rescheduled %s → %s",
            event.id, lead.id, old_start, event.start,
        )
        try:
            self.env["sales.ai.n8n"].post("meeting_rescheduled_notification", {
                "lead_id": lead.id,
                "lead_name": lead.name,
                "company": lead.partner_name or "",
                "contact_name": lead.contact_name or "",
                "contact_email": lead.email_from or "",
                "rep_name": lead.user_id.name if lead.user_id else "",
                "rep_email": lead.user_id.email if lead.user_id else "",
                "lead_stage": lead.stage_id.name if lead.stage_id else "",
                "lead_url": f"/web#id={lead.id}&model=crm.lead&view_type=form",
                "meeting_id": event.id,
                "meeting_name": event.name or "",
                "old_start": str(old_start),
                "new_start": str(event.start),
                "calendar_owner": event.user_id.name if event.user_id else "",
                "calendar_owner_email": event.user_id.email if event.user_id else "",
                "source": "calendar_sync",
            })
        except Exception:
            _logger.error(
                "Sales AI: n8n meeting_rescheduled notification failed for lead %s",
                lead.id, exc_info=True,
            )

    def _handle_meeting_cancelled(self, event):
        """
        Handle linked meeting deletion: log note on lead, restart follow-ups
        if the lead hasn't progressed past the Meeting stage, notify n8n.
        """
        lead = event.opportunity_id
        stage_meeting = self.env.ref(
            "sales_ai_integration.stage_meeting", raise_if_not_found=False
        )
        lead.message_post(
            body=_(
                "Meeting '%s' (was scheduled for %s) has been cancelled.",
                event.name or "",
                str(event.start) if event.start else "unknown",
            ),
            subtype_xmlid="mail.mt_note",
        )
        _logger.info(
            "Sales AI: Meeting %s (lead %s) cancelled", event.id, lead.id,
        )

        if stage_meeting and lead.stage_id == stage_meeting:
            stage_qualified = self.env.ref(
                "sales_ai_integration.stage_qualified", raise_if_not_found=False
            )
            if stage_qualified:
                lead.stage_id = stage_qualified
            lead.x_followup_stage = 0
            lead.action_create_followup_activities()
            _logger.info(
                "Sales AI: Restarted follow-ups for lead %s after meeting cancellation",
                lead.id,
            )

        try:
            self.env["sales.ai.n8n"].post("meeting_cancelled_notification", {
                "lead_id": lead.id,
                "lead_name": lead.name,
                "company": lead.partner_name or "",
                "contact_name": lead.contact_name or "",
                "contact_email": lead.email_from or "",
                "rep_name": lead.user_id.name if lead.user_id else "",
                "rep_email": lead.user_id.email if lead.user_id else "",
                "lead_stage": lead.stage_id.name if lead.stage_id else "",
                "lead_url": f"/web#id={lead.id}&model=crm.lead&view_type=form",
                "meeting_id": event.id,
                "meeting_name": event.name or "",
                "meeting_was_scheduled": str(event.start) if event.start else "",
                "calendar_owner": event.user_id.name if event.user_id else "",
                "calendar_owner_email": event.user_id.email if event.user_id else "",
                "source": "calendar_sync",
            })
        except Exception:
            _logger.error(
                "Sales AI: n8n meeting_cancelled notification failed for lead %s",
                lead.id, exc_info=True,
            )
