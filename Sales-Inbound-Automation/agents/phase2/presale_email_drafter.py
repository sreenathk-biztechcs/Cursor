"""
Agent 11 — PresaleEmailDrafterAgent
Model : Sonnet 4.6
Trigger: After PresaleMOMAgent generates the internal MOM

Purpose:
    Draft the CLIENT-FACING email after each presale meeting.
    This goes to the CRM lead (not the ticket) for rep review before sending.
    Tone: professional summary + clear next steps for the client.

Input dict keys:
    lead_id              (int)  : Odoo lead ID
    ticket_id            (str)  : Presale ticket number
    client_name          (str)  : Primary client contact name
    client_company       (str)  : Client company name
    meeting_date         (str)  : ISO date
    internal_mom         (str)  : Output from PresaleMOMAgent (internal MOM text)
    action_items_client  (list) : Client's action items from PresaleMOMAgent
    next_meeting_proposed(str)  : Proposed next meeting date/time or null
    rep_name             (str)  : Rep sending the email
    rep_designation      (str)  : Rep's title
    rep_calendar_link    (str)  : Booking URL
    presale_stage        (str)  : Current stage

Output dict:
    subject : str
    body    : str — client-facing email (plain text, 200–300 words)
"""

from __future__ import annotations

from agents.base import get_client, log_call, usage
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS, COMPANY_NAME

AGENT_NAME = "PresaleEmailDrafterAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = f"""You are a senior presale consultant at {COMPANY_NAME}.
After each presale meeting, you write a professional follow-up email to the client.

PURPOSE OF THIS EMAIL:
1. Confirm what was discussed (high-level — not a technical dump)
2. State the client's action items clearly (numbered)
3. State our team's commitments clearly
4. Propose or confirm the next step

TONE: Professional but warm. Clear and crisp. Shows the client we are organized
and they can trust us to deliver.

RULES:
- Max 300 words.
- NO internal jargon. NO financial figures.
- Do NOT include technical architecture details (those are internal).
- Use plain English — the email may be read by non-technical stakeholders.
- End with the rep's name, title, and a clear next step.

OUTPUT FORMAT — respond with ONLY valid JSON:
{{
  "subject": "<Meeting summary: [Client Company] — [Date]>",
  "body": "<full email body — plain text, no HTML>"
}}
"""


def run(data: dict) -> dict:
    """Draft the client email after a presale meeting."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    # Format client action items
    client_items = "\n".join([
        f"  {i+1}. {item}"
        for i, item in enumerate(data.get("action_items_client", []))
    ]) or "  None at this time."

    # Extract client-friendly summary from internal MOM
    # Pass the full MOM but instruct agent to write client-friendly version
    user_message = f"""Draft the post-presale-meeting email to the client.

CLIENT:
  Name   : {data.get('client_name', 'Team')}
  Company: {data.get('client_company', '')}

MEETING DATE: {data.get('meeting_date', '')}
PRESALE STAGE: {data.get('presale_stage', '')}

INTERNAL MOM (use this to understand what was discussed, but DO NOT copy it verbatim
— write a client-friendly version):
{data.get('internal_mom', '')[:3000]}

CLIENT ACTION ITEMS (include these clearly in the email):
{client_items}

NEXT STEP: {data.get('next_meeting_proposed', 'To be scheduled — include calendar link')}

REP:
  Name       : {data.get('rep_name', '')}
  Designation: {data.get('rep_designation', 'Presale Consultant')}
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
                 extra={"ticket_id": data.get("ticket_id")})
        return result

    except Exception as exc:
        log_call(AGENT_NAME, MODEL, lead_id, 0, 0, success=False, error=str(exc))
        raise
