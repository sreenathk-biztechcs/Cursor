"""
Agent 7 — ClientMOMAgent
Model : Sonnet 4.6
Trigger: n8n webhook after Apollo meeting transcript is fetched by Playwright

Purpose:
    Generate two artifacts from a meeting transcript:
    1. An INTERNAL MOM (full detail, for lead chatter — client never sees this)
    2. A CLIENT EMAIL (professional summary — rep reviews before sending)

    Financial figures are excluded from both artifacts per company policy.

Input dict keys:
    lead_id          (int)  : Odoo lead ID
    transcript       (str)  : Full meeting transcript text from Apollo
    meeting_date     (str)  : ISO date of the meeting
    meeting_duration (int)  : Duration in minutes
    attendees        (list) : List of dicts [{name, role, company, is_client}]
    rep_name         (str)  : Rep who attended (email sender)
    rep_designation  (str)  : Rep's title
    rep_calendar_link(str)  : Calendar link for next meeting
    client_company   (str)  : Client company name
    enriched_fields  (dict) : Enrichment data for context

Output dict:
    internal_mom          : str — full internal MOM (markdown)
    client_email_subject  : str — email subject
    client_email_body     : str — client-facing email body (plain text)
    action_items_rep      : list[str] — action items for our team
    action_items_client   : list[str] — action items for the client
    next_meeting_suggested: bool — whether to suggest next meeting
"""

from __future__ import annotations
import json

from agents.base import get_client, log_call, usage
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS, COMPANY_NAME

AGENT_NAME = "ClientMOMAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = f"""You are a senior consultant at {COMPANY_NAME}. After a client
discovery meeting, you write two documents:

1. INTERNAL MOM — comprehensive notes for the sales/presale team.
   Include: pain points, requirements, objections, client sentiment, risk signals.
   Be detailed. Include direct quotes where helpful. Max 600 words.

2. CLIENT EMAIL — a professional summary the rep sends to the client.
   Tone: warm, clear, action-oriented. Shows the client we listened carefully.
   Include: what was discussed, next steps (numbered), action items for each party.
   Max 400 words. NO internal commentary, NO financial figures, NO speculation.

CRITICAL: Strip all financial figures ($ amounts, budgets, pricing discussed)
from BOTH documents. Replace with "[discussed internally]" if needed.

OUTPUT FORMAT — respond with ONLY valid JSON:
{{
  "internal_mom": "<full internal MOM in markdown — no financial figures>",
  "client_email_subject": "<subject line>",
  "client_email_body": "<client-facing email — plain text, no HTML>",
  "action_items_rep": ["<list of our team's action items>"],
  "action_items_client": ["<list of client's action items>"],
  "next_meeting_suggested": <true|false>
}}
"""


def run(data: dict) -> dict:
    """Generate internal MOM and client email from transcript."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    # Format attendees
    attendees_text = "\n".join([
        f"  - {a.get('name','?')} ({a.get('role','?')}, {a.get('company','?')}) "
        f"{'[CLIENT]' if a.get('is_client') else '[OUR TEAM]'}"
        for a in data.get("attendees", [])
    ]) or "  Not specified"

    user_message = f"""Generate the internal MOM and client email for this meeting.

MEETING DETAILS:
  Date     : {data.get('meeting_date', '')}
  Duration : {data.get('meeting_duration', '?')} minutes
  Client   : {data.get('client_company', '')}
  Attendees:
{attendees_text}

REP SENDING EMAIL:
  Name       : {data.get('rep_name', '')}
  Designation: {data.get('rep_designation', 'Account Executive')}
  Calendar   : {data.get('rep_calendar_link', '[CALENDAR_LINK]')}

ENRICHMENT CONTEXT (for internal MOM):
  Industry   : {data.get('enriched_fields', {}).get('company_industry', 'unknown')}
  Pain point : {data.get('enriched_fields', {}).get('likely_pain_point', 'unknown')}

FULL MEETING TRANSCRIPT:
{data.get('transcript', '')[:8000]}
"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS[MODEL],
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        in_tok, out_tok = usage(response)
        result = extract_json(response.content[0].text)
        log_call(AGENT_NAME, MODEL, lead_id, in_tok, out_tok, success=True)
        return result

    except Exception as exc:
        log_call(AGENT_NAME, MODEL, lead_id, 0, 0, success=False, error=str(exc))
        raise
