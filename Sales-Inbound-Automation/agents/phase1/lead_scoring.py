"""
Agent 3 — LeadScoringAgent
Model : Haiku 4.5
Trigger: After enrichment write-back completes

Purpose:
    Score a lead 0–100 against the sales team's ICP criteria.
    The ICP config is stored as JSON in Odoo and passed in at runtime,
    allowing the sales team to tune criteria without code changes.

Input dict keys:
    lead_id          (int)  : Odoo lead ID
    enriched_fields  (dict) : Output from EnrichmentStructurerAgent
    original_inquiry (str)  : Lead's original email body
    icp_config       (dict) : ICP criteria JSON (see ICP_CONFIG_SCHEMA below)

ICP_CONFIG_SCHEMA example:
{
  "target_industries":      [{"name": "Manufacturing", "weight": 25}, ...],
  "target_employee_range":  {"min": 50, "max": 5000, "weight": 20},
  "target_revenue_range":   {"min": "$5M", "max": "$500M", "weight": 15},
  "target_seniority":       ["C-Level", "VP", "Director"],
  "seniority_weight":       15,
  "target_geographies":     ["IN", "US", "UK", "AE"],
  "geography_weight":       10,
  "inquiry_intent_weight":  10,
  "disqualifiers":          ["competitor_domain", "blacklisted_domain", "student"]
}

Output dict:
    score       : int 0–100
    band        : "hot" | "warm" | "neutral" | "cold"
    breakdown   : dict with each category's score
    rationale   : str — paragraph explaining the score
    red_flags   : list of strings (disqualifying signals found)
    recommended_action : str — what the rep should do next
"""

from __future__ import annotations
import json

from agents.base import get_client, log_call, extract_json, usage
from agents.config import MODEL_MAP, MAX_TOKENS, SCORE_BANDS

AGENT_NAME = "LeadScoringAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

SYSTEM_PROMPT = """You are an expert B2B sales analyst. Score this inbound lead against
the provided ICP (Ideal Customer Profile) criteria.

SCORING BREAKDOWN (must sum to the total score):
- Industry fit:       0–25 pts  (how well industry/sub-industry matches targets)
- Company size fit:   0–20 pts  (employee count within target range)
- Revenue fit:        0–15 pts  (revenue range within target)
- Contact seniority:  0–15 pts  (seniority level match with target titles)
- Geography fit:      0–10 pts  (HQ country in target list)
- Inquiry intent:     0–10 pts  (specificity and urgency of their ask)
- Disqualifiers:      –20 pts max (each disqualifier found reduces score)

BAND THRESHOLDS:
- 90–100: hot
- 70–89:  warm
- 50–69:  neutral
- 0–49:   cold

OUTPUT FORMAT — respond with ONLY valid JSON:
{
  "score": <int 0-100>,
  "band": "hot|warm|neutral|cold",
  "breakdown": {
    "industry_fit":      <int 0-25>,
    "company_size_fit":  <int 0-20>,
    "revenue_fit":       <int 0-15>,
    "contact_seniority": <int 0-15>,
    "geography_fit":     <int 0-10>,
    "inquiry_intent":    <int 0-10>,
    "disqualifier_penalty": <int 0 or negative>
  },
  "rationale": "<2-3 sentence explanation of the score>",
  "red_flags": ["<list of disqualifying signals or empty list>"],
  "recommended_action": "<what rep should do: proceed/review/disqualify>"
}
"""


def run(data: dict) -> dict:
    """Score the lead. Returns output dict or raises on failure."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    user_message = f"""Score this lead against the ICP criteria.

ICP CRITERIA:
{json.dumps(data.get('icp_config', {}), indent=2)}

ENRICHED LEAD DATA:
{json.dumps(data.get('enriched_fields', {}), indent=2)[:4000]}

ORIGINAL INQUIRY:
{data.get('original_inquiry', '')[:1000]}
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

        # Validate band against score
        score = result.get("score", 0)
        for band, (lo, hi) in SCORE_BANDS.items():
            if lo <= score <= hi:
                result["band"] = band
                break

        log_call(AGENT_NAME, MODEL, lead_id, in_tok, out_tok, success=True,
                 extra={"score": score, "band": result.get("band")})
        return result

    except Exception as exc:
        log_call(AGENT_NAME, MODEL, lead_id, 0, 0, success=False, error=str(exc))
        raise
