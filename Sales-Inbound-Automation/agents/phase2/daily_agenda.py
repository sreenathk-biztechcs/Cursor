"""
Agent 9 — DailyAgendaAgent
Model : Haiku 4.5 (runs on ALL active tickets daily — must be cheap)
Trigger: Odoo scheduled action — daily at 10:00 AM

Purpose:
    Post a crisp daily agenda on each active presale ticket so every team
    member knows what to accomplish today before the 10:30 AM standup.

Input dict keys:
    lead_id           (int)  : Odoo lead ID (for logging)
    ticket_id         (str)  : Presale ticket number
    client_company    (str)  : Client name
    ticket_stage      (str)  : Current stage of the presale ticket
    recent_chatter    (list) : Dicts [{date, author, content, type}]
                               type: "note"|"email"|"mom"|"action_item"
                               (last 7 days only)
    open_action_items (list) : Unresolved action items from past MOMs
    next_meeting_date (str)  : ISO datetime of next scheduled meeting or null
    days_since_last_mom(int) : Days since last presale MOM

Output dict:
    agenda_markdown : str — today's agenda as markdown (posted to ticket)
    urgent_flag     : bool — True if something needs immediate attention
    urgent_reason   : str | null
"""

from __future__ import annotations

from agents.base import get_client, log_call, usage
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS

AGENT_NAME = "DailyAgendaAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = """You are a presale coordinator. Every morning you post a concise
daily agenda on each active presale ticket to prepare the team for the day.

AGENDA STRUCTURE (strict — use this markdown format):

## Daily Agenda — [TODAY'S DATE]

**Status:** [One line: where are we in the presale process?]

**Today's Goal:** [What must be achieved today — be specific]

**Carry-over Items (from last meeting):**
- [Open action items not yet resolved]

**Questions to Resolve Today:**
- [Any open questions that need answers from client or internal team]

**Prep Needed Before Next Meeting:** *(only if meeting is today or tomorrow)*
- [Documents, demos, technical prep required]

**Watch:** [Any risk or blocker that needs attention]

RULES:
- Max 200 words total.
- Be specific — no generic placeholders.
- If all action items are done and next meeting is >3 days away, keep it brief.
- If days_since_last_mom > 7 and no meeting scheduled, flag as urgent.

OUTPUT FORMAT — respond with ONLY valid JSON:
{
  "agenda_markdown": "<agenda in markdown — replace [TODAY'S DATE] with actual date>",
  "urgent_flag": <true|false>,
  "urgent_reason": "<reason if urgent, else null>"
}
"""

from datetime import date


def run(data: dict) -> dict:
    """Generate today's agenda for one presale ticket."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    # Format recent chatter
    chatter_text = "\n".join([
        f"[{c.get('date','')}] {c.get('author','')} ({c.get('type','note')}): "
        f"{c.get('content','')[:400]}"
        for c in data.get("recent_chatter", [])[-15:]  # last 15 items max
    ]) or "No recent activity."

    # Format open action items
    action_items_text = "\n".join([
        f"- {item}" for item in data.get("open_action_items", [])
    ]) or "- None outstanding"

    today = date.today().strftime("%d %b %Y")

    user_message = f"""Generate today's ({today}) agenda for presale ticket {data.get('ticket_id','')}.

CLIENT: {data.get('client_company', '')}
STAGE : {data.get('ticket_stage', 'unknown')}
NEXT MEETING: {data.get('next_meeting_date', 'Not scheduled')}
DAYS SINCE LAST MOM: {data.get('days_since_last_mom', 'unknown')}

OPEN ACTION ITEMS:
{action_items_text}

RECENT CHATTER (last 7 days):
{chatter_text}
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
