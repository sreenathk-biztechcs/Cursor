"""
Agent 15 — MeetingPrepBriefAgent
Model : Sonnet 4.6
Trigger: 2 hours before a scheduled CRM meeting (Odoo scheduled action)

Purpose:
    Draft a concise pre-meeting brief for the sales rep.
    Gives the rep everything they need in a 2-minute read before the call:
    client snapshot, likely objections, talking points, prior context.
    Posted as internal note on the lead.

Input dict keys:
    lead_id            (int)  : Odoo lead ID
    client_name        (str)  : Client contact first name
    client_company     (str)  : Client company name
    client_role        (str)  : Contact's job title
    meeting_type       (str)  : "discovery"|"demo"|"follow-up"|"presale"|"commercial"
    meeting_duration   (int)  : Duration in minutes
    meeting_agenda     (str)  : Agenda if set, else ""
    enriched_fields    (dict) : EnrichmentStructurerAgent output
    email_thread       (list) : [{date, from, subject, body, direction}] — last 5
    lead_score         (int)  : 0–100
    rep_name           (str)  : Rep's name
    prior_moms         (list) : Summaries of prior meeting MOMs (if any)
    open_questions     (list) : Open questions from the lead/ticket

Output dict:
    brief_markdown     : str — full prep brief (markdown, internal note)
    top_talking_points : list[str] — top 3 points to land in this meeting
    likely_objections  : list[str] — objections to prepare for (with hints)
    must_ask_questions : list[str] — questions rep must ask today
"""

from __future__ import annotations

from agents.base import get_client, log_call, usage
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS

AGENT_NAME = "MeetingPrepBriefAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = """You are an expert sales coach. 2 hours before a meeting,
you give the rep a sharp pre-meeting brief that takes 2 minutes to read.

BRIEF STRUCTURE (strict markdown):

## Meeting Prep — [CLIENT] — [MEETING TYPE] — [DATE]
**Duration:** X min | **Contact:** [name, role]

### Client Snapshot (30 seconds)
[Industry, size, what they do, why they reached out — 3 lines max]

### What They're Trying to Achieve
[Their stated + inferred goal for this meeting]

### Top 3 Talking Points
1. [Most important thing to land]
2. [Second point]
3. [Third point]

### Likely Objections & How to Handle
- **[Objection]:** [Brief handling hint]

### Questions You Must Ask Today
- [Specific discovery/qualifying questions]

### What Success Looks Like After This Call
[What's the ideal outcome — next step agreed, requirement clarified, etc.]

### Quick Context Reminder
[1–2 lines on how we got here — relevant email/prior meeting context]

RULES:
- Total: max 300 words.
- Be specific to THIS client — no generic sales tips.
- Objections should be based on actual signals from the email thread.
- Questions must be open-ended and strategic.

OUTPUT FORMAT — respond with ONLY valid JSON:
{
  "brief_markdown": "<full brief in markdown>",
  "top_talking_points": ["<3 talking points>"],
  "likely_objections": ["<objection: hint>"],
  "must_ask_questions": ["<question>"]
}
"""


def run(data: dict) -> dict:
    """Generate the pre-meeting brief for the rep."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    enriched = data.get("enriched_fields", {})

    # Build recent email context
    recent_emails = "\n".join([
        f"[{e.get('date','')}] {'CLIENT' if e.get('direction')=='inbound' else 'US'} "
        f"— {e.get('subject','')}: {e.get('body','')[:300]}"
        for e in data.get("email_thread", [])[-5:]
    ]) or "No emails."

    prior_moms_text = "\n".join(data.get("prior_moms", [])) or "No prior meetings."

    user_message = f"""Generate the meeting prep brief.

MEETING:
  Type    : {data.get('meeting_type', 'discovery')}
  Duration: {data.get('meeting_duration', 60)} minutes
  Agenda  : {data.get('meeting_agenda', 'Not set')}
  Rep     : {data.get('rep_name', '')}

CLIENT:
  Name    : {data.get('client_name', '')}
  Company : {data.get('client_company', '')}
  Role    : {data.get('client_role', 'unknown')}
  Industry: {enriched.get('company_industry', 'unknown')}
  Size    : {enriched.get('company_employee_count', 'unknown')} employees
  Pain    : {enriched.get('likely_pain_point', 'unknown')}
  Score   : {data.get('lead_score', '?')}/100

OPEN QUESTIONS TO RESOLVE:
{chr(10).join(['- ' + q for q in data.get('open_questions', [])]) or '- None noted'}

RECENT EMAIL THREAD:
{recent_emails}

PRIOR MEETING MOMs:
{prior_moms_text}
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
