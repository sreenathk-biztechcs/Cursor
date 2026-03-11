"""
Agent 10 — PresaleMOMAgent
Model : Sonnet 4.6
Trigger: Presale meeting transcript available + ticket # identified from transcript

Purpose:
    Generate an INTERNAL presale MOM from the meeting transcript.
    This goes directly to the presale ticket chatter (internal note).
    Financial figures are stripped. Technical detail is preserved.

    The n8n "Presale MOM Splitter" workflow identifies the ticket # from the
    transcript (rep says "Moving to ticket 1042") and routes accordingly.

Input dict keys:
    lead_id           (int)  : Odoo lead ID
    ticket_id         (str)  : Presale ticket number
    transcript        (str)  : Full presale meeting transcript
    meeting_date      (str)  : ISO date
    meeting_duration  (int)  : Duration in minutes
    attendees         (list) : [{name, role, company, is_client}]
    ticket_context    (str)  : Brief context of the ticket (gist summary)
    prior_open_items  (list) : Open action items from previous presale MOMs
    presale_stage     (str)  : Current presale stage

Output dict:
    internal_mom_markdown : str — full presale MOM (markdown, for ticket)
    resolved_items        : list[str] — prior open items now resolved
    new_action_items_us   : list[str] — new action items for our team
    new_action_items_client: list[str] — new action items for client
    new_open_questions    : list[str] — questions raised, not yet answered
    technical_decisions   : list[str] — architecture/tech decisions made
    stage_recommendation  : str — should presale stage advance?
"""

from __future__ import annotations

from agents.base import get_client, log_call, usage
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS

AGENT_NAME = "PresaleMOMAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = """You are a senior presale consultant documenting a client presale
meeting. Write a comprehensive INTERNAL minutes of meeting (MOM) for the presale team.

MOM STRUCTURE (use this markdown format):

## Presale MOM — [TICKET_ID] — [DATE]

**Duration:** X minutes | **Stage:** [stage]

### Attendees
[List with names, roles, companies]

### Agenda Covered
[What was actually discussed, numbered]

### Key Requirements Discussed
[New or refined requirements — be technical and specific]

### Technical Decisions Made
[Architecture, modules, integrations, platforms confirmed]

### Open Questions Raised
[Questions not yet answered — include who should answer]

### Action Items
**Our Team:**
- [ ] [Task] — Owner: [name] — Due: [date or "next meeting"]

**Client:**
- [ ] [Task] — Owner: [name] — Due: [date or "next meeting"]

### Prior Items Status
[Which prior action items were resolved or discussed]

### Presale Stage Notes
[Recommendation on whether to advance stage]

RULES:
- Strip ALL financial figures (budgets, pricing, quotes). Replace with "[discussed]".
- Be specific on technical requirements — exact module names, integration points.
- Use the client's exact words for requirements where possible (in quotes).
- Flag any scope creep signals.
- Total: 400–700 words.

OUTPUT FORMAT — respond with ONLY valid JSON:
{
  "internal_mom_markdown": "<full MOM in markdown>",
  "resolved_items": ["<prior items resolved>"],
  "new_action_items_us": ["<our team action items>"],
  "new_action_items_client": ["<client action items>"],
  "new_open_questions": ["<unresolved questions>"],
  "technical_decisions": ["<decisions made>"],
  "stage_recommendation": "<advance|stay|escalate — with brief reason>"
}
"""


def run(data: dict) -> dict:
    """Generate presale MOM from transcript."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    attendees_text = "\n".join([
        f"  - {a.get('name','?')} ({a.get('role','?')}, {a.get('company','?')}) "
        f"{'[CLIENT]' if a.get('is_client') else '[OUR TEAM]'}"
        for a in data.get("attendees", [])
    ])

    prior_items_text = "\n".join([
        f"  - {item}" for item in data.get("prior_open_items", [])
    ]) or "  None"

    user_message = f"""Generate the presale MOM for ticket {data.get('ticket_id','')}.

MEETING DETAILS:
  Date     : {data.get('meeting_date', '')}
  Duration : {data.get('meeting_duration', '?')} minutes
  Stage    : {data.get('presale_stage', 'unknown')}

ATTENDEES:
{attendees_text}

TICKET CONTEXT (summary):
{data.get('ticket_context', 'No prior context available.')}

PRIOR OPEN ACTION ITEMS (check if resolved in this meeting):
{prior_items_text}

FULL TRANSCRIPT:
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
        log_call(AGENT_NAME, MODEL, lead_id, in_tok, out_tok, success=True,
                 extra={"ticket_id": data.get("ticket_id")})
        return result

    except Exception as exc:
        log_call(AGENT_NAME, MODEL, lead_id, 0, 0, success=False, error=str(exc))
        raise
