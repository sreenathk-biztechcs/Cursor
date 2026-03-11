"""
Agent 5 — FollowUpDrafterAgent
Model : Sonnet 4.6
Trigger: Scheduled Odoo job on each follow-up activity due date (Day 2/5/10)

Purpose:
    Draft the next follow-up email in the sequence. Each follow-up must be
    distinct in angle and tone — not a copy of the previous one.
    Pulls full email thread history to avoid repetition.

Input dict keys:
    lead_id             (int)   : Odoo lead ID
    client_name         (str)   : Contact first name
    client_company      (str)   : Company name
    client_role         (str)   : Job title
    followup_number     (int)   : 1, 2, or 3
    days_since_ack      (int)   : Days since auto-ack was sent
    original_inquiry    (str)   : Their original email
    emails_sent_so_far  (list)  : List of dicts [{subject, body, sent_date}]
    enriched_fields     (dict)  : EnrichmentStructurerAgent output
    rep_name            (str)   : Sales rep's full name
    rep_designation     (str)   : Rep's title
    rep_calendar_link   (str)   : Booking URL
    lead_score_band     (str)   : "hot"|"warm"|"neutral"|"cold"
    company_value_prop  (str)   : Our value prop (from config)
    rep_notes           (str)   : Any notes rep added to the lead chatter

Output dict:
    subject  : str
    body     : str (~80–120 words for FU1, ~100–150 for FU2, ~100–130 for FU3)
    angle    : str — the main value angle used in this follow-up
    cta      : str — the call to action used
"""

from __future__ import annotations
import json

from agents.base import get_client, log_call, usage
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS, COMPANY_NAME

AGENT_NAME = "FollowUpDrafterAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

FOLLOWUP_GUIDANCE = {
    1: {
        "label": "Follow-up 1 — Gentle check-in",
        "instructions": """
- Assume they were busy, not uninterested.
- Add ONE new angle not mentioned in the ack (e.g., a specific ROI signal,
  a relevant industry statistic, or a one-line case study reference).
- Keep it short: 80–100 words max.
- End with a soft CTA: "Would it make sense to jump on a 20-min call?"
- Do NOT resell. Be human.
""",
    },
    2: {
        "label": "Follow-up 2 — Value-driven nudge",
        "instructions": """
- Be more specific about their industry or company.
- Reference one concrete outcome a similar client achieved (keep vague if needed).
- Ask ONE specific question to prompt a reply — not a yes/no question.
- 100–130 words max.
- CTA: suggest a time or share the calendar link.
""",
    },
    3: {
        "label": "Follow-up 3 — Final respectful nudge",
        "instructions": """
- Acknowledge this is the last nudge — but keep the door open.
- Softer tone: "I'll leave it here for now, but happy to reconnect when timing works."
- Offer a reduced ask: "Even 15 minutes would be enough to see if there's a fit."
- 90–120 words max.
- No pressure, no guilt. Professional and warm.
""",
    },
}

SYSTEM_PROMPT = f"""You are a senior B2B sales rep at {COMPANY_NAME}. You write
follow-up emails that feel like they're from a real person — not a CRM sequence.

CORE RULES:
1. Never start with "I wanted to follow up" or "Just checking in."
2. Each follow-up must use a DIFFERENT angle from all previous emails.
3. Reference something specific from their original inquiry or company.
4. No bullet points. No hype. No generic phrases.
5. Sound like you genuinely believe you can help them — because you do.

OUTPUT FORMAT — respond with ONLY valid JSON:
{{
  "subject": "<subject line — different from all previous>",
  "body": "<email body — plain text>",
  "angle": "<the main value angle used in this email>",
  "cta": "<the call to action>"
}}
"""


def run(data: dict) -> dict:
    """Draft the follow-up email for the given followup_number."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")
    fu_num  = data.get("followup_number", 1)

    guidance = FOLLOWUP_GUIDANCE.get(fu_num, FOLLOWUP_GUIDANCE[1])
    enriched = data.get("enriched_fields", {})

    # Build prior emails summary
    prior_emails = data.get("emails_sent_so_far", [])
    prior_summary = "\n\n".join([
        f"Email {i+1} (sent {e.get('sent_date','')}):\n"
        f"Subject: {e.get('subject','')}\n"
        f"Body: {e.get('body','')[:500]}"
        for i, e in enumerate(prior_emails)
    ]) or "None sent yet."

    user_message = f"""Draft {guidance['label']}.

FOLLOW-UP INSTRUCTIONS:
{guidance['instructions']}

CLIENT:
  Name    : {data.get('client_name', 'there')}
  Company : {data.get('client_company', '')}
  Role    : {data.get('client_role', '') or 'unknown'}
  Industry: {enriched.get('company_industry', 'unknown')}
  Pain    : {enriched.get('likely_pain_point', 'not specified')}
  Score   : {data.get('lead_score_band', 'warm')}
  Days since first email: {data.get('days_since_ack', 'unknown')}

THEIR ORIGINAL INQUIRY:
{data.get('original_inquiry', '')[:1000]}

PRIOR EMAILS SENT (do NOT repeat these angles):
{prior_summary}

REP:
  Name        : {data.get('rep_name', '')}
  Designation : {data.get('rep_designation', 'Account Executive')}
  Calendar    : {data.get('rep_calendar_link', '[CALENDAR_LINK]')}

REP NOTES (if any):
{data.get('rep_notes', 'None')}

ENRICHMENT SIGNALS (use subtly):
  Follow-up angle: {enriched.get('follow_up_angle', 'not specified')}
  ICP signals    : {json.dumps(enriched.get('icp_match_signals', []))}
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
                 extra={"followup_number": fu_num})
        return result

    except Exception as exc:
        log_call(AGENT_NAME, MODEL, lead_id, 0, 0, success=False, error=str(exc))
        raise
