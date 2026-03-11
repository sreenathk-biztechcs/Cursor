"""
Agent 8 — TicketGistAgent
Model : Sonnet 4.6
Trigger: Presale ticket created in Odoo Projects (linked to a CRM lead)

Purpose:
    Synthesize the entire lead history — emails, notes, MOMs, enrichment —
    into a structured "gist" that onboards the presale team instantly.
    This is the first note on every presale ticket.

Input dict keys:
    lead_id          (int)   : Odoo lead ID
    ticket_id        (str)   : Presale ticket number (e.g. "PST-1042")
    client_company   (str)   : Client company name
    email_thread     (list)  : List of dicts [{date, from, subject, body, direction}]
                                direction: "inbound"|"outbound"
    internal_notes   (list)  : List of dicts [{date, author, content}]
    meeting_moms     (list)  : List of MOM strings from ClientMOMAgent
    enriched_fields  (dict)  : EnrichmentStructurerAgent output
    lead_score       (int)   : 0–100
    lead_score_band  (str)   : "hot"|"warm"|"neutral"|"cold"
    days_in_pipeline (int)   : Days from lead creation to ticket creation

Output dict:
    gist_markdown   : str — full gist as markdown (posted to ticket)
    open_questions  : list[str] — questions the presale team must resolve
    risk_flags      : list[str] — any red flags or concerns
    recommended_approach : str — suggested presale strategy
"""

from __future__ import annotations
import json

from agents.base import get_client, log_call, usage
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS

AGENT_NAME = "TicketGistAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = """You are a senior presale consultant. A new presale ticket has been
created. Your job is to write a comprehensive "Gist" that gives the presale team
everything they need to understand this deal in 2 minutes.

GIST STRUCTURE (use this exact markdown structure):

## Client Overview
[Company, industry, size, location — 2 sentences]

## What They're Looking For
[What they want — be specific, use their own words where possible]

## Key Requirements Identified
[Bulleted list — be concrete, not vague]

## Prior Discussions Summary
[Timeline of key touchpoints — what was said, what was agreed]

## Open Questions (must resolve in first presale meeting)
[Numbered list]

## Budget & Timeline Signals
[What was hinted at — NO specific $ amounts. Describe as "tight/moderate/flexible"]

## Risk Flags
[Any concerns: vague requirements, decision committee, competitor mentioned, etc.]

## Recommended Presale Approach
[How to structure the first presale meeting]

RULES:
- Strip all specific financial figures. Use "budget discussed" or "investment discussed".
- Be factual. Don't editorialize.
- If something is unknown, say "Not yet determined."
- Total gist should be 400–600 words.

OUTPUT FORMAT — respond with ONLY valid JSON:
{
  "gist_markdown": "<full gist in markdown>",
  "open_questions": ["<list of specific questions>"],
  "risk_flags": ["<list of risks>"],
  "recommended_approach": "<1–2 sentence strategy>"
}
"""


def _build_email_thread_text(email_thread: list) -> str:
    lines = []
    for e in email_thread[:20]:  # cap at 20 emails
        direction = "→ CLIENT" if e.get("direction") == "inbound" else "← US"
        lines.append(
            f"[{e.get('date','')}] {direction}\n"
            f"Subject: {e.get('subject','')}\n"
            f"{e.get('body','')[:600]}\n"
        )
    return "\n---\n".join(lines) or "No emails."


def run(data: dict) -> dict:
    """Generate the presale ticket gist."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    enriched = data.get("enriched_fields", {})

    user_message = f"""Create the presale gist for ticket {data.get('ticket_id','')}.

ENRICHMENT DATA:
  Company    : {data.get('client_company', '')}
  Industry   : {enriched.get('company_industry', 'unknown')}
  Size       : {enriched.get('company_employee_count', 'unknown')} employees
  Revenue    : {enriched.get('company_revenue_range', 'unknown')}
  Geography  : {enriched.get('company_hq_city', '')}, {enriched.get('company_hq_country', '')}
  Contact    : {enriched.get('contact_job_title', 'unknown')} — {enriched.get('contact_seniority', '')}
  Likely pain: {enriched.get('likely_pain_point', 'unknown')}
  Inquiry cat: {enriched.get('inquiry_category', 'unknown')}
  ICP signals: {json.dumps(enriched.get('icp_match_signals', []))}
  Lead score : {data.get('lead_score', '?')}/100 ({data.get('lead_score_band', '')})
  Days in pipe: {data.get('days_in_pipeline', '?')} days

EMAIL THREAD:
{_build_email_thread_text(data.get('email_thread', []))}

INTERNAL NOTES:
{chr(10).join([f"[{n.get('date','')}] {n.get('author','')}: {n.get('content','')}" for n in data.get('internal_notes', [])]) or 'None.'}

MEETING MOMs:
{chr(10).join(data.get('meeting_moms', [])) or 'No meetings yet.'}
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
