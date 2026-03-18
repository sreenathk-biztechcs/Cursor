import logging
import json
import base64
import hmac
import hashlib
import threading

from dateutil.relativedelta import relativedelta

from odoo import http, fields, SUPERUSER_ID
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
# rights needed by these endpoints (read/write crm.lead).
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
    # PING — reverse-direction health check (n8n → Odoo)
    # -----------------------------------------------------------------

    @http.route(
        "/odoo/api/sales_ai/ping",
        type="jsonrpc",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def ping(self, **payload):
        """
        Lightweight endpoint for n8n to verify the reverse connection
        (n8n → Odoo) during the bidirectional handshake.

        n8n calls this with:
            POST /api/sales_ai/ping
            Authorization: Bearer <odoo_api_key>
            {"ping": true}

        Response:
            {"status": "pong", "odoo_version": "19.0", "timestamp": "..."}
        """
        ICP = request.env["ir.config_parameter"].sudo()
        ICP.set_param("sales_ai.n8n_reverse_status", "ok")
        _logger.info("sales_ai: [PING] Reverse ping from n8n — OK")
        return {
            "status": "pong",
            "odoo_version": "19.0",
            "timestamp": fields.Datetime.now(),
        }

    # -----------------------------------------------------------------
    # UNIFIED LEAD INTAKE (Apollo enrichment + classification)
    # -----------------------------------------------------------------
    # n8n flow:
    #   1. Odoo sends: lead_intake webhook → n8n
    #   2. n8n calls Apollo People Enrichment API (POST /api/v1/people/match)
    #   3. n8n calls Apollo Organization Enrichment API (GET /api/v1/organizations/enrich)
    #   4. n8n calls THIS endpoint with combined results

    @http.route(
        "/odoo/api/sales_ai/lead_intake_complete",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def lead_intake_complete(self, **kw):
        """
        Unified callback after n8n queries Apollo APIs.

        n8n sends plain JSON (not JSON-RPC), so this uses type="http".

        Expected payload:
        {
            "lead_id": int,
            "apollo_match": bool,
            "apollo_person": {...},
            "apollo_organization": {...},
        }
        """
        def _json_resp(data, status=200):
            return request.make_response(
                json.dumps(data),
                headers=[("Content-Type", "application/json")],
                status=status,
            )

        if not _check_n8n_auth(request.httprequest.headers):
            _logger.warning("sales_ai: Unauthorized lead_intake_complete call")
            return _json_resp({"error": "unauthorized"}, 401)

        try:
            data = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except (json.JSONDecodeError, Exception):
            data = {}

        if isinstance(data, dict) and isinstance(data.get("params"), dict):
            payload = data["params"]
        else:
            payload = data if isinstance(data, dict) else {}

        lead_id = payload.get("lead_id")
        if not lead_id:
            return _json_resp({"error": "missing_lead_id"}, 400)

        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            _logger.warning("sales_ai: lead_intake_complete — lead %s not found", lead_id)
            return _json_resp({"error": "lead_not_found"}, 404)

        if lead.x_enrichment_done:
            _logger.info(
                "sales_ai: lead_intake_complete for lead %s — already enriched via synchronous path, skipping",
                lead_id,
            )
            return _json_resp({"status": "ok", "note": "already_enriched"})

        # n8n may send either:
        # - apollo_person / apollo_organization
        # - OR only apollo_result with nested person/org (older flow)
        apollo_person = payload.get("apollo_person") or {}
        apollo_org = payload.get("apollo_organization") or {}
        if not (apollo_person or apollo_org):
            apollo_result = payload.get("apollo_result") or {}
            if isinstance(apollo_result, dict):
                apollo_person = apollo_result.get("person") or apollo_result or {}
                apollo_org = apollo_result.get("organization") or {}

        apollo_match = payload.get("apollo_match")
        # If match flag is missing or empty, infer it from the presence of Apollo data
        if apollo_match in (None, "", "unknown"):
            apollo_match = bool(apollo_person or apollo_org)

        _logger.info(
            "sales_ai: lead_intake_complete received for lead %s (match=%s, force_full_intake=%s)",
            lead_id, apollo_match, payload.get("force_full_intake"),
        )
        lead.action_lead_intake_complete(
            apollo_person,
            apollo_org,
            bool(apollo_match),
            force_full_intake=bool(payload.get("force_full_intake")),
        )
        return _json_resp({"status": "ok"})

    # -----------------------------------------------------------------
    # LEGACY: receive_apollo_data (backward compat)
    # -----------------------------------------------------------------

    @http.route(
        "/odoo/api/sales_ai/receive_apollo_data",
        type="jsonrpc",
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
        "/odoo/api/sales_ai/receive_transcript",
        type="jsonrpc",
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

        # Run MOM generation in background thread — return response immediately.
        from ..models.crm_lead import _bg_client_mom_worker

        dbname = request.env.cr.dbname

        if meeting_type == "client":
            mom_kwargs = {
                "transcript": transcript,
                "meeting_date": payload.get("meeting_date") or "",
                "meeting_duration": int(payload.get("meeting_duration") or 0),
                "attendees": payload.get("attendees") or [],
            }
            t = threading.Thread(
                target=_bg_client_mom_worker,
                args=(dbname, SUPERUSER_ID, int(lead_id), mom_kwargs),
                name="bg-mom-%s" % lead_id,
            )
            t.start()
        elif meeting_type == "presale":
            lead.action_generate_presale_mom_from_transcript(
                transcript=transcript,
                meeting_date=payload.get("meeting_date"),
                meeting_duration=payload.get("meeting_duration"),
                attendees=payload.get("attendees") or [],
                prior_open_items=payload.get("prior_open_items") or [],
            )
        return {"status": "ok", "async": meeting_type == "client"}

    # -----------------------------------------------------------------
    # STRUCTURED ENRICHMENT WRITE-BACK (EnrichmentStructurerAgent)
    # -----------------------------------------------------------------

    @http.route(
        "/odoo/api/sales_ai/enrichment_structured",
        type="jsonrpc",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def enrichment_structured(self, **payload):
        """
        Endpoint for n8n / EnrichmentStructurerAgent to POST structured
        enrichment JSON back to Odoo.

        Expected payload:
        {
          "lead_id": int,
          "enrichment": { ... }  # JSON keys as defined by EnrichmentStructurerAgent
        }
        """
        lead_id = payload.get("lead_id")
        enrichment = payload.get("enrichment") or {}
        if not lead_id or not isinstance(enrichment, dict):
            return {"error": "missing_lead_or_enrichment"}

        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            _logger.warning("sales_ai: enrichment_structured — lead %s not found", lead_id)
            return {"error": "lead_not_found"}

        _logger.info(
            "sales_ai: enrichment_structured received for lead %s (keys=%s)",
            lead_id,
            list(enrichment.keys()),
        )
        lead.action_apply_structured_enrichment(enrichment)
        return {"status": "ok"}

    # -----------------------------------------------------------------
    # PROPOSAL READY
    # -----------------------------------------------------------------

    @http.route(
        "/odoo/api/sales_ai/proposal_ready",
        type="jsonrpc",
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
        "/odoo/api/sales_ai/wbs_ready",
        type="jsonrpc",
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
        "/odoo/api/sales_ai/presale_mom_posted",
        type="jsonrpc",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def presale_mom_posted(self, **payload):
        """n8n callback: presale MOM text available. Posts to lead + triggers presale email draft."""
        lead_id = payload.get("lead_id")
        mom_content = payload.get("mom_content") or ""
        if not lead_id:
            return {"error": "missing_lead_id"}
        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            return {"error": "lead_not_found"}

        if mom_content:
            lead.message_post(
                body="<b>Presale MOM (from n8n)</b><br/><pre>%s</pre>" % mom_content[:5000],
                subtype_xmlid="mail.mt_note",
            )
        _logger.info("sales_ai: Presale MOM posted for lead %s", lead_id)
        lead.action_generate_presale_client_email(mom_content=mom_content)
        return {"status": "ok"}

    # -----------------------------------------------------------------
    # STALE DEALS EXPORT
    # -----------------------------------------------------------------

    @http.route(
        "/odoo/api/sales_ai/stale_deals",
        type="jsonrpc",
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
        "/odoo/api/enrich_lead",
        type="jsonrpc",
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
                timeout=90,
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
                    timeout=90,
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

    # -----------------------------------------------------------------
    # CALENDLY / CALENDAR EVENT CREATED
    # -----------------------------------------------------------------

    @http.route(
        "/odoo/api/sales_ai/calendar_event_create",
        type="jsonrpc",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def calendar_event_create(self, **payload):
        """
        Called by n8n when a Calendly booking is created.

        Expected payload:
        {
            "lead_id": int,
            "event_name": str,
            "start_datetime": str,   ISO datetime
            "duration_minutes": int,
            "invitee_name": str,
            "invitee_email": str,
            "calendly_event_id": str,
            "calendly_event_url": str,
        }
        """
        lead_id = payload.get("lead_id")
        if not lead_id:
            # Try to find lead by invitee email
            email = (payload.get("invitee_email") or "").strip()
            if email:
                lead = request.env["crm.lead"].sudo().search(
                    [("email_from", "=ilike", email), ("active", "=", True)], limit=1
                )
                if lead:
                    lead_id = lead.id

        if not lead_id:
            _logger.warning("sales_ai: calendar_event_create — no lead_id and no email match")
            return {"error": "no_lead_found"}

        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            return {"error": "lead_not_found"}

        start_dt = payload.get("start_datetime", "")
        event_name = payload.get("event_name") or "Meeting"
        invitee = payload.get("invitee_name") or lead.contact_name or ""
        calendly_url = payload.get("calendly_event_url") or ""

        # Post note on lead
        note_html = (
            "<p><b>Meeting scheduled via Calendly:</b> %s</p>"
            "<p><b>Invitee:</b> %s &lt;%s&gt;</p>"
            "<p><b>Start:</b> %s</p>"
            "%s"
        ) % (
            event_name, invitee, payload.get("invitee_email") or "",
            start_dt,
            ("<p><a href='%s'>Calendly event</a></p>" % calendly_url) if calendly_url else "",
        )
        lead.message_post(body=note_html, subtype_xmlid="mail.mt_note")

        # Update lead stage to "Meeting Scheduled" if it exists
        meeting_stage = request.env["crm.stage"].sudo().search(
            [("name", "ilike", "meeting")], limit=1
        )
        if meeting_stage:
            lead.stage_id = meeting_stage

        _logger.info(
            "sales_ai: Calendar event created for lead %s — %s at %s",
            lead_id, event_name, start_dt,
        )
        return {"status": "ok", "lead_id": lead_id}

    # -----------------------------------------------------------------
    # MEETING DONE (transcript ready)
    # -----------------------------------------------------------------

    @http.route(
        "/odoo/api/sales_ai/meeting_done",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def meeting_done(self):
        """
        Called by n8n after a client meeting transcript is ready.
        Accepts plain JSON POST (Content-Type: application/json).

        Accepts TWO formats:

        **Format A – Apollo Transcript Service webhook** (preferred):
        {
            "lead_id": int,
            "job_id": "53",
            "status": "completed",
            "data": {
                "meeting_title": str,
                "conversation_id": str,
                "conversation_url": str,
                "segments": [{"speaker": str, "text": str, "timestamp": str}, ...],
                "extracted_at": str,
                "extraction_method": str
            }
        }

        **Format B – flat / legacy**:
        {
            "lead_id": int,
            "transcript": str,
            "meeting_date": str,
            "meeting_duration": int,
            "attendees": [...],
            "conversation_id": str,
            "meeting_name": str,
            "source": str
        }
        """
        try:
            raw_body = request.httprequest.get_data(as_text=True)
            payload = json.loads(raw_body) if raw_body else {}
        except (json.JSONDecodeError, Exception) as exc:
            _logger.error("sales_ai: [MEETING-DONE] invalid JSON: %s", exc)
            return request.make_json_response({"error": "invalid_json"}, status=400)

        # Unwrap n8n envelope (list / body / params wrappers)
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if "body" in payload and isinstance(payload.get("body"), dict):
            payload = payload["body"]
        elif "params" in payload and isinstance(payload.get("params"), dict) and payload["params"]:
            payload = payload["params"]

        if not _check_n8n_auth(request.httprequest.headers):
            _logger.warning("sales_ai: [MEETING-DONE] unauthorized")
            return request.make_json_response({"error": "unauthorized"}, status=401)

        # Extract lead_id: top-level OR from odoo_payload.payload.lead_id
        odoo_payload = payload.get("odoo_payload") or {}
        odoo_inner = odoo_payload.get("payload") or {} if isinstance(odoo_payload, dict) else {}
        lead_id = payload.get("lead_id") or odoo_inner.get("lead_id")
        if not lead_id:
            _logger.warning("sales_ai: [MEETING-DONE] missing lead_id")
            return request.make_json_response({"error": "missing_lead_id"}, status=400)

        # Detect Apollo format (has "data.segments") vs legacy flat
        apollo_data = payload.get("data") or {}
        segments = apollo_data.get("segments") if isinstance(apollo_data, dict) else None

        if segments and isinstance(segments, list):
            transcript = self._segments_to_transcript(segments)
            conversation_id = apollo_data.get("conversation_id") or ""
            conversation_url = apollo_data.get("conversation_url") or ""
            speakers = list({seg.get("speaker") for seg in segments if seg.get("speaker")})

            meeting_name = (
                odoo_inner.get("meeting_name")
                or apollo_data.get("meeting_title")
                or ""
            )
            source = odoo_inner.get("source") or "apollo"
            meeting_date = odoo_inner.get("meeting_start", "")[:10] if odoo_inner.get("meeting_start") else ""
            meeting_start = odoo_inner.get("meeting_start") or ""
            meeting_stop = odoo_inner.get("meeting_stop") or ""
            meeting_duration = int(payload.get("meeting_duration") or 0)
            if not meeting_duration and meeting_start and meeting_stop:
                try:
                    from datetime import datetime
                    fmt = "%Y-%m-%d %H:%M:%S"
                    dt_start = datetime.strptime(meeting_start, fmt)
                    dt_stop = datetime.strptime(meeting_stop, fmt)
                    meeting_duration = int((dt_stop - dt_start).total_seconds() / 60)
                except Exception:
                    pass

            odoo_participants = odoo_inner.get("participants") or []
            attendees = [{"name": n, "is_client": True} for n in odoo_participants]
            if not attendees:
                attendees = [{"name": s, "is_client": True} for s in speakers]

            _logger.info(
                "sales_ai: [MEETING-DONE] apollo format — lead=%s, segments=%d, transcript=%d chars",
                lead_id, len(segments), len(transcript),
            )
        else:
            transcript = payload.get("transcript") or ""
            meeting_name = payload.get("meeting_name") or ""
            conversation_id = payload.get("conversation_id") or ""
            conversation_url = payload.get("conversation_url") or ""
            source = payload.get("source") or "meeting_done"
            attendees = payload.get("attendees") or []
            meeting_date = payload.get("meeting_date") or ""
            meeting_duration = int(payload.get("meeting_duration") or 0)
            _logger.info(
                "sales_ai: [MEETING-DONE] legacy format — lead=%s, transcript=%d chars",
                lead_id, len(transcript),
            )

        if not transcript:
            _logger.warning("sales_ai: [MEETING-DONE] empty transcript for lead %s", lead_id)
            return request.make_json_response({"error": "empty_transcript"}, status=400)

        lead = request.env["crm.lead"].with_user(SUPERUSER_ID).browse(int(lead_id))
        if not lead.exists():
            _logger.warning("sales_ai: [MEETING-DONE] lead %s not found", lead_id)
            return request.make_json_response({"error": "lead_not_found"}, status=404)

        # Spawn background thread so n8n gets a fast response — MOM generation
        # (Claude call + chatter + activity) happens asynchronously.
        from ..models.crm_lead import _bg_client_mom_worker

        mom_kwargs = {
            "transcript": transcript,
            "meeting_date": meeting_date,
            "meeting_duration": meeting_duration,
            "attendees": attendees,
            "conversation_id": conversation_id,
            "conversation_url": conversation_url,
            "source": source,
            "meeting_name": meeting_name,
            "request_payload_json": json.dumps(payload, ensure_ascii=False),
        }
        dbname = request.env.cr.dbname
        t = threading.Thread(
            target=_bg_client_mom_worker,
            args=(dbname, SUPERUSER_ID, int(lead_id), mom_kwargs),
            name="bg-mom-%s" % lead_id,
        )
        t.start()

        _logger.info(
            "sales_ai: [MEETING-DONE] background MOM thread spawned for lead %s", lead_id,
        )
        return request.make_json_response({"status": "ok", "async": True})

    @staticmethod
    def _segments_to_transcript(segments):
        """Convert Apollo segments list to a readable transcript string.

        Input:  [{"speaker": "Alice", "text": "Hello", "timestamp": "00:01"}, ...]
        Output: "[00:01] Alice: Hello\n[00:02] Bob: Hi\n..."
        """
        lines = []
        for seg in segments:
            ts = seg.get("timestamp") or ""
            speaker = seg.get("speaker") or "Unknown"
            text = seg.get("text") or ""
            if ts:
                lines.append(f"[{ts}] {speaker}: {text}")
            else:
                lines.append(f"{speaker}: {text}")
        return "\n".join(lines)

    # -----------------------------------------------------------------
    # MEETING NO-SHOW
    # -----------------------------------------------------------------

    @http.route(
        "/odoo/api/sales_ai/meeting_no_show",
        type="jsonrpc",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def meeting_no_show(self, **payload):
        """
        Called by n8n when a scheduled meeting has no-show (Calendly detects cancellation
        or rep marks it manually).

        Expected payload:
        {
            "lead_id": int,
            "no_show_count": int,   1 = first no-show, 2 = second, etc.
        }
        """
        lead_id = payload.get("lead_id")
        if not lead_id:
            return {"error": "missing_lead_id"}

        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            return {"error": "lead_not_found"}

        no_show_count = int(payload.get("no_show_count") or 1)
        _logger.info(
            "sales_ai: Meeting no-show for lead %s (count=%d)", lead_id, no_show_count
        )
        lead.action_no_show_followup(no_show_count=no_show_count)
        return {"status": "ok"}

    # -----------------------------------------------------------------
    # PRESALE TRANSCRIPT (routes to ticket or lead)
    # -----------------------------------------------------------------

    @http.route(
        "/odoo/api/sales_ai/presale_transcript",
        type="jsonrpc",
        auth="api_key",
        methods=["POST"],
        csrf=False,
    )
    def presale_transcript(self, **payload):
        """
        Called by n8n "Presale MOM Splitter" workflow after a presale meeting.
        Routes the transcript directly to the lead — no project.task involved.

        Expected payload:
        {
            "lead_id": int,
            "transcript": str,
            "meeting_date": str,        ISO date
            "meeting_duration": int,    minutes
            "attendees": [...],
            "prior_open_items": [...],
        }
        """
        lead_id = payload.get("lead_id")
        transcript = payload.get("transcript") or ""

        if not lead_id or not transcript:
            return {"error": "missing_lead_or_transcript"}

        lead = request.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            return {"error": "lead_not_found"}

        _logger.info(
            "sales_ai: Presale transcript for lead %s — ref %s (%d chars)",
            lead_id, lead.x_presale_ref or "no-ref", len(transcript),
        )
        lead.action_generate_presale_mom_from_transcript(
            transcript=transcript,
            meeting_date=payload.get("meeting_date"),
            meeting_duration=payload.get("meeting_duration"),
            attendees=payload.get("attendees") or [],
            prior_open_items=payload.get("prior_open_items") or [],
        )
        return {"status": "ok", "lead_id": lead_id, "presale_ref": lead.x_presale_ref}

    # ------------------------------------------------------------------
    # MOM activity creation – transcript + attachment extracts
    # ------------------------------------------------------------------

    @http.route(
        "/odoo/api/create_mom_activity",
        type="jsonrpc",
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
