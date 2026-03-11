"""
Agent 16 — ProposalGeneratorAgent
Model : Opus 4.6 (highest quality — used only for proposals)
Trigger: Rep clicks "Request Proposal from AI" on presale ticket
         (stage-gated: only available when stage = "Ready for Proposal")

Purpose:
    Generate a full sales proposal. n8n pulls the template structure from
    Google Drive, calls this agent, and writes the output back to Google Drive
    as a new document.

    Uses streaming (Opus with long output) to avoid timeout.

Input dict keys:
    lead_id              (int)   : Odoo lead ID
    ticket_id            (str)   : Presale ticket number
    client_company       (str)   : Client company name
    client_primary_contact(str)  : Name of decision maker
    client_designation   (str)   : Decision maker's title
    template_sections    (list)  : Section names from Google Drive template
    requirements         (list)  : Requirements from presale MOMs
    wbs_summary          (list)  : High-level WBS phases with task counts
    pricing_table        (list)  : [{item, qty, unit, amount}] — provided by presale
    tech_stack           (list)  : Recommended Odoo modules + integrations
    our_team_profiles    (list)  : [{name, role, experience_line}]
    timeline_weeks       (int)   : Total implementation timeline
    go_live_date         (str)   : Target go-live date
    enriched_fields      (dict)  : EnrichmentStructurerAgent output
    ticket_gist          (str)   : TicketGistAgent output (gist_markdown)
    all_presale_moms     (list)  : All presale MOM texts
    company_portfolio    (str)   : Our relevant case studies / portfolio
    rep_name             (str)   : Rep name (proposal cover)
    rep_designation      (str)   : Rep title

Output dict:
    proposal_sections : dict — {section_name: section_content}
    cover_page        : dict — {title, subtitle, date, prepared_by, prepared_for}
    executive_summary : str — standalone for email body if needed
    word_count        : int
"""

from __future__ import annotations
import json

import anthropic
from agents.base import get_client, log_call
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS, COMPANY_NAME, COMPANY_PORTFOLIO

AGENT_NAME = "ProposalGeneratorAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = f"""You are the lead presale consultant and proposal writer at
{COMPANY_NAME}, an Odoo implementation partner.

You are writing a full sales proposal that will be sent to the client.
This document represents our company — it must be polished, specific, and compelling.

PROPOSAL PHILOSOPHY:
- Every section must feel written FOR THIS CLIENT — not a template with placeholders.
- Reference their specific requirements, industry, and stated challenges.
- Use the client's own language and terms where possible.
- The proposal should answer: "Why you, why now, and why this scope?"
- Tone: confident, professional, consultative — not salesy.

RULES:
- No buzzwords: "cutting-edge", "state-of-the-art", "revolutionary".
- No vague promises. Every claim must be specific.
- Pricing section: use the exact pricing table provided — do not add or modify.
- Executive Summary: must be strong enough to stand alone (read by a CEO).
- Keep language accessible to non-technical stakeholders.
- Total proposal: 1800–2500 words.

PROPOSAL SECTIONS TO WRITE (follow the template structure provided):
You will be given a list of section names. Write each one fully.

OUTPUT FORMAT — respond with ONLY valid JSON:
{{
  "cover_page": {{
    "title": "<proposal title>",
    "subtitle": "<e.g. 'Odoo Implementation Proposal'>",
    "date": "<today's date>",
    "prepared_by": "<rep name, company>",
    "prepared_for": "<client name, company>"
  }},
  "proposal_sections": {{
    "<section_name>": "<full section content in markdown>"
  }},
  "executive_summary": "<standalone executive summary — 150 words>",
  "word_count": <int>
}}
"""


def run(data: dict) -> dict:
    """
    Generate the full proposal. Uses streaming due to long output (Opus 4.6).
    Returns structured proposal dict for n8n → Google Drive.
    """
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    enriched = data.get("enriched_fields", {})
    sections = data.get("template_sections", [
        "Executive Summary",
        "Understanding Your Requirements",
        "Our Proposed Solution",
        "Technical Architecture",
        "Implementation Approach",
        "Project Team",
        "Timeline & Milestones",
        "Investment",
        "Why Choose Us",
        "Next Steps",
    ])

    # Format pricing table
    pricing_text = "\n".join([
        f"  {p.get('item','')}: {p.get('qty','')} {p.get('unit','')} — {p.get('amount','')}"
        for p in data.get("pricing_table", [])
    ]) or "  [To be completed by presale team]"

    # Format team profiles
    team_text = "\n".join([
        f"  - {t.get('name','')}, {t.get('role','')}: {t.get('experience_line','')}"
        for t in data.get("our_team_profiles", [])
    ]) or "  [Team profiles to be added]"

    # Format WBS summary
    wbs_text = "\n".join([
        f"  {p.get('phase_name','')}: {p.get('task_count','?')} tasks"
        for p in data.get("wbs_summary", [])
    ]) or "  [WBS summary not provided]"

    user_message = f"""Write the complete proposal for this client.

CLIENT:
  Company  : {data.get('client_company', '')}
  Contact  : {data.get('client_primary_contact', '')} ({data.get('client_designation', '')})
  Industry : {enriched.get('company_industry', 'unknown')}
  Size     : {enriched.get('company_employee_count', 'unknown')} employees
  Location : {enriched.get('company_hq_city', '')}, {enriched.get('company_hq_country', '')}
  Pain     : {enriched.get('likely_pain_point', 'not specified')}

PROPOSAL SECTIONS TO WRITE (in this order):
{chr(10).join(['  ' + str(i+1) + '. ' + s for i, s in enumerate(sections)])}

REQUIREMENTS (from presale discussions):
{chr(10).join(['  - ' + r for r in data.get('requirements', [])]) or '  Not specified'}

RECOMMENDED TECH STACK:
{chr(10).join(['  - ' + t for t in data.get('tech_stack', [])]) or '  Not specified'}

WBS SUMMARY:
{wbs_text}

TIMELINE:
  Total   : {data.get('timeline_weeks', 'TBD')} weeks
  Go-live : {data.get('go_live_date', 'TBD')}

PRICING TABLE (use exactly as provided):
{pricing_text}

OUR TEAM:
{team_text}

OUR PORTFOLIO (reference relevant work):
{data.get('company_portfolio', COMPANY_PORTFOLIO)}

PRESALE CONTEXT (use to make proposal specific):
{data.get('ticket_gist', '')[:2000]}

FULL PRESALE MOMs (reference requirements from these):
{chr(10).join(data.get('all_presale_moms', []))[:3000]}

PREPARED BY:
  Name       : {data.get('rep_name', '')}
  Designation: {data.get('rep_designation', 'Account Executive')}
"""

    in_tok, out_tok = 0, 0
    full_text = ""

    try:
        # Use streaming — Opus with 16K output requires it to avoid timeouts
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS[MODEL],
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text_chunk in stream.text_stream:
                full_text += text_chunk

            final = stream.get_final_message()
            in_tok  = final.usage.input_tokens
            out_tok = final.usage.output_tokens

        result = extract_json(full_text)
        log_call(AGENT_NAME, MODEL, lead_id, in_tok, out_tok, success=True,
                 extra={"ticket_id": data.get("ticket_id"),
                        "word_count": result.get("word_count")})
        return result

    except Exception as exc:
        log_call(AGENT_NAME, MODEL, lead_id, in_tok, out_tok,
                 success=False, error=str(exc))
        raise
