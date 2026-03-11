"""
Agent 2 — EnrichmentStructurerAgent
Model : Haiku 4.5
Trigger: n8n webhook after Apollo Playwright scrape completes

Purpose:
    Take raw Apollo data (JSON dump from Playwright scrape) and structure it
    into exactly 30 Odoo lead fields. Handles missing data gracefully.

Input dict keys:
    lead_id          (int)  : Odoo lead ID
    apollo_raw       (dict) : Raw JSON from Apollo scrape (company + contact)
    original_inquiry (str)  : The lead's original email body (for context)

Output dict: 30 structured fields (see FIELD_SCHEMA below).
    All fields default to None if data is unavailable.
    enrichment_confidence: int 0–100 (how complete the data is)
    enrichment_notes: str (what was missing or inferred)
"""

from __future__ import annotations
import json

from agents.base import get_client, log_call, extract_json, usage
from agents.config import MODEL_MAP, MAX_TOKENS

AGENT_NAME = "EnrichmentStructurerAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = """You are a data extraction specialist. You receive raw Apollo.io
profile data (company + contact) and must extract/infer 30 structured fields
for a CRM lead record.

OUTPUT FORMAT — respond with ONLY valid JSON matching exactly this schema.
Use null for any field you cannot determine. Do NOT guess or fabricate data:

{
  "company_industry":        "<string or null>",
  "company_sub_industry":    "<string or null>",
  "company_employee_count":  "<range string e.g. '51-200' or null>",
  "company_revenue_range":   "<range string e.g. '$10M-$50M' or null>",
  "company_hq_country":      "<string or null>",
  "company_hq_city":         "<string or null>",
  "company_founded_year":    "<int or null>",
  "company_tech_stack":      ["<list of tech strings>"],
  "company_funding_stage":   "<string or null>",
  "company_linkedin_url":    "<url or null>",
  "company_website":         "<url or null>",
  "contact_job_title":       "<string or null>",
  "contact_seniority":       "<C-Level|VP|Director|Manager|IC|Unknown>",
  "contact_email_verified":  "<email or null>",
  "contact_phone":           "<phone or null>",
  "contact_linkedin_url":    "<url or null>",
  "contact_is_decision_maker": "<true|false|null>",
  "likely_pain_point":       "<1-sentence inference from inquiry + profile or null>",
  "similar_clients_won":     "<industry/size match note or null>",
  "icp_match_signals":       ["<list of positive signals>"],
  "icp_disqualify_signals":  ["<list of red flags>"],
  "apollo_conversation_history": "<brief summary of any prior Apollo convos or null>",
  "enrichment_confidence":   <int 0-100>,
  "enrichment_notes":        "<what was missing or inferred>",
  "data_source":             "apollo_playwright",
  "enrichment_date":         "<today's date YYYY-MM-DD>",
  "lead_language":           "<detected language of inquiry or 'en'>",
  "inquiry_category":        "<new-implementation|upgrade|support|consulting|other>",
  "inquiry_urgency":         "<high|medium|low — inferred from language>",
  "follow_up_angle":         "<one key angle for the first follow-up email>"
}
"""


def run(data: dict) -> dict:
    """
    Structure raw Apollo data into 30 Odoo fields.
    Returns the structured dict or raises on failure.
    """
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    user_message = f"""Structure this Apollo profile data into the required 30 fields.

ORIGINAL INQUIRY (from the lead's email):
{data.get('original_inquiry', '')[:1500]}

RAW APOLLO DATA:
{json.dumps(data.get('apollo_raw', {}), indent=2)[:6000]}
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
