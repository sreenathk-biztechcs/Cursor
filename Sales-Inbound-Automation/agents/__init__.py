# Inbound Sales AI Agents
# Import agents by phase for clean Odoo integration

from agents.phase1 import (
    junk_filter,
    enrichment_structurer,
    lead_scoring,
    auto_ack_drafter,
    follow_up_drafter,
    reply_classifier,
    client_mom,
)

from agents.phase2 import (
    ticket_gist,
    daily_agenda,
    presale_mom,
    presale_email_drafter,
    wbs_generator,
    retrospective,
    no_show_followup,
)

from agents.phase3 import (
    proposal_generator,
    meeting_prep_brief,
)

__all__ = [
    "junk_filter", "enrichment_structurer", "lead_scoring",
    "auto_ack_drafter", "follow_up_drafter", "reply_classifier", "client_mom",
    "ticket_gist", "daily_agenda", "presale_mom", "presale_email_drafter",
    "wbs_generator", "retrospective", "no_show_followup",
    "proposal_generator", "meeting_prep_brief",
]
