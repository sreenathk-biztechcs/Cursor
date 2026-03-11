"""
Agent 4 — AutoAckDrafterAgent
Model : Sonnet 4.6
Trigger: Immediately after lead is assigned to a rep

Purpose:
    Draft a personalized acknowledgment email that references the client's
    specific inquiry, adds one relevant value angle, and includes the rep's
    calendar link. Max 150 words. Must feel personal — not a template.

Input dict keys:
    lead_id            (int)  : Odoo lead ID
    client_name        (str)  : Contact first name (or "there" if unknown)
    client_company     (str)  : Company name
    client_role        (str)  : Job title if known
    original_inquiry   (str)  : Their email body
    enriched_fields    (dict) : EnrichmentStructurerAgent output
    rep_name           (str)  : Sales rep's full name
    rep_designation    (str)  : Rep's title (e.g. "Account Executive")
    rep_calendar_link  (str)  : Calendly/Cal.com booking URL
    company_value_prop (str)  : 1-2 lines about our company (from config)
    lead_score_band    (str)  : "hot"|"warm"|"neutral"|"cold"

Output dict:
    subject  : str — email subject line
    body     : str — full email body (plain text, ~100–150 words)
    tone_used: str — brief note on tone chosen
"""

from __future__ import annotations

from agents.base import get_client, log_call, get_text, usage
from agents.config import MODEL_MAP, MAX_TOKENS, COMPANY_NAME

AGENT_NAME = "AutoAckDrafterAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = f"""You are a senior B2B sales rep at {COMPANY_NAME}, an Odoo
implementation partner. Your task is to draft the very first reply to an inbound
lead inquiry.

MANDATORY RULES:
1. Max 150 words in the email body. Every word must earn its place.
2. Open by acknowledging something SPECIFIC from their actual inquiry —
   never a generic "Thanks for reaching out."
3. Add exactly ONE relevant value angle (not already in their inquiry).
4. Include the rep's calendar link with a natural CTA.
5. End with the rep's name and designation.
6. NO hype words: "revolutionary", "cutting-edge", "game-changer", "excited".
7. NO bullet points. Flowing prose only.
8. Tone: warm, confident, professional — like a trusted advisor, not a vendor.

OUTPUT FORMAT — respond with ONLY valid JSON:
{{
  "subject": "<email subject — specific, not generic>",
  "body": "<full email body — plain text, no HTML>",
  "tone_used": "<one phrase: e.g. 'consultative and brief'>"
}}
"""


def run(data: dict) -> dict:
    """Draft the acknowledgment email. Returns subject + body dict."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    enriched = data.get("enriched_fields", {})
    pain_point = enriched.get("likely_pain_point") or "their operational challenge"
    inquiry_category = enriched.get("inquiry_category", "general inquiry")

    user_message = f"""Draft the first acknowledgment email for this lead.

CLIENT DETAILS:
  Name       : {data.get('client_name', 'there')}
  Company    : {data.get('client_company', '')}
  Role       : {data.get('client_role', '') or 'not specified'}
  Industry   : {enriched.get('company_industry', 'not specified')}
  Likely pain: {pain_point}
  Inquiry type: {inquiry_category}

THEIR ORIGINAL INQUIRY:
{data.get('original_inquiry', '')[:2000]}

REP DETAILS:
  Name        : {data.get('rep_name', '')}
  Designation : {data.get('rep_designation', 'Account Executive')}
  Calendar    : {data.get('rep_calendar_link', '[CALENDAR_LINK]')}

OUR VALUE PROP (use sparingly, weave in naturally):
{data.get('company_value_prop', '')}

Lead score band: {data.get('lead_score_band', 'warm')}
(For hot leads, be a bit more direct and suggest a specific slot.)
"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS[MODEL],
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        in_tok, out_tok = usage(response)

        from agents.base.output_parser import extract_json
        result = extract_json(response.content[0].text)
        log_call(AGENT_NAME, MODEL, lead_id, in_tok, out_tok, success=True)
        return result

    except Exception as exc:
        log_call(AGENT_NAME, MODEL, lead_id, 0, 0, success=False, error=str(exc))
        raise
