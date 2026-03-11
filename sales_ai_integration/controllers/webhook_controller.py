import logging
import json
import base64
import hmac
import hashlib

from dateutil.relativedelta import relativedelta

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger("sales_ai")


def _check_n8n_auth(headers) -> bool:
    """
    Lightweight shared auth check for endpoints that are called from n8n or
    other trusted automations which cannot easily use Odoo API key auth.

    Expected header:
        X-N8N-Secret: <shared_secret>

    The secret value is stored in ir.config_parameter under:
        sales_ai.n8n_secret_token

    For stronger integrity checks on JSON payloads, see the HMAC-based
    signing used by the outbound helper model `sales.ai.n8n`.
    """
    if not headers:
        return False

    ICP = request.env["ir.config_parameter"].sudo()
    expected = ICP.get_param("sales_ai.n8n_secret_token", default="") or ""
    received = headers.get("X-N8N-Secret") or ""

    if not expected or not received:
        return False

    token = received.strip()

    # Optional JWT mode:
    # - expected is used as the HMAC secret (HS256)
    # - n8n sends a JWT string in X-N8N-Secret
    # If decode succeeds, we accept the request.
    if "." in token:
        try:
            import jwt  # PyJWT

            # We don't enforce particular claims here; n8n can add `exp`
            # or other claims if desired. Signature verification is enough
            # to prove possession of the shared secret.
            jwt.decode(token, expected, algorithms=["HS256"])
            return True
        except Exception:
            # Fall through to shared-secret compare if JWT verification fails
            pass

    # Default: shared-secret comparison (static token)
    try:
        return hmac.compare_digest(expected, received)
    except Exception:
        # Fallback to simple equality if compare_digest is unavailable
        return expected == received

# ---------------------------------------------------------------------------
# Authentication strategy (n8n → Odoo):
#
# All routes use auth="api_key".  In n8n, configure an HTTP Header Auth
# credential with:
#   Header name:  Authorization
#   Value:        Bearer <odoo_api_key>
#
# To generate the Odoo API key:
#   Settings → Technical → API Keys → New → copy the key into n8n.
# The key is bound to a dedicated "n8n Service" Odoo user with only the
# rights needed by these endpoints (read/write crm.lead, project.task).
# ---------------------------------------------------------------------------


