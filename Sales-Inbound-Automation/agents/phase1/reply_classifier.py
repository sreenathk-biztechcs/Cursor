"""
Agent 6 — ReplyClassifierAgent
Model : Haiku 4.5 (fast — runs on every incoming reply)
Trigger: mail_smart_link module routes an inbound email → webhook

Purpose:
    Classify the intent of an incoming reply to an outbound sales email.
    Drive automated actions (pause sequence, move stage, create tasks, etc.)
    without rep intervention.

Input dict keys:
    lead_id          (int)  : Odoo lead ID
    reply_body       (str)  : Full body of the incoming reply
    reply_from       (str)  : Sender email address
    reply_subject    (str)  : Reply subject line
    lead_stage       (str)  : Current Odoo CRM stage of the lead
    lead_score_band  (str)  : "hot"|"warm"|"neutral"|"cold"
    emails_sent      (int)  : How many outbound emails have been sent

Output dict:
    intent          : str — one of the INTENT values below
    confidence      : int 0–100
    action          : str — the Odoo action to trigger
    ooo_return_date : str | null — ISO date if intent is "ooo"
    new_contact_hint: str | null — if intent is "wrong_person", any name/email hint
    note_for_rep    : str — one sentence summary for the rep's activity note
    priority_flag   : bool — True if rep needs to respond today

INTENT VALUES:
    "interested"       → genuine interest, wants to continue conversation
    "meeting_booked"   → they've booked or are confirming a meeting
    "not_interested"   → politely declining, not now or ever
    "ooo"              → out-of-office auto-reply
    "wrong_person"     → they're not the right contact
    "referral"         → referring to another person
    "generic_positive" → positive but vague (e.g. "thanks", "noted")
    "unsubscribe"      → wants to stop receiving emails
    "question"         → asking a specific question (needs rep reply)
    "negotiating"      → discussing pricing, scope, or terms
"""

from __future__ import annotations

from agents.base import get_client, log_call, usage
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS

AGENT_NAME = "ReplyClassifierAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = """You are an expert sales email intent classifier. Analyze the
incoming reply to a B2B sales outreach email and classify its intent precisely.

VALID INTENTS (choose exactly one):
  interested        | not_interested | meeting_booked | ooo
  wrong_person      | referral       | generic_positive | unsubscribe
  question          | negotiating

ACTION MAPPING (what Odoo should do automatically):
  interested        → reset_sequence, move_stage=Engaged
  meeting_booked    → cancel_sequence, move_stage=Meeting Scheduled
  not_interested    → stop_sequence, move_stage=Lost, reason=Not Interested
  ooo               → pause_sequence_until_return_date
  wrong_person      → create_task=Find correct contact
  referral          → create_note=Referred by X to Y
  generic_positive  → reset_sequence, create_activity=Reply with value add
  unsubscribe       → stop_sequence_permanently, tag=Unsubscribed
  question          → create_activity=Rep must answer question TODAY, priority=true
  negotiating       → move_stage=Negotiation, create_activity=Rep follow up today

OUTPUT FORMAT — respond with ONLY valid JSON:
{
  "intent": "<one of the 10 intent values>",
  "confidence": <int 0-100>,
  "action": "<odoo_action_slug>",
  "ooo_return_date": "<YYYY-MM-DD or null>",
  "new_contact_hint": "<name and/or email if wrong_person, else null>",
  "note_for_rep": "<one sentence for the rep's activity note>",
  "priority_flag": <true|false>
}
"""


def run(data: dict) -> dict:
    """Classify the reply intent. Returns output dict."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    user_message = f"""Classify this inbound reply.

CONTEXT:
  Lead stage   : {data.get('lead_stage', 'unknown')}
  Score band   : {data.get('lead_score_band', 'unknown')}
  Emails sent  : {data.get('emails_sent', 'unknown')}
  Reply from   : {data.get('reply_from', '')}
  Reply subject: {data.get('reply_subject', '')}

REPLY BODY:
{data.get('reply_body', '')[:3000]}
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
                 extra={"intent": result.get("intent")})
        return result

    except Exception as exc:
        log_call(AGENT_NAME, MODEL, lead_id, 0, 0, success=False, error=str(exc))
        raise
