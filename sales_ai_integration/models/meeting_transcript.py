import json

from odoo import fields, models


class SalesAiMeetingTranscript(models.Model):
    _name = "sales.ai.meeting.transcript"
    _description = "Sales AI Meeting Transcript"

    lead_id = fields.Many2one(
        "crm.lead",
        string="Lead",
        required=True,
        ondelete="cascade",
    )
    meeting_name = fields.Char("Meeting Title")
    meeting_date = fields.Date("Meeting Date")
    meeting_start = fields.Datetime("Meeting Start")
    meeting_duration = fields.Integer("Duration (minutes)")
    conversation_id = fields.Char("Conversation ID")
    conversation_url = fields.Char(
        "Conversation URL",
        help="Apollo conversation URL for the transcript.",
    )
    source = fields.Char("Source")
    transcript = fields.Text("Transcript")
    extracted_at = fields.Datetime(
        "Extracted At",
        help="Timestamp when the transcript was extracted from Apollo.",
    )
    payload_json = fields.Text(
        "Claude Payload (JSON)",
        help="JSON payload sent to Claude ClientMOMAgent for this meeting.",
    )
    request_payload_json = fields.Text(
        "Request Payload (JSON)",
        help="Raw JSON payload received from n8n / transcript service for this meeting.",
    )