class SalesAiWebhookController(http.Controller):
    """
    HTTP endpoints for n8n callbacks.

    n8n sends data here after:
      - Apollo API enrichment completes (lead intake)
      - Meeting transcript is ready
      - WBS sheet generated
      - Proposal generated
      - Presale MOM posted
      - Stale deal query
    """

    # -----------------------------------------------------------------
    # UNIFIED LEAD INTAKE (Apollo enrichment + classification)
    # -----------------------------------------------------------------
    # n8n flow:
    #   1. Odoo sends: lead_intake webhook → n8n
    #   2. n8n calls Apollo People Enrichment API (POST /api/v1/people/match)
    #   3. n8n calls Apollo Organization Enrichment API (GET /api/v1/organizations/enrich)
    #   4. n8n calls THIS endpoint with combined results

    @http.route(
        "/api/sales_ai/lead_intake_complete",
        type="json",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def lead_intake_complete(self, **payload):
        """
        Unified callback after n8n queries Apollo APIs.

        Expected payload:
        {
            "lead_id": int,
            "apollo_match": bool,        // true if Apollo found a person match
            "apollo_person": {...},       // Apollo People Enrichment response (or {})
            "apollo_organization": {...}, // Apollo Org Enrichment response (or {})
        }
        """
        lead_id = payload.get("lead_id")
        if not lead_id:
            return {"error": "missing_lead_id"}

        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            _logger.warning("sales_ai: lead_intake_complete — lead %s not found", lead_id)
            return {"error": "lead_not_found"}

        apollo_person = payload.get("apollo_person") or {}
        apollo_org = payload.get("apollo_organization") or {}
        apollo_match = payload.get("apollo_match", False)

        _logger.info(
            "sales_ai: lead_intake_complete received for lead %s (match=%s)",
            lead_id, apollo_match,
        )
        lead.action_lead_intake_complete(apollo_person, apollo_org, apollo_match)
        return {"status": "ok"}

    # -----------------------------------------------------------------
    # LEGACY: receive_apollo_data (backward compat)
    # -----------------------------------------------------------------

    @http.route(
        "/api/sales_ai/receive_apollo_data",
        type="json",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def receive_apollo_data(self, **payload):
        """Legacy endpoint — use lead_intake_complete instead."""
        lead_id = payload.get("lead_id")
        apollo_data = payload.get("apollo_data")
        if not lead_id or apollo_data is None:
            return {"error": "missing lead_id or apollo_data"}
        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            return {"error": "lead_not_found"}
        # Treat as person data with match
        lead.action_lead_intake_complete(
            apollo_person_data=apollo_data if isinstance(apollo_data, dict) else {},
            apollo_org_data={},
            apollo_match=bool(apollo_data),
        )
        return {"status": "ok"}

    # -----------------------------------------------------------------
    # MEETING TRANSCRIPT
    # -----------------------------------------------------------------

    @http.route(
        "/api/sales_ai/receive_transcript",
        type="json",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def receive_transcript(self, **payload):
        lead_id = payload.get("lead_id")
        transcript = payload.get("transcript")
        meeting_type = payload.get("meeting_type", "client")
        if not lead_id or not transcript:
            return {"error": "missing_lead_or_transcript"}
        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            return {"error": "lead_not_found"}

        _logger.info(
            "sales_ai: Transcript received for lead %s (type=%s, %d chars)",
            lead_id, meeting_type, len(transcript),
        )

        if meeting_type == "client":
            lead.action_generate_client_mom(transcript)
        elif meeting_type == "presale":
            # For presale meetings, generate presale client email
            lead.action_generate_presale_client_email(mom_content=transcript)
        return {"status": "ok"}

    # -----------------------------------------------------------------
    # PROPOSAL READY
    # -----------------------------------------------------------------

    @http.route(
        "/api/sales_ai/proposal_ready",
        type="json",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def proposal_ready(self, **payload):
        lead_id = payload.get("lead_id")
        url = payload.get("proposal_drive_url")
        if not lead_id or not url:
            return {"error": "missing_lead_or_url"}
        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            return {"error": "lead_not_found"}

        lead.write({
            "x_proposal_drive_url": url,
            "x_presale_status": "proposal_generated",
        })
        lead.message_post(
            body="AI-generated proposal ready: <a href='%s'>Open proposal</a>" % url,
            subtype_xmlid="mail.mt_note",
        )
        _logger.info("sales_ai: Proposal ready for lead %s — URL: %s", lead_id, url)
        return {"status": "ok"}

    # -----------------------------------------------------------------
    # WBS READY
    # -----------------------------------------------------------------

    @http.route(
        "/api/sales_ai/wbs_ready",
        type="json",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def wbs_ready(self, **payload):
        lead_id = payload.get("lead_id")
        sheet_url = payload.get("sheet_url")
        if not lead_id or not sheet_url:
            return {"error": "missing_lead_or_url"}
        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            return {"error": "lead_not_found"}

        lead.write({
            "x_wbs_sheet_url": sheet_url,
            "x_presale_status": "ready_for_wbs",
        })
        lead.message_post(
            body="WBS generated. <a href='%s'>Open Google Sheet</a>" % sheet_url,
            subtype_xmlid="mail.mt_note",
        )
        _logger.info("sales_ai: WBS ready for lead %s — URL: %s", lead_id, sheet_url)
        return {"status": "ok"}

    # -----------------------------------------------------------------
    # PRESALE MOM POSTED
    # -----------------------------------------------------------------

    @http.route(
        "/api/sales_ai/presale_mom_posted",
        type="json",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def presale_mom_posted(self, **payload):
        lead_id = payload.get("lead_id")
        mom_content = payload.get("mom_content") or ""
        if not lead_id:
            return {"error": "missing_lead_id"}
        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            return {"error": "lead_not_found"}

        _logger.info("sales_ai: Presale MOM posted for lead %s", lead_id)
        lead.action_generate_presale_client_email(mom_content=mom_content)
        return {"status": "ok"}

    # -----------------------------------------------------------------
    # STALE DEALS EXPORT
    # -----------------------------------------------------------------

    @http.route(
        "/api/sales_ai/stale_deals",
        type="json",
        auth="api_key",
        methods=["GET", "POST"],
        csrf=False,
    )
    def stale_deals(self, **kwargs):
        ICP = request.env["ir.config_parameter"].sudo()
        thresholds_raw = ICP.get_param("sales_ai.stale_thresholds_json", default="{}")
        try:
            thresholds = json.loads(thresholds_raw)
        except Exception:
            thresholds = {}

        Lead = request.env["crm.lead"].sudo()
        today = fields.Date.today()
        result = []
        for stage_name, days in thresholds.items():
            stage = request.env["crm.stage"].sudo().search(
                [("name", "=", stage_name)], limit=1
            )
            if not stage:
                continue
            cutoff = today - relativedelta(days=int(days))
            leads = Lead.search([
                ("stage_id", "=", stage.id),
                ("write_date", "<", cutoff),
            ])
            for lead in leads:
                result.append({
                    "lead_id": lead.id,
                    "lead_name": lead.name,
                    "stage": stage_name,
                    "salesperson": lead.user_id.name if lead.user_id else "",
                    "days_stuck": (today - lead.write_date.date()).days,
                    "email": lead.user_id.email if lead.user_id else "",
                })
        _logger.info("sales_ai: Stale deals query returned %d results", len(result))
        return result

    # ------------------------------------------------------------------
    # Apollo enrichment endpoint (direct Apollo REST from Odoo)
    # ------------------------------------------------------------------

    @http.route(
        "/api/enrich_lead",
        type="json",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def api_enrich_lead(self, **payload):
        """
        Entry point that can be called directly (or from n8n) to:
        - take {email / name / phone}
        - call Apollo /v1/mixed_people/search and /v1/accounts/search
        - match/update existing lead OR, if no match, call Claude to
          generate a new lead payload and create it.
        """
        if not _check_n8n_auth(request.httprequest.headers):
            _logger.warning("Unauthorized /api/enrich_lead call")
            return {"error": "unauthorized"}

        from requests import Session

        ICP = request.env["ir.config_parameter"].sudo()
        api_key = ICP.get_param("sales_ai.apollo_api_key", default="")
        base_url = (
            ICP.get_param("sales_ai.apollo_api_base_url", default="https://api.apollo.io")
            or "https://api.apollo.io"
        ).rstrip("/")

        if not api_key:
            _logger.error("Apollo API key not configured (sales_ai.apollo_api_key)")
            return {"error": "apollo_api_key_missing"}

        email = (payload.get("email") or "").strip()
        name = (payload.get("name") or "").strip()
        phone = (payload.get("phone") or "").strip()

        if not (email or name or phone):
            return {"error": "missing_identifiers"}

        session = Session()
        headers = {"Content-Type": "application/json", "X-Api-Key": api_key}

        # 1) Person search
        search_body = {"q_keywords": name} if name else {}
        if email:
            search_body["person_email"] = email
        if phone:
            search_body["person_phone"] = phone

        person = None
        try:
            resp = session.post(
                f"{base_url}/v1/mixed_people/search",
                json=search_body,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            people = data.get("people", []) or data.get("contacts", []) or []
            if people:
                person = people[0]
        except Exception as exc:
            _logger.error("Apollo person search failed: %s", exc, exc_info=True)

        # Junk filter via Apollo email_status
        if person and person.get("email_status") and person["email_status"] != "deliverable":
            _logger.error(
                "Apollo marked email %s as %s; treating as junk.",
                person.get("email"),
                person.get("email_status"),
            )
            return {"status": "junk"}

        # 2) Organisation search (if we have company/domain)
        account = None
        company_name = person and (person.get("organization_name") or person.get("company_name"))
        domain = person and person.get("organization_website_url")
        org_body = {}
        if company_name:
            org_body["q_organization_name"] = company_name
        if domain:
            org_body["domain"] = domain
        if org_body:
            try:
                resp = session.post(
                    f"{base_url}/v1/accounts/search",
                    json=org_body,
                    headers=headers,
                    timeout=15,
                )
                resp.raise_for_status()
                org_data = resp.json()
                accounts = org_data.get("accounts", [])
                if accounts:
                    account = accounts[0]
            except Exception as exc:
                _logger.error("Apollo org search failed: %s", exc, exc_info=True)

        env = request.env
        Lead = env["crm.lead"].sudo()

        # 3) Try to match existing lead by email
        matched_lead = None
        if email:
            leads = Lead.search(
                [("email_from", "=ilike", email), ("active", "=", True)], limit=1
            )
            if leads:
                matched_lead = leads[0]

        # 4) Enrich existing lead
        if matched_lead and person:
            _logger.info("Apollo enrichment start for lead %s", matched_lead.id)
            vals = {
                "x_apollo_person_id": person.get("id"),
                "x_apollo_data_raw": json.dumps(
                    {"person": person, "account": account}, ensure_ascii=False
                ),
            }
            if account and account.get("employee_count"):
                vals["x_employee_count"] = account["employee_count"]
            if account and account.get("estimated_annual_revenue"):
                vals["x_annual_revenue"] = account["estimated_annual_revenue"]
            if person.get("linkedin_url"):
                vals["x_linkedin_url"] = person["linkedin_url"]
            matched_lead.write(vals)
            _logger.info("Apollo enrichment completed for lead %s", matched_lead.id)
            return {"status": "enriched", "lead_id": matched_lead.id}

        # 5) No match -> use Claude to create a new lead payload
        claude_service = env["claude.service"]
        system_prompt = ICP.get_param("sales_ai.claude_system_prompt", default="") or (
            "You are an assistant that converts Apollo person/account JSON into "
            "a CRM lead creation payload."
        )
        try:
            resp = claude_service.call(
                tier="sonnet",
                system_prompt=system_prompt,
                user_message=json.dumps(
                    {"input": payload, "person": person, "account": account},
                    ensure_ascii=False,
                ),
                max_tokens=800,
                expect_json=True,
            )
        except Exception as exc:
            _logger.error("Claude failed to generate lead payload: %s", exc, exc_info=True)
            return {"error": "claude_failed"}

        if not isinstance(resp, dict):
            return {"error": "invalid_claude_payload"}

        lead_vals = {
            "name": resp.get("name") or (company_name or email or name or "New Lead"),
            "email_from": resp.get("email_from") or email,
            "phone": resp.get("phone") or phone,
            "description": resp.get("description") or "",
            "type": "lead",
        }
        # Assign by simple rule: if estimated revenue > 1M, assign to Sales Team 1 lead
        revenue = resp.get("expected_revenue") or 0
        team = env["crm.team"].sudo().search([], limit=1)
        if team:
            lead_vals["team_id"] = team.id

        new_lead = Lead.create(lead_vals)
        _logger.info("New lead %s created from Apollo/Claude enrichment", new_lead.id)
        return {"status": "created", "lead_id": new_lead.id}

    # ------------------------------------------------------------------
    # MOM activity creation – transcript + attachment extracts
    # ------------------------------------------------------------------

    @http.route(
        "/api/create_mom_activity",
        type="json",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def api_create_mom_activity(self, **payload):
        if not _check_n8n_auth(request.httprequest.headers):
            _logger.warning("Unauthorized /api/create_mom_activity call")
            return {"error": "unauthorized"}

        lead_id = payload.get("lead_id")
        transcript = payload.get("transcript") or ""
        attachment_ids = payload.get("attachment_ids") or []
        if not lead_id or not transcript:
            return {"error": "missing_lead_or_transcript"}

        env = request.env
        Lead = env["crm.lead"].sudo()
        lead = Lead.browse(int(lead_id))
        if not lead.exists():
            return {"error": "lead_not_found"}

        # Extract attachments into text
        extracts = {}
        Attachment = env["ir.attachment"].sudo()
        try:
            from PyPDF2 import PdfReader
            import pytesseract
            from docx import Document
            from io import BytesIO
            from PIL import Image
        except Exception as exc:
            _logger.error("Attachment libraries missing: %s", exc, exc_info=True)
            # Proceed with transcript only
            extracts = {}
        else:
            for att_id in attachment_ids:
                att = Attachment.browse(int(att_id))
                if not att.exists() or not att.datas:
                    continue
                raw = att.datas
                try:
                    data = base64.b64decode(raw)
                except Exception:
                    continue
                text = ""
                mime = att.mimetype or ""
                name = (att.name or "").lower()
                try:
                    if mime == "application/pdf" or name.endswith(".pdf"):
                        reader = PdfReader(BytesIO(data))
                        for page in reader.pages:
                            text += page.extract_text() or ""
                    elif mime.startswith("image/"):
                        img = Image.open(BytesIO(data))
                        text = pytesseract.image_to_string(img)
                    elif name.endswith(".docx"):
                        doc = Document(BytesIO(data))
                        text = "\n".join(p.text for p in doc.paragraphs)
                except Exception as exc:
                    _logger.error("Failed to extract text from attachment %s: %s", att.id, exc)
                if text:
                    extracts[str(att.id)] = text[:20000]

        # Cache extracts on lead
        if extracts:
            lead.x_attachment_extracts_json = json.dumps(extracts, ensure_ascii=False)

        # Call Claude for structured MOM JSON
        claude_service = env["claude.service"]
        system_prompt = (
            "You are a sales assistant creating structured meeting minutes (MOM). "
            "Return JSON: {date: string, time: string, points: [..], "
            "actions: [{owner, description, due_date}], next_steps: string}."
        )
        try:
            resp = claude_service.call(
                tier="sonnet",
                system_prompt=system_prompt,
                user_message=json.dumps(
                    {
                        "transcript": transcript[:150000],
                        "attachments": extracts,
                    },
                    ensure_ascii=False,
                ),
                max_tokens=1200,
                expect_json=True,
            )
        except Exception as exc:
            _logger.error("Claude MOM structuring failed: %s", exc, exc_info=True)
            return {"error": "claude_failed"}

        if not isinstance(resp, dict):
            return {"error": "invalid_mom_json"}

        # Append to x_mom_history
        try:
            history = json.loads(lead.x_mom_history or "[]")
        except Exception:
            history = []
        history.append(resp)
        lead.x_mom_history = json.dumps(history, ensure_ascii=False)

        # Create mail.activity + chatter note
        mom_html = "<p><b>Date:</b> %s<br/><b>Time:</b> %s</p>" % (
            resp.get("date") or "",
            resp.get("time") or "",
        )
        mom_html += "<h4>Discussion Points</h4><ul>"
        for pt in resp.get("points") or []:
            mom_html += "<li>%s</li>" % pt
        mom_html += "</ul><h4>Actions</h4><ul>"
        for act in resp.get("actions") or []:
            mom_html += "<li><b>%s</b>: %s (due %s)</li>" % (
                act.get("owner") or "",
                act.get("description") or "",
                act.get("due_date") or "",
            )
        mom_html += "</ul><h4>Next Steps</h4><p>%s</p>" % (resp.get("next_steps") or "")

        lead.message_post(body=mom_html, subtype_xmlid="mail.mt_note")

        mom_type = env.ref(
            "sales_ai_integration.activity_type_client_mom", raise_if_not_found=False
        )
        env["mail.activity"].sudo().create(
            {
                "res_model": "crm.lead",
                "res_id": lead.id,
                "user_id": lead.user_id.id,
                "activity_type_id": mom_type.id if mom_type else False,
                "note": "[AI MOM] " + (resp.get("next_steps") or ""),
                "date_deadline": fields.Date.today(),
            }
        )

        return {"status": "ok", "lead_id": lead.id}
