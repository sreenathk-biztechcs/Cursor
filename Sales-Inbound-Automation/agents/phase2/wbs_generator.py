"""
Agent 12 — WBSGeneratorAgent
Model : Sonnet 4.6
Trigger: Presale team clicks "Generate WBS" button on the presale ticket
         (n8n orchestrates: calls this agent, writes output to Google Sheets)

Purpose:
    Generate a full Work Breakdown Structure from presale discussion notes.
    Output is structured JSON that n8n writes into the company's WBS
    Google Sheets template (one tab per ticket).

Input dict keys:
    lead_id             (int)  : Odoo lead ID
    ticket_id           (str)  : Presale ticket number
    client_company      (str)  : Client company name
    project_type        (str)  : e.g. "new-implementation"|"upgrade"|"integration"|"custom-dev"
    requirements        (list) : List of requirement strings (from presale MOMs)
    technical_decisions (list) : Architecture/tech decisions from presale MOMs
    client_existing_systems (list): Client's current tech stack / systems
    modules_in_scope    (list) : Odoo modules or custom features in scope
    integrations_in_scope(list): Third-party integrations required
    constraints         (dict) : {timeline_weeks, team_size, go_live_date, pilot_entity}
    wbs_template_phases (list) : Phase names from company's existing WBS template

Output dict:
    wbs_phases  : list of phase dicts (see PHASE_SCHEMA)
    assumptions : list[str] — assumptions made in the WBS
    exclusions  : list[str] — explicitly out of scope
    risks       : list[str] — risks that could affect timeline
    total_tasks : int

PHASE_SCHEMA:
{
  "phase_name": str,
  "phase_order": int,
  "tasks": [
    {
      "task_id": str,           e.g. "P1.T1"
      "task_name": str,
      "description": str,
      "owner": str,             "Dev"|"QA"|"PM"|"Presale"|"Client"|"BA"
      "depends_on": list[str],  task_ids
      "effort_placeholder": str "TBD by tech team"
      "deliverable": str,
      "notes": str
    }
  ]
}
"""

from __future__ import annotations
import json

from agents.base import get_client, log_call, usage
from agents.base.output_parser import extract_json
from agents.config import MODEL_MAP, MAX_TOKENS

AGENT_NAME = "WBSGeneratorAgent"
MODEL       = MODEL_MAP[AGENT_NAME]

DEFAULT_PHASES = [
    "Phase 1: Discovery & Gap Analysis",
    "Phase 2: System Design & Prototype",
    "Phase 3: Core Development",
    "Phase 4: Integrations",
    "Phase 5: UAT & Training",
    "Phase 6: Go-Live & Hypercare",
]

SYSTEM_PROMPT = """You are a senior Odoo implementation project manager. Generate a
detailed Work Breakdown Structure (WBS) for an Odoo implementation project.

WBS RULES:
1. Follow the provided phase structure (or company's template phases if given).
2. Every task must have a clear deliverable — not just a verb phrase.
3. Owner must be one of: Dev | QA | PM | BA | Presale | Client | Joint
4. Use "TBD by tech team" for all effort estimates — never guess hours.
5. Dependencies must use task_id references (e.g. "P1.T3").
6. Include client-side tasks (data prep, UAT sign-off, training attendance).
7. Don't over-engineer: include only tasks needed for THIS specific scope.
8. Flag tasks that are risky or scope-ambiguous in the "notes" field.

OUTPUT FORMAT — respond with ONLY valid JSON matching exactly:
{
  "wbs_phases": [
    {
      "phase_name": "<name>",
      "phase_order": <int>,
      "tasks": [
        {
          "task_id": "<e.g. P1.T1>",
          "task_name": "<short name>",
          "description": "<what this task involves>",
          "owner": "<Dev|QA|PM|BA|Presale|Client|Joint>",
          "depends_on": ["<task_id>"],
          "effort_placeholder": "TBD by tech team",
          "deliverable": "<what is produced>",
          "notes": "<risks, assumptions, or blank>"
        }
      ]
    }
  ],
  "assumptions": ["<list of WBS assumptions>"],
  "exclusions": ["<explicit out-of-scope items>"],
  "risks": ["<schedule/scope risks>"],
  "total_tasks": <int>
}
"""


def run(data: dict) -> dict:
    """Generate the WBS. Returns structured WBS JSON for n8n → Google Sheets."""
    client  = get_client()
    lead_id = data.get("lead_id", "unknown")

    phases = data.get("wbs_template_phases") or DEFAULT_PHASES
    constraints = data.get("constraints", {})

    user_message = f"""Generate the WBS for this Odoo project.

PROJECT OVERVIEW:
  Client        : {data.get('client_company', '')}
  Ticket        : {data.get('ticket_id', '')}
  Project type  : {data.get('project_type', 'new-implementation')}
  Go-live target: {constraints.get('go_live_date', 'TBD')}
  Timeline      : {constraints.get('timeline_weeks', 'TBD')} weeks
  Pilot entity  : {constraints.get('pilot_entity', 'Full company')}

MODULES IN SCOPE:
{chr(10).join(['  - ' + m for m in data.get('modules_in_scope', [])]) or '  Not specified'}

INTEGRATIONS IN SCOPE:
{chr(10).join(['  - ' + i for i in data.get('integrations_in_scope', [])]) or '  None'}

CLIENT'S EXISTING SYSTEMS:
{chr(10).join(['  - ' + s for s in data.get('client_existing_systems', [])]) or '  Not specified'}

REQUIREMENTS (from presale discussions):
{chr(10).join(['  - ' + r for r in data.get('requirements', [])]) or '  Not specified'}

TECHNICAL DECISIONS MADE:
{chr(10).join(['  - ' + d for d in data.get('technical_decisions', [])]) or '  None yet'}

WBS PHASE STRUCTURE TO FOLLOW:
{chr(10).join(['  ' + str(i+1) + '. ' + p for i, p in enumerate(phases)])}
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
                 extra={"ticket_id": data.get("ticket_id"),
                        "total_tasks": result.get("total_tasks")})
        return result

    except Exception as exc:
        log_call(AGENT_NAME, MODEL, lead_id, 0, 0, success=False, error=str(exc))
        raise
