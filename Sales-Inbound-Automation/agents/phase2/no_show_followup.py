"""
Agent 14 — NoShowFollowUpAgent
Model : Sonnet 4.6
Trigger: Rep marks a scheduled meeting as "No Show" in Odoo Calendar

Purpose:
    Draft a professional, non-pushy no-show follow-up email.
    Tone: understanding, offers easy reschedule, keeps the door open.
    Must feel human — not a canned "you missed our meeting" template.

Input dict keys:
    lead_id            (int)  : Odoo lead ID
    client_name        (str)  : Client contact first name
    client_company     (str)  : Client company name
    meeting_date       (str)  : ISO date/time of the missed meeting
    meeting_topic      (str)  : What the meeting was about
    enriched_fields    (dict) : EnrichmentStructurerAgent output
    rep_name           (str)  : Rep's name
    rep_designation    (str)  : Rep's title
    rep_calendar_link  (str)  : Booking URL for easy reschedule
    prior_interaction  (str)  : Brief summary of prior emails/context
    lead_score_band    (str)  : "hot"|"warm"|"neutral"|"cold"
    no_show_count      (int)  : How many times they've no-showed (1 = first time)

Output dict:
    subject : str
    body    : str (~80–120 words — brief and gracious)
    tone    : str — brief note on tone chosen
"""

from __future__ import annotations

from agents.base import get_client, log_call, usage
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS, COMPANY_NAME

AGENT_NAME = "NoShowFollowUpAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = f"""You are a senior B2B sales rep at {COMPANY_NAME}.
A client missed a scheduled meeting. Draft a gracious, brief follow-up.

TONE RULES BY NO-SHOW COUNT:
  1st no-show: Completely understanding. "Things come up." Easy reschedule CTA.
  2nd no-show: Still warm, but subtly note this is the second attempt.
               Ask if timing/priority has changed.
  3rd+ no-show: Very gentle check-in. Offer to pause outreach if timing isn't right.
               Leave door fully open. No frustration.

RULES:
- Max 120 words. Every word matters.
- Never say "you missed our meeting" — say "we didn't get to connect" or "our time didn't work out."
- Include a specific reschedule CTA with the calendar link.
- No guilt, no passive aggression, no corporate coldness.
- Sound like a real person who genuinely wants to help.

OUTPUT FORMAT — respond with ONLY valid JSON:
{{
  "subject": "<subject line — not 'Missed Meeting'>",
  "body": "<email body — plain text>",
  "tone": "<one phrase describing tone chosen>"
}}
"""


def run(data: dict) -> dict:
    """Draft the no-show follow-up email."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")
    count   = data.get("no_show_count", 1)

    enriched = data.get("enriched_fields", {})

    user_message = f"""Draft a no-show follow-up email. This is no-show #{count}.

CLIENT:
  Name    : {data.get('client_name', 'there')}
  Company : {data.get('client_company', '')}
  Industry: {enriched.get('company_industry', 'unknown')}
  Score   : {data.get('lead_score_band', 'warm')}

MISSED MEETING:
  Date   : {data.get('meeting_date', '')}
  Topic  : {data.get('meeting_topic', 'discovery call')}

PRIOR CONTEXT:
{data.get('prior_interaction', 'No additional context.')}

REP:
  Name       : {data.get('rep_name', '')}
  Designation: {data.get('rep_designation', 'Account Executive')}
  Calendar   : {data.get('rep_calendar_link', '[CALENDAR_LINK]')}
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
        log_call(AGENT_NAME, MODEL, lead_id, in_tok, out_tok, success=True,
                 extra={"no_show_count": count})
        return result

    except Exception as exc:
        log_call(AGENT_NAME, MODEL, lead_id, 0, 0, success=False, error=str(exc))
        raise
