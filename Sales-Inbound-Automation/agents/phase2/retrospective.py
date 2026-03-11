"""
Agent 13 — RetrospectiveAgent
Model : Sonnet 4.6
Trigger: Lead marked "Won" or "Lost" in Odoo CRM

Purpose:
    Generate a full deal retrospective when a lead is closed.
    Won deals get a "why we won" analysis. Lost deals get a learning-focused
    "what we could have done differently" analysis.
    Posted to the presale ticket (or lead if no ticket).

Input dict keys:
    lead_id              (int)   : Odoo lead ID
    ticket_id            (str)   : Presale ticket number (or null)
    outcome              (str)   : "won" | "lost"
    win_loss_reason      (str)   : Reason entered by rep in Odoo
    client_company       (str)   : Client company name
    deal_value_band      (str)   : "small"|"medium"|"large"|"enterprise" (no $ amounts)
    rep_name             (str)   : Rep who owned the deal
    lead_score           (int)   : Lead score at time of scoring
    lead_score_band      (str)   : "hot"|"warm"|"neutral"|"cold"
    days_to_close        (int)   : Days from lead creation to close
    pipeline_stage_history(list) : [{stage, entered_date, days_in_stage}]
    email_thread         (list)  : [{date, from, subject, body, direction}]
    meeting_count        (int)   : Number of discovery/presale meetings
    presale_meeting_count(int)   : Number of presale-specific meetings
    internal_notes       (list)  : Internal chatter notes
    proposal_sent        (bool)  : Whether a proposal was sent

Output dict:
    retro_markdown   : str — full retrospective (markdown)
    key_learnings    : list[str] — 3–5 bullet learnings for the team
    replication_tips : list[str] — (WON only) what to replicate for similar leads
    watch_outs       : list[str] — (LOST only) early warning signals missed
    stage_bottleneck : str | null — stage where deal stalled the longest
"""

from __future__ import annotations
import json

from agents.base import get_client, log_call, usage
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS

AGENT_NAME = "RetrospectiveAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

WON_PROMPT = """Analyze why this deal was won. Be honest and specific.

RETRO STRUCTURE FOR WON DEALS:

## Deal Retrospective — WON ✓
**Client:** [name] | **Deal size:** [band] | **Closed by:** [rep]

### Why We Won
[3–5 specific reasons based on the evidence in the deal history]

### Key Turning Points
[Moments in the deal that made the difference]

### What Worked Well
- Approach / messaging
- Timing
- Technical fit
- Relationship building

### Client's Primary Decision Driver
[The #1 reason they chose us, based on evidence]

### Deal Velocity Analysis
[X days from lead to close. Which stages were quick, which were slow?]

### What to Replicate for Similar Leads
[Specific, actionable advice — not generic best practices]

### Risk That Almost Derailed the Deal
[Any close calls — what nearly went wrong]
"""

LOST_PROMPT = """Analyze why this deal was lost. Be honest and constructive.

RETRO STRUCTURE FOR LOST DEALS:

## Deal Retrospective — LOST ✗
**Client:** [name] | **Deal size:** [band] | **Rep:** [rep]

### Most Likely Reason We Lost
[Based on the evidence — not just the rep's stated reason]

### Early Warning Signals (that we missed or ignored)
[Signals from the emails/meetings that indicated risk]

### Where the Deal Stalled
[Which stage had the longest delay and why]

### What Could Have Been Done Differently
[Specific, actionable — per stage if possible]

### Competitor / Alternative Analysis
[Any competitor mentioned? What might they have offered differently?]

### Price / Scope / Timing Sensitivity
[Was this a price issue, scope mismatch, or timing problem?]

### Should We Have Disqualified Earlier?
[Honest assessment — did we waste time on a poor-fit lead?]
"""

BASE_SYSTEM = """You are a senior sales coach writing a deal retrospective.
Be specific, evidence-based, and constructive. Use the deal history provided.
Do NOT use generic sales advice — every point must be grounded in THIS deal's data.
No financial figures. Replace with "deal size" or "investment discussed".

OUTPUT FORMAT — respond with ONLY valid JSON:
{
  "retro_markdown": "<full retrospective in markdown>",
  "key_learnings": ["<3-5 specific learnings>"],
  "replication_tips": ["<won only — what to replicate>"],
  "watch_outs": ["<lost only — early signals missed>"],
  "stage_bottleneck": "<stage name where deal stalled longest or null>"
}
"""


def _build_stage_history(stages: list) -> str:
    return "\n".join([
        f"  {s.get('stage','?')}: {s.get('days_in_stage','?')} days"
        for s in stages
    ]) or "  Not tracked."


def _build_email_summary(emails: list) -> str:
    return "\n".join([
        f"  [{e.get('date','')}] {'→ CLIENT' if e.get('direction')=='inbound' else '← US'} "
        f"— {e.get('subject','')[:60]}"
        for e in emails[:15]
    ]) or "  No emails."


def run(data: dict) -> dict:
    """Generate the deal retrospective."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")
    outcome = data.get("outcome", "lost").lower()

    outcome_prompt = WON_PROMPT if outcome == "won" else LOST_PROMPT
    system_prompt  = BASE_SYSTEM + "\n\n" + outcome_prompt

    user_message = f"""Write the retrospective for this {outcome.upper()} deal.

DEAL SUMMARY:
  Client         : {data.get('client_company', '')}
  Outcome        : {outcome.upper()}
  Rep            : {data.get('rep_name', '')}
  Rep's reason   : {data.get('win_loss_reason', 'Not specified')}
  Deal size band : {data.get('deal_value_band', 'unknown')}
  Lead score     : {data.get('lead_score', '?')}/100 ({data.get('lead_score_band', '')})
  Days to close  : {data.get('days_to_close', '?')} days
  Meetings held  : {data.get('meeting_count', '?')} discovery + {data.get('presale_meeting_count','?')} presale
  Proposal sent  : {'Yes' if data.get('proposal_sent') else 'No'}

PIPELINE STAGE HISTORY:
{_build_stage_history(data.get('pipeline_stage_history', []))}

EMAIL THREAD TIMELINE:
{_build_email_summary(data.get('email_thread', []))}

INTERNAL NOTES:
{chr(10).join(['  [' + n.get('date','') + '] ' + n.get('author','') + ': ' + n.get('content','')[:300] for n in data.get('internal_notes',[])]) or '  None.'}
"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS[MODEL],
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        in_tok, out_tok = usage(response)
        result = extract_json(response.content[0].text)
        log_call(AGENT_NAME, MODEL, lead_id, in_tok, out_tok, success=True,
                 extra={"outcome": outcome, "ticket_id": data.get("ticket_id")})
        return result

    except Exception as exc:
        log_call(AGENT_NAME, MODEL, lead_id, 0, 0, success=False, error=str(exc))
        raise
