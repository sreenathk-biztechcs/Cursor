"""
Agent 1 — JunkFilterAgent
Model : Haiku 4.5 (fast, cheap)
Trigger: Every new lead created in Odoo (before enrichment)

Purpose:
    Classify an incoming lead as genuine, marketing, junk, or job-seeker
    so that non-genuine leads are routed to Marketing User immediately
    and genuine leads proceed to enrichment.

Input dict keys:
    email_subject  (str)  : Subject line of the incoming email
    email_body     (str)  : Full body text of the incoming email
    sender_email   (str)  : Sender's email address
    sender_domain  (str)  : Domain part (e.g. "acme.com")
    company_name   (str)  : Company name if captured by web form, else ""
    lead_id        (int)  : Odoo lead ID (for logging)

Output dict:
    classification : "genuine" | "marketing" | "junk" | "job_seeker"
    confidence     : int 0–100
    reason         : str — one-line explanation
    suggested_tag  : str — Odoo tag to apply
"""

from __future__ import annotations

from agents.base import get_client, log_call, extract_json, usage
from agents.config import MODEL_MAP, MAX_TOKENS

AGENT_NAME = "JunkFilterAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = """You are an expert lead qualification filter for a B2B software company
(Odoo implementation partner). Your only job is to classify inbound leads.

CLASSIFICATION RULES:
- "genuine"    : Real business inquiry — someone who might buy our services.
                 Signs: asks about implementation, pricing, features, demo, timeline,
                 mentions a real company need, asks technical questions.
- "marketing"  : Newsletters, press releases, promotional offers, vendor pitches,
                 conference invites, award submissions, generic "partnership" spam
                 with no real need.
- "junk"       : Completely irrelevant, gibberish, test emails, auto-generated spam,
                 phishing attempts, random contact form submissions with no content.
- "job_seeker" : Looking for a job, internship, freelance work, or referral.
                 Signs: "I am looking for", "my resume", "available for projects",
                 LinkedIn recruiter messages.

OUTPUT FORMAT — respond with ONLY valid JSON, no other text:
{
  "classification": "genuine|marketing|junk|job_seeker",
  "confidence": <0-100>,
  "reason": "<one concise sentence>",
  "suggested_tag": "<odoo-tag-slug>"
}

suggested_tag values: "genuine-lead", "marketing-promo", "junk-spam", "job-inquiry"
"""


def run(data: dict) -> dict:
    """
    Classify the lead. Returns output dict (see module docstring).
    Raises ValueError if classification cannot be parsed.
    """
    client = get_client()
    lead_id = data.get("lead_id", "unknown")

    user_message = f"""Classify this inbound lead:

Sender email : {data.get('sender_email', '')}
Sender domain: {data.get('sender_domain', '')}
Company name : {data.get('company_name', '') or '(not provided)'}
Subject      : {data.get('email_subject', '')}

Email body:
{data.get('email_body', '')[:3000]}
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
