import base64
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, api, fields, models, _, tools
from odoo.exceptions import UserError

from . import prompts

_logger = logging.getLogger("sales_ai")  # unified logger prefix


def _clean_internal_mom_text(text: str) -> str:
    """Normalize Claude internal MOM text so chatter stays readable.

    - Strip markdown headings (##, ###), bullets, blockquotes.
    - Drop markdown tables and horizontal rules.
    - Remove loud meta flags like RED FLAG / DATA QUALITY FLAG lines.
    """
    if not text:
        return ""

    cleaned_lines: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            cleaned_lines.append("")
            continue

        # Drop pure markdown table separators / horizontal rules
        if re.match(r"^\|[-\s|]+\|?$", line):
            continue
        if re.match(r"^-{3,}$", line):
            continue

        # Drop very meta commentary lines
        lower = line.lower()
        if "red flag" in lower or "data quality flag" in lower:
            continue

        # Strip common markdown prefixes
        line = re.sub(r"^#{1,6}\s*", "", line)  # headings
        line = re.sub(r"^>\s*", "", line)  # blockquote
        line = re.sub(r"^[-*+]\s+", "", line)  # bullet
        line = re.sub(r"^\d+\.\s+", "", line)  # numbered list marker

        cleaned_lines.append(line)

    # Collapse excessive blank lines
    result_lines: List[str] = []
    blank_streak = 0
    for l in cleaned_lines:
        if not l:
            blank_streak += 1
            if blank_streak > 1:
                continue
        else:
            blank_streak = 0
        result_lines.append(l)

    return "\n".join(result_lines).strip()


def _bg_genuine_pipeline_worker(dbname, uid, lead_ids):
    """Background thread: run Apollo enrichment + scoring + auto-ack for genuine leads.

    Each lead gets its own DB transaction so a failure on one lead doesn't
    block the others.
    """
    try:
        from odoo.orm.registry import Registry
        registry = Registry(dbname)
    except Exception:
        _logger.error("sales_ai: [BG-PIPELINE] Cannot obtain registry for db=%s", dbname, exc_info=True)
        return

    for lead_id in lead_ids:
        try:
            with registry.cursor() as cr:
                env = api.Environment(cr, uid, {})
                lead = env["crm.lead"].browse(lead_id)
                if not lead.exists() or lead.x_classification != "genuine":
                    continue
                _logger.info(
                    "sales_ai: [STEP 2/3] GENUINE — lead_id=%s triggering Apollo enrichment via n8n",
                    lead.id,
                )
                lead.action_trigger_lead_intake()
                _logger.info(
                    "sales_ai: [STEP 2/3] DONE — lead_id=%s n8n intake triggered; "
                    "awaiting /api/sales_ai/lead_intake_complete callback",
                    lead.id,
                )
        except Exception:
            _logger.error(
                "sales_ai: [STEP 2/3] FAIL — pipeline error for lead_id=%s. "
                "Check Settings → Sales AI → n8n Webhook URL.",
                lead_id, exc_info=True,
            )


def _bg_client_mom_worker(dbname, uid, lead_id, kwargs):
    """Background thread: generate client MOM from transcript.

    Runs in its own DB cursor so the calling HTTP request can return
    immediately without waiting for Claude + chatter + activity creation.
    """
    try:
        from odoo.orm.registry import Registry
        registry = Registry(dbname)
    except Exception:
        _logger.error("sales_ai: [BG-MOM] Cannot obtain registry for db=%s", dbname, exc_info=True)
        return

    try:
        with registry.cursor() as cr:
            env = api.Environment(cr, uid, {})
            lead = env["crm.lead"].browse(lead_id)
            if not lead.exists():
                _logger.warning("sales_ai: [BG-MOM] lead %s not found", lead_id)
                return
            lead.action_generate_client_mom(**kwargs)
            _logger.info("sales_ai: [BG-MOM] completed for lead %s", lead_id)
    except Exception:
        _logger.error(
            "sales_ai: [BG-MOM] FAILED for lead %s",
            lead_id, exc_info=True,
        )


class CrmLead(models.Model):
    _inherit = "crm.lead"

    # -------------------------------------------------------------------------
    # Custom fields – Lead qualification & enrichment
    # -------------------------------------------------------------------------

    # High-level classification (backwards compatible with earlier versions)
    x_lead_quality = fields.Selection(
        [
            ("genuine", "Genuine"),
            ("marketing", "Marketing"),
            ("junk", "Junk"),
        ],
        string="Lead Quality (Legacy)",
        tracking=True,
    )

    # Detailed classification as per Inbound_Sales_Mindmap_Workflow.md
    x_classification = fields.Selection(
        [
            ("genuine", "Genuine"),
            ("marketing", "Marketing"),
            ("junk", "Junk/Spam"),
            ("job_seeker", "Job Seeker"),
        ],
        string="Inbound Classification",
        tracking=True,
    )
    x_classification_conf = fields.Float(
        "Classification Confidence (0-100)",
        help="AI confidence score for lead classification.",
        tracking=True,
    )
    x_classification_reason = fields.Char(
        "Classification Reason", help="Short explanation from the AI classifier."
    )
    x_lead_score = fields.Integer("Lead Score (0-100)", tracking=True)
    x_lead_score_band = fields.Selection(
        [
            ("hot", "Hot"),
            ("warm", "Warm"),
            ("neutral", "Neutral"),
            ("cold", "Cold"),
        ],
        string="Lead Score Band",
        tracking=True,
    )
    x_lead_score_breakdown = fields.Text(
        "Lead Score Breakdown (JSON)",
        help="JSON breakdown of how the lead score was calculated.",
    )
    x_lead_score_rationale = fields.Text(
        "Lead Score Rationale",
        help="Short narrative explaining why the score was assigned.",
    )
    x_followup_stage = fields.Integer("Follow-up Stage", default=0, tracking=True)
    x_last_reply_date = fields.Datetime("Last Reply Date", tracking=True)
    x_reply_intent = fields.Selection(
        [
            ("interested", "Interested"),
            ("meeting_booked", "Meeting Booked"),
            ("not_interested", "Not Interested"),
            ("ooo", "Out of Office"),
            ("wrong_person", "Wrong Person"),
            ("referral", "Referral"),
            ("generic_positive", "Generic Positive"),
            ("unsubscribe", "Unsubscribe"),
            ("question", "Question"),
            ("negotiating", "Negotiating"),
        ],
        string="Reply Intent",
        tracking=True,
    )
    x_ooo_return_date = fields.Date("OOO Return Date")
    x_unsubscribed = fields.Boolean("Unsubscribed from Outreach", default=False)

    # Enrichment fields (populated from Apollo via n8n)
    x_is_it_company = fields.Boolean("Is IT Company")
    x_employee_count = fields.Integer("Employee Count")
    x_annual_revenue = fields.Monetary(
        "Annual Revenue", currency_field="company_currency"
    )
    x_tech_stack = fields.Text("Technology Stack (JSON Array)")
    x_is_decision_maker = fields.Boolean("Is Decision Maker")
    x_seniority = fields.Selection(
        [
            ("c_level", "C-level"),
            ("vp", "VP"),
            ("director", "Director"),
            ("manager", "Manager"),
            ("other", "Other"),
        ],
        string="Seniority",
    )
    x_contact_score = fields.Integer("Contact Score (0-100)")
    x_intent_score = fields.Integer("Intent Score (0-100)")
    x_linkedin_url = fields.Char("LinkedIn URL")
    x_apollo_data_raw = fields.Text("Apollo Raw Data", help="Raw JSON from Apollo.io")
    x_apollo_person_id = fields.Char("Apollo Person ID")
    x_attachment_extracts_json = fields.Text(
        "Attachment Extracts (JSON)",
        help="Cached text extracted from attachments (PDF, images, DOCX) as JSON.",
    )
    x_mom_history = fields.Text(
        "MOM History (JSON)",
        help="Optional JSON array of structured MOM entries.",
    )
    x_apollo_match = fields.Boolean("Apollo Match Found", help="True if Apollo People API returned a match")
    x_enrichment_done = fields.Boolean("Enrichment Completed")
    x_scoring_done = fields.Boolean("Scoring Completed")
    x_stale_monitor_start = fields.Date("Stale Monitor Start")

    # Extended structured enrichment fields (from EnrichmentStructurerAgent)
    x_industry = fields.Char("Industry")
    x_subindustry = fields.Char("Sub-industry")
    x_employee_count_range = fields.Char("Employee Count Range")
    x_revenue_range = fields.Char("Annual Revenue Range")
    x_hq_country_id = fields.Many2one("res.country", string="HQ Country")
    x_hq_city = fields.Char("HQ City")
    x_founded_year = fields.Integer("Founded Year")
    x_company_funding_stage = fields.Char("Funding Stage")
    x_company_linkedin_url = fields.Char("Company LinkedIn URL")
    x_website = fields.Char("Website")

    x_contact_job_title = fields.Char("Contact Job Title")
    x_contact_seniority_structured = fields.Selection(
        [
            ("c_level", "C-Level"),
            ("vp", "VP"),
            ("director", "Director"),
            ("manager", "Manager"),
            ("ic", "Individual Contributor"),
            ("unknown", "Unknown"),
        ],
        string="Contact Seniority (Structured)",
    )
    x_direct_email = fields.Char("Direct Email")
    x_direct_phone = fields.Char("Direct Phone")
    x_contact_linkedin_url = fields.Char("Contact LinkedIn URL")
    x_contact_decision_authority = fields.Selection(
        [("yes", "Yes"), ("no", "No"), ("unknown", "Unknown")],
        string="Decision-making Authority",
    )

    x_likely_pain_point = fields.Text("Likely Pain Point")
    x_similar_companies_won = fields.Text("Similar Companies We've Won")
    x_icp_match_signals = fields.Text("ICP Match Signals (JSON/List)")
    x_icp_disqualify_signals = fields.Text("ICP Disqualifying Signals (JSON/List)")
    x_apollo_conversation_summary = fields.Text("Apollo Conversation Summary")
    x_enrichment_conf = fields.Float("Enrichment Confidence (0-100)")
    x_enrichment_notes = fields.Text("Enrichment Notes")
    x_enrichment_source = fields.Char("Enrichment Source")
    x_enrichment_date = fields.Datetime("Enrichment Date")
    x_lead_language = fields.Char("Lead Language")
    x_inquiry_category = fields.Selection(
        [
            ("new_implementation", "New Implementation"),
            ("upgrade", "Upgrade"),
            ("support", "Support"),
            ("consulting", "Consulting"),
            ("other", "Other"),
        ],
        string="Inquiry Category",
    )
    x_inquiry_urgency = fields.Selection(
        [("high", "High"), ("medium", "Medium"), ("low", "Low")],
        string="Inquiry Urgency",
    )
    x_follow_up_angle = fields.Char("Follow-up Angle")

    # -------------------------------------------------------------------------
    # Presale fields – everything managed on the lead (no project.task needed)
    # -------------------------------------------------------------------------

    x_presale_status = fields.Selection(
        [
            ("none", "No Presale"),
            ("open", "Presale Open"),
            ("ready_for_wbs", "Ready for WBS"),
            ("wbs_done", "WBS Done"),
            ("ready_for_proposal", "Ready for Proposal"),
            ("proposal_generated", "Proposal Generated"),
            ("proposal_sent", "Proposal Sent"),
        ],
        default="none",
        string="Presale Status",
        tracking=True,
    )
    x_wbs_sheet_url = fields.Char("WBS Sheet URL")
    x_proposal_drive_url = fields.Char("Proposal Drive URL")
    x_last_agenda_date = fields.Date("Last Presale Agenda Date")
    x_retro_logged = fields.Boolean("Retro Logged")

    # Presale reference number (auto-assigned when presale opens, e.g. PST-42)
    x_presale_ref = fields.Char(
        "Presale Reference",
        help="Auto-generated presale reference (e.g. PST-42). Set when presale is opened.",
        readonly=True,
    )
    x_wbs_json = fields.Text(
        "WBS JSON",
        help="Structured WBS JSON generated by WBSGeneratorAgent (Sonnet).",
    )
    x_ticket_gist = fields.Text(
        "Presale Gist",
        help="AI-generated summary of all lead context for the presale team (TicketGistAgent).",
    )
    x_presale_mom_history = fields.Text(
        "Presale MOM History",
        help="JSON list of presale MOM texts from each presale meeting.",
    )
    transcript_ids = fields.One2many(
        "sales.ai.meeting.transcript",
        "lead_id",
        string="Meeting Transcripts",
    )

    # -------------------------------------------------------------------------
    # Attachment text cache – extract once, reuse for all AI calls
    # -------------------------------------------------------------------------

    x_attachment_summaries = fields.Text(
        "Attachment Text Cache",
        help="JSON dict mapping attachment_id -> extracted text / description. "
        "Auto-populated when attachments are added. Claude reads this cache "
        "instead of re-processing files each time.",
    )

    def _get_company_currency(self):
        return self.env.company.currency_id

    company_currency = fields.Many2one(
        "res.currency", string="Company Currency", default=_get_company_currency
    )

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _business_day_offset(self, base_date: datetime, days: int) -> datetime:
        """Move forward `days` business days from base_date.

        Skips weekends and public holidays defined in
        sales_ai.public_holidays_json (list of YYYY-MM-DD strings).
        """
        ICP = self.env["ir.config_parameter"].sudo()
        holidays_raw = ICP.get_param("sales_ai.public_holidays_json", default="[]")
        try:
            holiday_dates = {
                fields.Date.from_string(d)
                for d in json.loads(holidays_raw or "[]")
                if d
            }
        except Exception:
            holiday_dates = set()

        date = base_date
        added = 0
        while added < days:
            date += relativedelta(days=1)
            if date.weekday() < 5 and date.date() not in holiday_dates:
                added += 1
        return date

    def _claude(self):
        return self.env["claude.service"]

    def _n8n(self):
        return self.env["sales.ai.n8n"]

    # =========================================================================
    # PIPELINE DIAGNOSTICS
    # =========================================================================

    @api.model
    def action_test_pipeline(self):
        """
        Self-test for the AI pipeline. Call from Odoo shell:

            env['crm.lead'].action_test_pipeline()

        Checks Claude API key, Claude connectivity (Haiku ping), and n8n URL config.
        Logs results with [DIAG] prefix — grep 'sales_ai.*DIAG' in odoo.log.
        Returns dict with ok/failed counts.
        """
        _logger.info("sales_ai: [DIAG] ========== PIPELINE SELF-TEST START ==========")
        ok_count = 0
        fail_count = 0

        # 1. Check Claude API key
        api_key = self.env["ir.config_parameter"].sudo().get_param("sales_ai.claude_api_key", "")
        if api_key:
            _logger.info("sales_ai: [DIAG] OK Claude API key is SET (first 8 chars: %s...)", api_key[:8])
            ok_count += 1
        else:
            _logger.error(
                "sales_ai: [DIAG] FAIL Claude API key is MISSING. "
                "Set it: Settings -> Technical -> System Parameters -> sales_ai.claude_api_key"
            )
            fail_count += 1

        # 2. Test Claude Haiku connectivity
        if api_key:
            try:
                ping_result = self._claude().call(
                    tier="haiku",
                    system_prompt='Reply with exactly: {"ok": true}',
                    user_message="ping",
                    max_tokens=20,
                    expect_json=True,
                )
                if isinstance(ping_result, dict) and ping_result.get("ok"):
                    _logger.info("sales_ai: [DIAG] OK Claude Haiku ping OK — response: %s", ping_result)
                    ok_count += 1
                else:
                    _logger.error("sales_ai: [DIAG] FAIL Claude Haiku ping — unexpected response: %s", ping_result)
                    fail_count += 1
            except Exception as exc:
                _logger.error("sales_ai: [DIAG] FAIL Claude Haiku ping EXCEPTION: %s", exc, exc_info=True)
                fail_count += 1
        else:
            _logger.warning("sales_ai: [DIAG] SKIP Claude connectivity test (no API key)")

        # 3. Check n8n URL
        n8n_url = self.env["ir.config_parameter"].sudo().get_param("sales_ai.n8n_webhook_base_url", "")
        if n8n_url:
            _logger.info("sales_ai: [DIAG] OK n8n webhook URL is SET: %s", n8n_url)
            ok_count += 1
        else:
            _logger.error(
                "sales_ai: [DIAG] FAIL n8n webhook URL is MISSING. "
                "Set it: Settings -> Technical -> System Parameters -> sales_ai.n8n_webhook_base_url"
            )
            fail_count += 1

        # 4. Check marketing user
        mkt_uid = self.env["ir.config_parameter"].sudo().get_param("sales_ai.marketing_user_id", "")
        if mkt_uid and int(mkt_uid or 0):
            _logger.info("sales_ai: [DIAG] OK Marketing user ID is SET: %s", mkt_uid)
            ok_count += 1
        else:
            _logger.warning(
                "sales_ai: [DIAG] WARN Marketing user ID is MISSING — "
                "non-genuine leads won't be re-assigned. "
                "Set: Settings -> Technical -> System Parameters -> sales_ai.marketing_user_id"
            )
            fail_count += 1

        # 5. Check junk_filter_system prompt exists
        from . import prompts as _prompts
        if _prompts.PROMPTS.get("junk_filter_system"):
            _logger.info("sales_ai: [DIAG] OK junk_filter_system prompt is defined")
            ok_count += 1
        else:
            _logger.error("sales_ai: [DIAG] FAIL junk_filter_system prompt is MISSING in prompts.py")
            fail_count += 1

        _logger.info(
            "sales_ai: [DIAG] ========== SELF-TEST COMPLETE: %d OK, %d FAILED ==========",
            ok_count, fail_count,
        )
        return {"ok": ok_count, "failed": fail_count}

    # =========================================================================
    # ATTACHMENT HANDLING
    # =========================================================================

    def action_extract_attachment_texts(self):
        """
        Extract text from all unprocessed attachments on this lead.

        Strategy:
        - PDF/DOC/TXT: extract raw text, truncate to 4000 chars per file
        - Images (JPG/PNG): send to Claude Vision for a one-time description
        - Cache results in x_attachment_summaries so we never re-process

        This method is called:
        - Manually via a "Sync Attachments" button on the lead form
        - Automatically before any AI call that needs attachment context
        """
        for lead in self:
            existing_cache = {}
            if lead.x_attachment_summaries:
                try:
                    existing_cache = json.loads(lead.x_attachment_summaries)
                except Exception:
                    existing_cache = {}

            attachments = self.env["ir.attachment"].sudo().search([
                ("res_model", "=", "crm.lead"),
                ("res_id", "=", lead.id),
            ])

            updated = False
            for att in attachments:
                att_key = str(att.id)
                if att_key in existing_cache:
                    continue  # already cached

                mimetype = (att.mimetype or "").lower()
                text = ""

                if "pdf" in mimetype:
                    text = self._extract_pdf_text(att)
                elif any(t in mimetype for t in ("text", "csv", "xml", "json", "html")):
                    try:
                        raw = base64.b64decode(att.datas or b"")
                        text = raw.decode("utf-8", errors="replace")[:4000]
                    except Exception:
                        text = "[Could not decode text file]"
                elif any(t in mimetype for t in ("image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp")):
                    text = self._describe_image_attachment(att)
                elif any(t in mimetype for t in ("msword", "wordprocessing", "opendocument")):
                    # For DOC/DOCX: extract what we can via basic parsing
                    text = self._extract_doc_text(att)
                else:
                    text = f"[Attachment: {att.name}, type: {att.mimetype}, size: {att.file_size} bytes]"

                existing_cache[att_key] = {
                    "name": att.name,
                    "mimetype": att.mimetype,
                    "summary": (text or "")[:4000],
                }
                updated = True
                _logger.info(
                    "sales_ai: Extracted text from attachment %s (%s) on lead %s",
                    att.name, att.mimetype, lead.id,
                )

            if updated:
                lead.x_attachment_summaries = json.dumps(existing_cache, ensure_ascii=False)

    def _extract_pdf_text(self, attachment):
        """Extract text from a PDF attachment using PyPDF2 or pdfplumber."""
        try:
            import io
            raw = base64.b64decode(attachment.datas or b"")
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(raw)) as pdf:
                    pages_text = []
                    for page in pdf.pages[:20]:  # max 20 pages
                        pages_text.append(page.extract_text() or "")
                    return "\n".join(pages_text)[:4000]
            except ImportError:
                pass
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(io.BytesIO(raw))
                pages_text = []
                for page in reader.pages[:20]:
                    pages_text.append(page.extract_text() or "")
                return "\n".join(pages_text)[:4000]
            except ImportError:
                return "[PDF detected but no PDF parser available (install pdfplumber or PyPDF2)]"
        except Exception as exc:
            _logger.warning("sales_ai: PDF extraction failed for %s: %s", attachment.name, exc)
            return "[PDF extraction failed]"

    def _extract_doc_text(self, attachment):
        """Extract text from DOC/DOCX using python-docx."""
        try:
            import io
            raw = base64.b64decode(attachment.datas or b"")
            try:
                from docx import Document
                doc = Document(io.BytesIO(raw))
                text = "\n".join(p.text for p in doc.paragraphs)
                return text[:4000]
            except ImportError:
                return "[DOCX detected but python-docx not installed]"
        except Exception as exc:
            _logger.warning("sales_ai: DOC extraction failed for %s: %s", attachment.name, exc)
            return "[DOC extraction failed]"

    def _describe_image_attachment(self, attachment):
        """Send image to Claude Vision for a one-time description."""
        try:
            raw_b64 = attachment.datas
            if not raw_b64:
                return "[Empty image]"
            # Use Claude's vision capability
            media_type = attachment.mimetype or "image/jpeg"
            resp = self._claude().call_vision(
                image_b64=raw_b64.decode() if isinstance(raw_b64, bytes) else raw_b64,
                media_type=media_type,
                prompt="Describe this image in the context of a B2B sales lead. "
                       "Focus on: company logos, product screenshots, diagrams, "
                       "business cards, or any business-relevant information. "
                       "Keep description under 300 words.",
                max_tokens=400,
            )
            return resp or "[Image — no description generated]"
        except Exception as exc:
            _logger.warning("sales_ai: Image description failed for %s: %s", attachment.name, exc)
            return f"[Image: {attachment.name}]"

    def _get_attachment_context(self) -> str:
        """Return cached attachment summaries as a text block for AI prompts."""
        self.ensure_one()
        if not self.x_attachment_summaries:
            return ""
        try:
            cache = json.loads(self.x_attachment_summaries)
        except Exception:
            return ""
        parts = []
        for _att_id, info in cache.items():
            parts.append(f"--- {info.get('name', 'Unknown')} ({info.get('mimetype', '')}) ---\n{info.get('summary', '')}")
        return "\n\n".join(parts)

    # =========================================================================
    # PHASE 1: UNIFIED LEAD INTAKE (replaces old junk filter + enrichment)
    # =========================================================================
    #
    # Flow:
    #   1. Lead created → automation sends lead data to n8n
    #   2. n8n calls Apollo People Enrichment API (email, name, domain)
    #   3. n8n calls Apollo Organization Enrichment API (domain)
    #   4. n8n calls back: /api/sales_ai/lead_intake_complete
    #   5. Odoo: enrich → classify (genuine/marketing/junk) → score → assign
    #
    # If Apollo has NO match → classify from email content only.

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        for lead in leads:
            _logger.info(
                "sales_ai: [PIPELINE START] lead_id=%s name=%r email=%s source=%s",
                lead.id, lead.name, lead.email_from or "(none)",
                lead.source_id.name if lead.source_id else "direct",
            )
            # STEP 1/3 — Junk filter (Haiku ~$0.003) BEFORE Apollo (~$0.02)
            _logger.info("sales_ai: [STEP 1/3] Junk filter — lead_id=%s", lead.id)
            t0 = time.time()
            try:
                lead._classify_lead_quality(has_apollo_data=False)
            except Exception:
                _logger.error(
                    "sales_ai: [STEP 1/3] FAIL — junk filter error lead_id=%s (%.2fs)",
                    lead.id, time.time() - t0, exc_info=True,
                )
                continue
            _logger.info(
                "sales_ai: [STEP 1/3] DONE — lead_id=%s classification=%s conf=%.0f%% (%.2fs)",
                lead.id, lead.x_classification or "none",
                lead.x_classification_conf or 0.0, time.time() - t0,
            )
            # Route non-genuine leads immediately (fast, no external calls)
            if lead.x_classification == "junk":
                lead.active = False
                _logger.info(
                    "sales_ai: [STEP 2/3] JUNK — lead_id=%s auto-archived after junk filter",
                    lead.id,
                )
            elif lead.x_classification != "genuine":
                _logger.info(
                    "sales_ai: [STEP 2/3] NON-GENUINE — lead_id=%s classification=%s "
                    "Apollo enrichment SKIPPED (saves ~$0.02), routed to Marketing User",
                    lead.id,
                    lead.x_classification,
                )

        # Defer genuine lead pipeline (Apollo + scoring + auto-ack) to background
        # so the HTTP response returns quickly and the UI doesn't show "Connection lost".
        genuine_ids = [l.id for l in leads if l.x_classification == "genuine"]
        if genuine_ids:
            _logger.info(
                "sales_ai: Deferring pipeline for %d genuine lead(s): %s",
                len(genuine_ids), genuine_ids,
            )
            self._defer_genuine_pipeline(genuine_ids)

        return leads

    def _defer_genuine_pipeline(self, lead_ids):
        """Schedule Apollo enrichment + scoring in a background thread after commit."""
        dbname = self.env.cr.dbname
        uid = self.env.uid

        @self.env.cr.postcommit.add
        def _start_bg():
            thread = threading.Thread(
                target=_bg_genuine_pipeline_worker,
                args=(dbname, uid, lead_ids),
                daemon=True,
                name="sales_ai_pipeline_%s" % lead_ids,
            )
            thread.start()

    def action_trigger_lead_intake(self):
        """Send lead data to n8n for Apollo enrichment.

        When called from the UI, show a toast notification for both success and
        failure instead of raising blocking errors.

        If context key ``sales_ai_force_full_intake`` is True, the caller is
        explicitly asking to resume the full intake pipeline (enrich → classify
        → score → auto-ack → follow-ups) even if some steps ran earlier.
        """
        self.ensure_one()
        force_full = bool(self.env.context.get("sales_ai_force_full_intake"))
        notifications = []
        for lead in self:
            email = lead.email_from or ""
            domain = email.split("@")[-1] if "@" in email else ""
            payload = {
                "lead_id": lead.id,
                "email": email,
                "name": lead.contact_name or lead.name or "",
                "company": lead.partner_id.name if lead.partner_id else "",
                "domain": domain,
                "phone": lead.phone or "",
                "description": (lead.description or "")[:2000],
                "source": lead.source_id.display_name if lead.source_id else "",
                "force_full_intake": force_full,
            }
            _logger.info(
                "sales_ai: [INTAKE] lead_id=%s sending to n8n — email=%s domain=%s",
                lead.id, email, domain,
            )
            try:
                result = self._n8n().post("lead_intake", payload)
                # If n8n returned Apollo data synchronously, apply it immediately.
                apollo_result = isinstance(result, dict) and result.get("apollo_result") or None
                if apollo_result:
                    # n8n may either return:
                    #  - {"person": {...}, "organization": {...}}
                    #  - or a direct Apollo "person" object with nested "organization"
                    if isinstance(apollo_result, dict) and (
                        "person" in apollo_result or "organization" in apollo_result
                    ):
                        person = apollo_result.get("person") or {}
                        org = apollo_result.get("organization") or {}
                    else:
                        person = apollo_result
                        org = (
                            apollo_result.get("organization")
                            if isinstance(apollo_result, dict)
                            else {}
                        ) or {}
                    match = bool(person or org)
                    _logger.info(
                        "sales_ai: [INTAKE] Applying synchronous Apollo enrichment + scoring for lead %s (match=%s)",
                        lead.id,
                        match,
                    )
                    lead.action_lead_intake_complete(
                        person, org, match, force_full_intake=force_full
                    )
                _logger.info(
                    "sales_ai: [INTAKE] n8n call OK — lead_id=%s "
                    "awaiting Apollo callback at /api/sales_ai/lead_intake_complete",
                    lead.id,
                )
                notifications.append(
                    {
                        "title": _("Enrichment sync triggered"),
                        "type": "success",
                        "message": _(
                            "Lead %(id)s has been sent to n8n for Apollo enrichment. "
                            "If Apollo data was returned immediately, enrichment and scoring "
                            "have already been applied."
                        )
                        % {"id": lead.id},
                        "sticky": False,
                    }
                )
            except Exception as exc:
                _logger.error(
                    "sales_ai: [INTAKE] FAIL — n8n unreachable for lead_id=%s. "
                    "Verify n8n URL/secret in Settings → Sales AI → n8n Configuration.",
                    lead.id, exc_info=True,
                )
                # Log in chatter and create a follow-up activity for visibility
                lead.message_post(
                    body=_(
                        "n8n enrichment call failed: %s. "
                        "Please open Sales AI settings and check the n8n connection."
                    )
                    % str(exc),
                    subtype_xmlid="mail.mt_note",
                )
                # activity_type = self.env.ref(
                #     "mail.mail_activity_data_todo", raise_if_not_found=False
                # )
                # self.env["mail.activity"].sudo().create(
                #     {
                #         "res_model": "crm.lead",
                #         "res_id": lead.id,
                #         "user_id": lead.user_id.id or self.env.user.id,
                #         "note": _(
                #             "n8n enrichment failed for this lead. "
                #             "Check the n8n connection and secrets in Sales AI settings."
                #         ),
                #         "date_deadline": fields.Date.today(),
                #     }
                # )
                _logger.info(
                    "sales_ai: [INTAKE] Created activity and chatter log for n8n failure on lead_id=%s",
                    lead.id,
                )
                notifications.append(
                    {
                        "title": _("Enrichment sync failed"),
                        "type": "warning",
                        "message": _(
                            "Could not reach the n8n enrichment service for lead %(id)s.\n"
                            "Details: %(details)s\n"
                            "Please verify the n8n Webhook URL, environment (Test/Live) "
                            "and secret in Settings → Sales AI → n8n Configuration."
                        )
                        % {"id": lead.id, "details": str(exc)},
                        "sticky": True,
                    }
                )

        # For multiple leads, show the last notification (most recent lead).
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": notifications[-1] if notifications else {
                "title": _("Enrichment"),
                "type": "info",
                "message": _("Nothing to sync."),
                "sticky": False,
            },
        }

    def action_lead_intake_complete(
        self,
        apollo_person_data,
        apollo_org_data,
        apollo_match,
        force_full_intake: bool = False,
    ):
        """
        Unified callback from n8n after Apollo API lookup.

        :param apollo_person_data: dict from Apollo People Enrichment API (or {})
        :param apollo_org_data: dict from Apollo Organization Enrichment API (or {})
        :param apollo_match: bool — True if Apollo found a match
        """
        # Run callback logic as superuser to avoid issues with public/None users
        # hitting the endpoint (auth="none" + header-based auth).
        self = self.with_user(SUPERUSER_ID).sudo()
        self.ensure_one()

        if self.x_enrichment_done and not force_full_intake:
            _logger.info(
                "sales_ai: [INTAKE-CB] SKIP — lead_id=%s already enriched, ignoring duplicate callback",
                self.id,
            )
            return

        person_keys = len(apollo_person_data or {})
        org_keys = len(apollo_org_data or {})
        _logger.info(
            "sales_ai: [INTAKE-CB] lead_id=%s Apollo match=%s person_fields=%d org_fields=%d",
            self.id, apollo_match, person_keys, org_keys,
        )

        self.x_apollo_data_raw = json.dumps(
            {"person": apollo_person_data or {}, "organization": apollo_org_data or {}},
            ensure_ascii=False,
        )
        self.x_apollo_match = bool(apollo_match)

        # STEP 1/3 — Enrich from Apollo (re-run when forced to refresh enrichment)
        if apollo_match and (apollo_person_data or apollo_org_data):
            _logger.info("sales_ai: [INTAKE-CB] STEP 1/3 — Enriching from Apollo — lead_id=%s", self.id)
            t0 = time.time()
            try:
                self._enrich_from_apollo(apollo_person_data or {}, apollo_org_data or {})
                _logger.info(
                    "sales_ai: [INTAKE-CB] STEP 1/3 DONE — lead_id=%s enriched (%.2fs)",
                    self.id, time.time() - t0,
                )
            except Exception:
                _logger.error(
                    "sales_ai: [INTAKE-CB] STEP 1/3 FAIL — enrich error lead_id=%s",
                    self.id, exc_info=True,
                )
        else:
            _logger.info(
                "sales_ai: [INTAKE-CB] STEP 1/3 SKIP — no Apollo data for lead_id=%s",
                self.id,
            )

        # STEP 2/3 — Re-classify with Apollo context
        _logger.info(
            "sales_ai: [INTAKE-CB] STEP 2/3 — Re-classifying with Apollo context — lead_id=%s",
            self.id,
        )
        t0 = time.time()
        self._classify_lead_quality(apollo_match)
        _logger.info(
            "sales_ai: [INTAKE-CB] STEP 2/3 DONE — lead_id=%s classification=%s conf=%.0f%% (%.2fs)",
            self.id, self.x_classification or "none",
            self.x_classification_conf or 0.0, time.time() - t0,
        )

        # STEP 3/3 — Score if genuine
        if self.x_classification == "genuine":
            _logger.info("sales_ai: [INTAKE-CB] STEP 3/3 — Scoring — lead_id=%s", self.id)
            t0 = time.time()
            try:
                self.action_run_lead_scoring()
                self.action_send_auto_ack()

                _logger.info(
                    "sales_ai: [INTAKE-CB] STEP 3/3 DONE — lead_id=%s score=%s band=%s (%.2fs)",
                    self.id, self.x_lead_score, self.x_lead_score_band, time.time() - t0,
                )
            except Exception:
                _logger.error(
                    "sales_ai: [INTAKE-CB] STEP 3/3 FAIL — scoring error lead_id=%s",
                    self.id, exc_info=True,
                )
        else:
            _logger.info(
                "sales_ai: [INTAKE-CB] STEP 3/3 SKIP — lead_id=%s is %s, scoring skipped",
                self.id, self.x_classification,
            )

    def _enrich_from_apollo(self, person: dict, org: dict):
        """Map Apollo API response fields to lead custom fields."""
        # n8n may sometimes pass Apollo blobs as JSON strings instead of dicts.
        # Normalise both inputs to dicts before field access.
        if isinstance(person, str):
            try:
                person = json.loads(person) or {}
            except Exception:
                person = {}
        if isinstance(org, str):
            try:
                org = json.loads(org) or {}
            except Exception:
                org = {}

        # Apollo "person" payloads coming from n8n are often wrapped like:
        # {"person": {..., "contact": {...}, "organization": {...}}, "request_id": ...}
        # Normalise into explicit sub-dicts for convenience.
        ap_person = {}
        ap_contact = {}
        ap_person_org = {}
        if isinstance(person, dict) and person:
            if person.get("person"):
                ap_person = person.get("person") or {}
                ap_contact = ap_person.get("contact") or {}
                ap_person_org = ap_person.get("organization") or {}
            else:
                ap_person = person
                ap_contact = person.get("contact") or {}
                ap_person_org = person.get("organization") or {}

        vals = {}

        # ------------------------------------------------------------------
        # Person + contact enrichment (from POST /api/v1/people/match)
        # ------------------------------------------------------------------
        if ap_person:
            # Core identity
            first_name = (ap_person.get("first_name") or "").strip()
            last_name = (ap_person.get("last_name") or "").strip()
            full_name = (ap_person.get("name") or "").strip()

            # Prefer an explicit full name, otherwise build from first/last.
            name = full_name or (" ".join(p for p in [first_name, last_name] if p).strip())
            if name and not self.contact_name:
                vals["contact_name"] = name

            # Email: prefer verified contact email, then primary person email.
            email = None
            if ap_contact:
                email = ap_contact.get("email")
                if not email:
                    emails = ap_contact.get("contact_emails") or []
                    if emails and isinstance(emails[0], dict):
                        email = emails[0].get("email")
            if not email:
                email = ap_person.get("email")

            if email:
                # Direct email enrichment field
                if not self.x_direct_email:
                    vals["x_direct_email"] = email
                # Lead's primary email, if not already set
                if not self.email_from:
                    vals["email_from"] = email

            # Phone: take first number from Apollo contact phones.
            phone = None
            if ap_contact:
                phones = ap_contact.get("phone_numbers") or []
                if phones and isinstance(phones[0], dict):
                    phone = phones[0].get("raw_number") or phones[0].get("sanitized_number")
            if phone:
                if not self.x_direct_phone:
                    vals["x_direct_phone"] = phone
                if not self.phone:
                    vals["phone"] = phone

            # LinkedIn + seniority / decision maker signals
            linkedin = (
                ap_person.get("linkedin_url")
                or ap_contact.get("linkedin_url")
                or self.x_linkedin_url
            )
            if linkedin:
                vals["x_linkedin_url"] = linkedin

            seniority_raw = ap_person.get("seniority")
            vals["x_seniority"] = self._map_apollo_seniority(seniority_raw)
            vals["x_is_decision_maker"] = seniority_raw in (
                "c_suite", "vp", "director", "owner", "founder"
            )

            # Contact/intent scores from Apollo
            p_org = ap_person_org or {}
            if isinstance(p_org, dict) and p_org.get("estimated_num_employees"):
                vals["x_employee_count"] = p_org["estimated_num_employees"]

        # Organization enrichment (from GET /api/v1/organizations/enrich or raw Apollo JSON)
        if isinstance(org, dict) and org:
            if org.get("estimated_num_employees"):
                vals["x_employee_count"] = org["estimated_num_employees"]
            if org.get("annual_revenue") or org.get("organization_revenue"):
                vals["x_annual_revenue"] = org.get("annual_revenue") or org.get(
                    "organization_revenue"
                )

            # Company profile
            if org.get("industry"):
                vals["x_industry"] = org["industry"]
            if org.get("founded_year"):
                vals["x_founded_year"] = org["founded_year"]
            if org.get("city"):
                vals["x_hq_city"] = org["city"]
            if org.get("website_url"):
                vals["x_website"] = org["website_url"]
            if org.get("linkedin_url"):
                vals["x_company_linkedin_url"] = org["linkedin_url"]

            # Employee count / revenue ranges (simple bucketing for ICP display)
            emp = org.get("estimated_num_employees")
            if emp:
                if emp < 50:
                    vals["x_employee_count_range"] = "1-49"
                elif emp < 200:
                    vals["x_employee_count_range"] = "50-199"
                elif emp < 500:
                    vals["x_employee_count_range"] = "200-499"
                elif emp < 1000:
                    vals["x_employee_count_range"] = "500-999"
                else:
                    vals["x_employee_count_range"] = "1000+"

            rev = org.get("annual_revenue") or org.get("organization_revenue")
            if rev:
                try:
                    rev = float(rev)
                except Exception:
                    rev = None
                if rev is not None:
                    if rev < 5_000_000:
                        vals["x_revenue_range"] = "<5M"
                    elif rev < 10_000_000:
                        vals["x_revenue_range"] = "5M-10M"
                    elif rev < 50_000_000:
                        vals["x_revenue_range"] = "10M-50M"
                    elif rev < 100_000_000:
                        vals["x_revenue_range"] = "50M-100M"
                    else:
                        vals["x_revenue_range"] = "100M+"
            # Technology stack from Apollo — prefer structured current_technologies,
            # but fall back to technology_names list if needed.
            tech_names = []
            if org.get("current_technologies"):
                tech_names = [
                    t.get("name", "")
                    for t in (org["current_technologies"] or [])
                    if isinstance(t, dict) and t.get("name")
                ]
            elif org.get("technology_names"):
                tech_names = [name for name in (org.get("technology_names") or []) if name]
            if tech_names:
                vals["x_tech_stack"] = json.dumps(tech_names[:30])
            if org.get("industry"):
                # Check if it's an IT company
                industry = (org["industry"] or "").lower()
                it_keywords = ("software", "technology", "information", "saas", "cloud", "cyber", "data", "ai", "internet")
                vals["x_is_it_company"] = any(kw in industry for kw in it_keywords)

        if vals:
            self.write(vals)
        self.x_enrichment_done = True
        _logger.info("sales_ai: Enrichment written for lead %s — %d fields updated", self.id, len(vals))

        # ------------------------------------------------------------------
        # Create / update contact (res.partner) from Apollo person data
        # ------------------------------------------------------------------
        Partner = self.env["res.partner"].sudo()
        email = (person.get("email") or "").strip() if isinstance(person, dict) else ""

        # Preferred human-readable name:
        # 1) lead.contact_name
        # 2) Apollo name (first/last)
        # 3) email prefix, cleaned up
        name = (self.contact_name or "").strip()
        if not name and isinstance(person, dict):
            name = (
                person.get("name")
                or " ".join(
                    p for p in [person.get("first_name"), person.get("last_name")] if p
                )
                or ""
            )
        if not name and email:
            prefix = email.split("@")[0]
            for ch in [".", "_", "-"]:
                prefix = prefix.replace(ch, " ")
            name = prefix.title()

        phone = ""
        if isinstance(person, dict):
            # Apollo may have phone fields in different shapes; keep it simple
            phone = (person.get("phone") or "").strip()

        partner = False
        # Reuse existing linked partner only when BOTH name and email match
        if self.partner_id and email and self.partner_id.email:
            if self.partner_id.email.lower() == email.lower() and (
                not name
                or self.partner_id.name.strip().lower() == name.strip().lower()
            ):
                partner = self.partner_id

        if not partner and email:
            # Search for an existing partner with same name+email combination
            domain = [("email", "=ilike", email)]
            if name:
                domain.append(("name", "=ilike", name))
            partner = Partner.search(domain, limit=1)
        if partner:
            # Update partner with latest Apollo / ICP details
            update_vals = {}
            if name and (not partner.name or partner.name == partner.email):
                update_vals["name"] = name
            if email and (not partner.email or partner.email.lower() == email.lower()):
                update_vals["email"] = email
            if phone and not partner.phone:
                update_vals["phone"] = phone

            # Contact enrichment
            if isinstance(person, dict):
                if person.get("linkedin_url"):
                    update_vals["x_contact_linkedin_url"] = person.get("linkedin_url")
                if self.x_contact_job_title:
                    update_vals["x_contact_job_title"] = self.x_contact_job_title
                if self.x_contact_seniority_structured:
                    update_vals[
                        "x_contact_seniority_structured"
                    ] = self.x_contact_seniority_structured
                if self.x_contact_decision_authority:
                    update_vals[
                        "x_contact_decision_authority"
                    ] = self.x_contact_decision_authority
                if self.x_inquiry_urgency:
                    update_vals["x_inquiry_urgency"] = self.x_inquiry_urgency

            # Company enrichment
            if isinstance(org, dict):
                if org.get("industry"):
                    update_vals["x_industry"] = org.get("industry")
                if org.get("subindustry"):
                    update_vals["x_sub_industry"] = org.get("subindustry")
                if org.get("estimated_num_employees"):
                    update_vals["x_employee_count"] = org.get("estimated_num_employees")
                if self.x_employee_count_range:
                    update_vals["x_employee_count_range"] = self.x_employee_count_range
                if self.x_revenue_range:
                    update_vals["x_annual_revenue_range"] = self.x_revenue_range
                if self.x_annual_revenue:
                    update_vals["x_annual_revenue"] = self.x_annual_revenue
                if self.x_is_it_company is not None:
                    update_vals["x_is_it_company"] = self.x_is_it_company
                if org.get("linkedin_url"):
                    update_vals["x_company_linkedin_url"] = org.get("linkedin_url")
                if org.get("city"):
                    update_vals["x_hq_city"] = org.get("city")
                if org.get("founded_year"):
                    update_vals["x_founded_year"] = org.get("founded_year")
                if org.get("website_url"):
                    update_vals["x_website"] = org.get("website_url")

                if org.get("country"):
                    country = (
                        self.env["res.country"]
                        .sudo()
                        .search(
                            [
                                "|",
                                ("name", "ilike", org.get("country")),
                                ("code", "ilike", org.get("country")),
                            ],
                            limit=1,
                        )
                    )
                    if country:
                        update_vals["x_hq_country_id"] = country.id

            # ICP / AI signals mirrored on contact
            if self.x_likely_pain_point:
                update_vals["x_likely_pain_point"] = self.x_likely_pain_point
            if self.x_similar_companies_won:
                update_vals["x_similar_companies_won"] = self.x_similar_companies_won
            if self.x_icp_match_signals:
                update_vals["x_icp_match_signals"] = self.x_icp_match_signals
            if self.x_icp_disqualify_signals:
                update_vals[
                    "x_icp_disqualify_signals"
                ] = self.x_icp_disqualify_signals
            if self.x_inquiry_category:
                update_vals["x_inquiry_category"] = self.x_inquiry_category
            if self.x_lead_language:
                update_vals["x_lead_language"] = self.x_lead_language
            if self.x_enrichment_conf:
                update_vals["x_enrichment_conf"] = self.x_enrichment_conf
            if self.x_enrichment_source:
                update_vals["x_enrichment_source"] = self.x_enrichment_source
            if self.x_enrichment_date:
                update_vals["x_enrichment_date"] = self.x_enrichment_date

            # Key Fit Signals -> partner
            if self.x_industry:
                update_vals["x_fit_industry"] = self.x_industry
            if self.x_employee_count_range:
                update_vals["x_fit_company_size"] = self.x_employee_count_range
            if self.x_revenue_range:
                update_vals["x_fit_revenue_range"] = self.x_revenue_range
            if self.x_hq_country_id:
                update_vals["x_fit_geography"] = self.x_hq_country_id.name
            if self.x_contact_seniority_structured:
                update_vals[
                    "x_fit_contact_seniority"
                ] = self.x_contact_seniority_structured
            if self.x_contact_decision_authority:
                update_vals[
                    "x_fit_decision_authority"
                ] = self.x_contact_decision_authority
            if self.x_inquiry_urgency:
                update_vals["x_fit_urgency"] = self.x_inquiry_urgency

            if update_vals:
                partner.write(update_vals)
        elif email or name or phone:
            # No existing partner, create a new one
            create_vals = {
                "name": name or email or phone or "New Contact",
            }
            if email:
                create_vals["email"] = email
            if phone:
                create_vals["phone"] = phone
            if isinstance(org, dict):
                if org.get("city"):
                    create_vals["x_hq_city"] = org.get("city")
                if org.get("country"):
                    country = (
                        self.env["res.country"]
                        .sudo()
                        .search(
                            [
                                "|",
                                ("name", "ilike", org.get("country")),
                                ("code", "ilike", org.get("country")),
                            ],
                            limit=1,
                        )
                    )
                    if country:
                        create_vals["x_hq_country_id"] = country.id
                if org.get("industry"):
                    create_vals["x_industry"] = org.get("industry")
                if org.get("founded_year"):
                    create_vals["x_founded_year"] = org.get("founded_year")
                if org.get("website_url"):
                    create_vals["x_website"] = org.get("website_url")

            partner = Partner.create(create_vals)
            self.partner_id = partner

        # Final sync of all enrichment / ICP fields from lead to partner
        if partner:
            self._sync_partner_from_lead(partner)

    def _sync_partner_from_lead(self, partner):
        """Copy enrichment + key fit signals from lead onto contact."""
        update_vals = {}

        # Contact enrichment
        if self.x_contact_job_title:
            update_vals["x_contact_job_title"] = self.x_contact_job_title
        if self.x_contact_seniority_structured:
            update_vals[
                "x_contact_seniority_structured"
            ] = self.x_contact_seniority_structured
        if self.x_contact_decision_authority:
            update_vals[
                "x_contact_decision_authority"
            ] = self.x_contact_decision_authority
        if self.x_direct_email:
            update_vals["x_direct_email"] = self.x_direct_email
        if self.x_direct_phone:
            update_vals["x_direct_phone"] = self.x_direct_phone
        if self.x_contact_linkedin_url:
            update_vals["x_contact_linkedin_url"] = self.x_contact_linkedin_url

        # Company enrichment
        if self.x_industry:
            update_vals["x_industry"] = self.x_industry
        if hasattr(self, "x_sub_industry") and self.x_sub_industry:
            update_vals["x_sub_industry"] = self.x_sub_industry
        if self.x_employee_count_range:
            update_vals["x_employee_count_range"] = self.x_employee_count_range
        if self.x_employee_count:
            update_vals["x_employee_count"] = self.x_employee_count
        if self.x_revenue_range:
            update_vals["x_annual_revenue_range"] = self.x_revenue_range
        if self.x_annual_revenue:
            update_vals["x_annual_revenue"] = self.x_annual_revenue
        if hasattr(self, "x_is_it_company") and self.x_is_it_company is not None:
            update_vals["x_is_it_company"] = self.x_is_it_company
        if self.x_company_linkedin_url:
            update_vals["x_company_linkedin_url"] = self.x_company_linkedin_url
        if self.x_hq_city:
            update_vals["x_hq_city"] = self.x_hq_city
        if self.x_hq_country_id:
            update_vals["x_hq_country_id"] = self.x_hq_country_id.id
        if self.x_founded_year:
            update_vals["x_founded_year"] = self.x_founded_year
        if self.x_website:
            update_vals["x_website"] = self.x_website

        # AI / ICP signals
        if self.x_likely_pain_point:
            update_vals["x_likely_pain_point"] = self.x_likely_pain_point
        if self.x_similar_companies_won:
            update_vals["x_similar_companies_won"] = self.x_similar_companies_won
        if self.x_icp_match_signals:
            update_vals["x_icp_match_signals"] = self.x_icp_match_signals
        if self.x_icp_disqualify_signals:
            update_vals["x_icp_disqualify_signals"] = self.x_icp_disqualify_signals
        if self.x_inquiry_category:
            update_vals["x_inquiry_category"] = self.x_inquiry_category
        if self.x_inquiry_urgency:
            update_vals["x_inquiry_urgency"] = self.x_inquiry_urgency
        if self.x_lead_language:
            update_vals["x_lead_language"] = self.x_lead_language
        if self.x_enrichment_conf:
            update_vals["x_enrichment_conf"] = self.x_enrichment_conf
        if self.x_enrichment_source:
            update_vals["x_enrichment_source"] = self.x_enrichment_source
        if self.x_enrichment_date:
            update_vals["x_enrichment_date"] = self.x_enrichment_date

        # Key Fit Signals
        if self.x_industry:
            update_vals["x_fit_industry"] = self.x_industry
        if self.x_employee_count_range:
            update_vals["x_fit_company_size"] = self.x_employee_count_range
        if self.x_revenue_range:
            update_vals["x_fit_revenue_range"] = self.x_revenue_range
        if self.x_hq_country_id:
            update_vals["x_fit_geography"] = self.x_hq_country_id.name
        if self.x_contact_seniority_structured:
            update_vals[
                "x_fit_contact_seniority"
            ] = self.x_contact_seniority_structured
        if self.x_contact_decision_authority:
            update_vals[
                "x_fit_decision_authority"
            ] = self.x_contact_decision_authority
        if self.x_inquiry_urgency:
            update_vals["x_fit_urgency"] = self.x_inquiry_urgency

        if update_vals:
            partner.write(update_vals)

    def _ensure_partner_from_enrichment(self):
        """Ensure a contact exists for this lead, then sync enrichment onto it.

        This is called after the full Apollo + structured enrichment + ICP
        scoring pipeline so that the contact always reflects the final state.
        """
        self.ensure_one()
        Partner = self.env["res.partner"].sudo()

        # Best email/name/phone we have: prefer enriched direct fields, then lead.
        email = (self.x_direct_email or self.email_from or "").strip()

        # Contact name priority:
        # 1) Apollo person: first_name + last_name / full name → stored in contact_name
        # 2) Apollo organization: organization/company name → stored as partner_name / partner_id.name
        # 3) Fallback: local-part of email (before '@')
        name = (self.contact_name or "").strip()
        if not name:
            company_name = (self.partner_name or (self.partner_id.name if self.partner_id else "") or "").strip()
            name = company_name
        if not name and email:
            prefix = email.split("@")[0]
            for ch in [".", "_", "-"]:
                prefix = prefix.replace(ch, " ")
            name = prefix.title()
        phone = (self.x_direct_phone or self.phone or "").strip()

        partner = self.partner_id

        # Reuse linked partner only when both name and email match.
        if partner and email and partner.email:
            if not (
                partner.email.lower() == email.lower()
                and (
                    not name
                    or partner.name.strip().lower() == name.strip().lower()
                )
            ):
                partner = False

        # Otherwise, search for an existing partner with same email (+name if available)
        if not partner and email:
            domain = [("email", "=ilike", email)]
            if name:
                domain.append(("name", "=ilike", name))
            partner = Partner.search(domain, limit=1)

        # Still nothing: create a new contact ONLY when we have a concrete email.
        # If there is no email, skip contact creation but still apply enrichment on the lead.
        if not partner and email:
            vals = {"name": name or email or phone or "New Contact"}
            if email:
                vals["email"] = email
            if phone:
                vals["phone"] = phone
            partner = Partner.create(vals)
            self.partner_id = partner

        # Finally sync all enrichment + key fit signals onto the contact.
        if partner:
            self._sync_partner_from_lead(partner)

        # Run AI-based structured enrichment on the raw Apollo JSON to populate
        # the remaining 30+ enrichment fields (ICP signals, pain points, etc.).
        # This is a best-effort call; if Claude or config is missing, we simply skip.
        try:
            raw_blob = {
                "person": person or {},
                "organization": org or {},
            }
            struct = self._claude().call(
                tier="haiku",
                system_prompt=prompts.PROMPTS["enrichment_system"],
                user_message=json.dumps(raw_blob, ensure_ascii=False),
                max_tokens=800,
                expect_json=True,
            )
        except Exception:
            _logger.warning(
                "sales_ai: EnrichmentStructurerAgent failed for lead %s; raw Apollo only.",
                self.id,
                exc_info=True,
            )
        else:
            if isinstance(struct, dict):
                _logger.info(
                    "sales_ai: Applying structured enrichment for lead %s (keys=%s)",
                    self.id,
                    list(struct.keys()),
                )
                self.action_apply_structured_enrichment(struct)
                if self.partner_id:
                    self._sync_partner_from_lead(self.partner_id)

    def _map_apollo_seniority(self, apollo_seniority):
        """Map Apollo seniority values to our selection field."""
        mapping = {
            "c_suite": "c_level",
            "owner": "c_level",
            "founder": "c_level",
            "vp": "vp",
            "director": "director",
            "manager": "manager",
            "senior": "other",
            "entry": "other",
            "training": "other",
        }
        return mapping.get(apollo_seniority or "", None)

    # -------------------------------------------------------------------------
    # Structured enrichment write-back (EnrichmentStructurerAgent)
    # -------------------------------------------------------------------------

    def action_apply_structured_enrichment(self, enrichment: dict):
        """
        Apply structured enrichment JSON (from EnrichmentStructurerAgent)
        onto this lead's fields.

        Expected keys (subset aligned with agents/phase1/enrichment_structurer.py):
          company_industry, company_sub_industry, company_employee_count,
          company_revenue_range, company_hq_country, company_hq_city,
          company_founded_year, company_tech_stack (list),
          company_funding_stage, company_linkedin_url, company_website,
          contact_job_title, contact_seniority, contact_email_verified,
          contact_phone, contact_linkedin_url, contact_is_decision_maker,
          likely_pain_point, similar_clients_won, icp_match_signals,
          icp_disqualify_signals, apollo_conversation_history,
          enrichment_confidence, enrichment_notes, data_source,
          enrichment_date, lead_language, inquiry_category, inquiry_urgency,
          follow_up_angle.
        """
        self.ensure_one()
        vals = {}

        # Company
        vals["x_industry"] = enrichment.get("company_industry") or False
        vals["x_subindustry"] = enrichment.get("company_sub_industry") or False
        vals["x_employee_count_range"] = enrichment.get("company_employee_count") or False
        vals["x_revenue_range"] = enrichment.get("company_revenue_range") or False
        vals["x_hq_city"] = enrichment.get("company_hq_city") or False
        vals["x_founded_year"] = enrichment.get("company_founded_year") or False
        vals["x_company_funding_stage"] = enrichment.get("company_funding_stage") or False
        vals["x_company_linkedin_url"] = enrichment.get("company_linkedin_url") or False
        vals["x_website"] = enrichment.get("company_website") or False

        country_name = enrichment.get("company_hq_country")
        if country_name:
            country = (
                self.env["res.country"]
                .sudo()
                .search([("name", "ilike", country_name)], limit=1)
            )
            vals["x_hq_country_id"] = country.id if country else False

        tech_stack = enrichment.get("company_tech_stack")
        if tech_stack:
            # Store as JSON string in existing x_tech_stack field
            try:
                vals["x_tech_stack"] = json.dumps(tech_stack, ensure_ascii=False)
            except Exception:
                vals["x_tech_stack"] = str(tech_stack)

        # Contact
        vals["x_contact_job_title"] = enrichment.get("contact_job_title") or False
        seniority = (enrichment.get("contact_seniority") or "").lower()
        seniority_map = {
            "c-level": "c_level",
            "c_level": "c_level",
            "vp": "vp",
            "director": "director",
            "manager": "manager",
            "ic": "ic",
            "individual_contributor": "ic",
            "unknown": "unknown",
        }
        vals["x_contact_seniority_structured"] = seniority_map.get(seniority) or False
        vals["x_direct_email"] = enrichment.get("contact_email_verified") or False
        vals["x_direct_phone"] = enrichment.get("contact_phone") or False
        vals["x_contact_linkedin_url"] = enrichment.get("contact_linkedin_url") or False

        is_dm = enrichment.get("contact_is_decision_maker")
        if is_dm is True:
            vals["x_contact_decision_authority"] = "yes"
            vals["x_is_decision_maker"] = True
        elif is_dm is False:
            vals["x_contact_decision_authority"] = "no"
            vals["x_is_decision_maker"] = False
        else:
            vals["x_contact_decision_authority"] = "unknown"

        # Lead context
        vals["x_likely_pain_point"] = enrichment.get("likely_pain_point") or False
        vals["x_similar_companies_won"] = enrichment.get("similar_clients_won") or False

        icp_signals = enrichment.get("icp_match_signals")
        if icp_signals is not None:
            try:
                vals["x_icp_match_signals"] = json.dumps(icp_signals, ensure_ascii=False)
            except Exception:
                vals["x_icp_match_signals"] = str(icp_signals)

        icp_disq = enrichment.get("icp_disqualify_signals")
        if icp_disq is not None:
            try:
                vals["x_icp_disqualify_signals"] = json.dumps(icp_disq, ensure_ascii=False)
            except Exception:
                vals["x_icp_disqualify_signals"] = str(icp_disq)

        vals["x_apollo_conversation_summary"] = enrichment.get("apollo_conversation_history") or False

        conf = enrichment.get("enrichment_confidence")
        if conf is not None:
            try:
                vals["x_enrichment_conf"] = float(conf)
            except Exception:
                pass
        vals["x_enrichment_notes"] = enrichment.get("enrichment_notes") or False
        vals["x_enrichment_source"] = enrichment.get("data_source") or False

        date_str = enrichment.get("enrichment_date")
        if date_str:
            try:
                # Accept YYYY-MM-DD or ISO datetime
                if "T" in date_str:
                    vals["x_enrichment_date"] = fields.Datetime.to_datetime(date_str)
                else:
                    vals["x_enrichment_date"] = fields.Datetime.to_datetime(
                        date_str + " 00:00:00"
                    )
            except Exception:
                vals["x_enrichment_date"] = fields.Datetime.now()

        vals["x_lead_language"] = enrichment.get("lead_language") or False

        cat = (enrichment.get("inquiry_category") or "").lower()
        cat_map = {
            "new-implementation": "new_implementation",
            "new_implementation": "new_implementation",
            "upgrade": "upgrade",
            "support": "support",
            "consulting": "consulting",
            "other": "other",
        }
        vals["x_inquiry_category"] = cat_map.get(cat) or False

        urg = (enrichment.get("inquiry_urgency") or "").lower()
        urg_map = {"high": "high", "medium": "medium", "low": "low"}
        vals["x_inquiry_urgency"] = urg_map.get(urg) or False

        vals["x_follow_up_angle"] = enrichment.get("follow_up_angle") or False

        # Write all values and mark enrichment as done
        vals["x_enrichment_done"] = True
        self.write(vals)

        # After final structured enrichment, always ensure there is a contact
        # and that it carries all enrichment + key fit signals.
        self._ensure_partner_from_enrichment()

        # Log to chatter
        self.message_post(
            body=_("Enriched from Apollo on %s", fields.Datetime.now()),
            subtype_xmlid="mail.mt_note",
        )

    def _classify_lead_quality(self, has_apollo_data: bool):
        """
        Classify lead as genuine / marketing / junk.

        If Apollo had data → use enriched fields + email content for classification.
        If no Apollo data → classify from email content only (more conservative).
        """
        _logger.info(
            "sales_ai: [JUNK-FILTER] lead_id=%s has_apollo=%s email=%s",
            self.id, has_apollo_data, self.email_from or "(none)",
        )
        settings = self.env["ir.config_parameter"].sudo()
        marketing_user_id = int(
            settings.get_param("sales_ai.marketing_user_id", default="0") or 0
        )
        if not marketing_user_id:
            _logger.warning(
                "sales_ai: [JUNK-FILTER] WARNING lead_id=%s — "
                "sales_ai.marketing_user_id not set. Non-genuine leads won't be routed. "
                "Fix: Settings → Sales AI → Marketing User.",
                self.id,
            )

        subject = (self.name or "")[:512]
        body = (self.description or "")[:4000]
        sender_email = self.email_from or ""
        sender_domain = (
            sender_email.split("@")[-1] if sender_email and "@" in sender_email else ""
        )

        payload = {
            "email_subject": subject,
            "email_body": body,
            "sender_email": sender_email,
            "sender_domain": sender_domain,
            "company_name": (self.partner_id.name or "") if self.partner_id else "",
            "lead_id": self.id,
        }

        # Include simple enrichment hints if available
        if has_apollo_data:
            payload.update(
                {
                    "employee_count": self.x_employee_count,
                    "is_it_company": self.x_is_it_company,
                    "seniority": self.x_seniority,
                    "is_decision_maker": self.x_is_decision_maker,
                    "linkedin_url": self.x_linkedin_url,
                    "tech_stack": self.x_tech_stack,
                }
            )

        t0 = time.time()
        try:
            result = self._claude().call(
                tier="haiku",
                system_prompt=prompts.PROMPTS["junk_filter_system"],
                user_message=json.dumps(payload, ensure_ascii=False),
                max_tokens=256,
                expect_json=True,
            )
        except Exception:
            _logger.error(
                "sales_ai: [JUNK-FILTER] FAIL — Claude API error lead_id=%s (%.2fs); "
                "defaulting to genuine. Check API key and network.",
                self.id, time.time() - t0, exc_info=True,
            )
            quality = "genuine"
            self.x_lead_quality = quality
            self.x_classification = quality
            return

        if not isinstance(result, dict):
            result = {}

        # Detect silent failure: Claude returned empty dict (API key missing / SDK error)
        if not result:
            _logger.error(
                "sales_ai: [JUNK-FILTER] NO RESULT — lead_id=%s (%.2fs). "
                "Claude returned empty response. Most likely cause: "
                "sales_ai.claude_api_key not set in Settings → Technical → System Parameters. "
                "Defaulting to genuine.",
                self.id, time.time() - t0,
            )
            quality = "genuine"
            self.x_lead_quality = quality
            self.x_classification = quality
            return

        _logger.info(
            "sales_ai: [JUNK-FILTER] Claude Haiku OK — lead_id=%s (%.2fs) raw=%s",
            self.id, time.time() - t0, str(result)[:150],
        )
        classification = (result.get("classification") or "genuine").lower()
        confidence = float(result.get("confidence") or 0.0)
        reason = result.get("reason") or ""
        suggested_tag = (result.get("suggested_tag") or "").strip()

        # Server-side safety net: for trusted internal domains with clearly
        # business-y subjects, force classification to genuine even if the
        # model is overly conservative (e.g. empty body during testing).
        internal_domains = {"biztechcs.com"}
        subject_lc = subject.lower()
        looks_like_requirement = any(
            kw in subject_lc
            for kw in [
                "requirement",
                "inquiry",
                "implementation",
                "web-to-print",
                "web to print",
                "business requirement",
                "software requirement",
                "discussion",
            ]
        )
        if (
            sender_domain in internal_domains
            and looks_like_requirement
            and classification in ("junk", "marketing")
        ):
            _logger.info(
                "sales_ai: [JUNK-FILTER] OVERRIDE to genuine for lead_id=%s "
                "(internal domain %s + requirement-style subject). "
                "Original: classification=%s conf=%.0f%% reason=%s",
                self.id,
                sender_domain,
                classification,
                confidence,
                reason,
            )
            classification = "genuine"
            confidence = max(confidence, 60.0)

        # Normalise to our selection values
        if classification not in ("genuine", "marketing", "junk", "job_seeker"):
            classification = "genuine"

        # Backwards-compatible lead quality (no job_seeker value there)
        quality_map = {
            "genuine": "genuine",
            "marketing": "marketing",
            "junk": "junk",
            "job_seeker": "marketing",  # job seekers are handled by Marketing
        }
        quality = quality_map[classification]

        self.write(
            {
                "x_lead_quality": quality,
                "x_classification": classification,
                "x_classification_conf": max(0.0, min(100.0, confidence)),
                "x_classification_reason": reason[:255] if reason else False,
            }
        )

        # Apply suggested Odoo tag if provided
        if suggested_tag:
            Tag = self.env["crm.tag"].sudo()
            tag = Tag.search([("name", "=", suggested_tag)], limit=1)
            if not tag:
                tag = Tag.create({"name": suggested_tag})
            self.tag_ids = [(4, tag.id)]

        _logger.info(
            "sales_ai: Lead %s classified as %s (conf=%.1f, Apollo match: %s)",
            self.id,
            classification,
            confidence,
            has_apollo_data,
        )

        # Route non-genuine leads to Marketing user and stop automation
        if classification in ("marketing", "junk", "job_seeker") and marketing_user_id:
            self.user_id = self.env["res.users"].browse(marketing_user_id)
            self.message_post(
                body=_(
                    "Classified as <b>%s</b> by AI (%.1f%% confidence, Apollo match: %s). "
                    "Routed to Marketing user and automation stopped.",
                    classification,
                    max(0.0, min(100.0, confidence)),
                    "Yes" if has_apollo_data else "No",
                ),
                subtype_xmlid="mail.mt_note",
            )

    # Legacy method — kept for backward compat with old automation XML
    def action_run_junk_filter(self):
        """Fallback: classify without Apollo data (for manually created leads)."""
        for lead in self.filtered(lambda l: not l.x_lead_quality):
            lead._classify_lead_quality(has_apollo_data=False)

    # =========================================================================
    # PHASE 2: LEAD SCORING
    # =========================================================================

    def action_run_lead_scoring(self):
        """Score the lead 0-100 and set band based on configured ICP JSON."""
        _logger.info("sales_ai: [SCORING] Starting for lead_id(s)=%s", self.ids)
        ICP = self.env["ir.config_parameter"].sudo()
        icp_json = ICP.get_param("sales_ai.icp_criteria_json", default="{}")
        try:
            icp = json.loads(icp_json)
        except Exception:
            icp = {}
            _logger.warning(
                "sales_ai: [SCORING] WARNING — ICP JSON invalid. "
                "Default score 50/warm applied. Fix: Settings → Sales AI → ICP Criteria."
            )

        for lead in self.filtered(lambda l: not l.x_scoring_done):
            if not icp:
                lead.x_lead_score = 50
                lead.x_lead_score_band = "warm"
                lead.x_scoring_done = True
                lead.x_lead_score_breakdown = False
                lead.x_lead_score_rationale = _(
                    "Default score applied because no ICP criteria are configured."
                )
                _logger.info(
                    "sales_ai: Lead %s scored 50 (warm) — no ICP criteria configured",
                    lead.id,
                )
                continue

            payload = {
                "lead_id": lead.id,
                "enriched_fields": {
                    "company_industry": lead.x_industry or "",
                    "company_subindustry": lead.x_subindustry or "",
                    "company_employee_count": lead.x_employee_count or 0,
                    "company_employee_range": lead.x_employee_count_range or "",
                    "company_revenue_range": lead.x_revenue_range or "",
                    "company_hq_country": lead.x_hq_country_id.name if lead.x_hq_country_id else "",
                    "company_hq_city": lead.x_hq_city or "",
                    "tech_stack": lead.x_tech_stack or "",
                    "funding_stage": lead.x_company_funding_stage or "",
                    "contact_job_title": lead.x_contact_job_title or "",
                    "contact_seniority": lead.x_contact_seniority_structured or lead.x_seniority or "",
                    "contact_is_decision_maker": lead.x_contact_decision_authority == "yes",
                    "likely_pain_point": lead.x_likely_pain_point or "",
                    "icp_match_signals": lead.x_icp_match_signals or "",
                    "icp_disqualify_signals": lead.x_icp_disqualify_signals or "",
                    "apollo_match": lead.x_apollo_match,
                },
                "original_inquiry": (lead.description or "")[:2000],
                "icp_config": icp,
            }
            try:
                result = self._claude().call(
                    tier="haiku",
                    system_prompt=prompts.PROMPTS["lead_scoring_system"],
                    user_message=json.dumps(payload, ensure_ascii=False),
                    max_tokens=800,
                    expect_json=True,
                )
            except Exception:
                _logger.error(
                    "sales_ai: Lead scoring failed for lead %s",
                    lead.id,
                    exc_info=True,
                )
                continue

            if not isinstance(result, dict):
                result = {}

            score = int(result.get("score") or 0)
            band = (result.get("band") or "").lower()
            if band not in ("hot", "warm", "neutral", "cold"):
                # Map legacy three-band outputs into four-band scheme
                if score >= 90:
                    band = "hot"
                elif score >= 70:
                    band = "warm"
                elif score >= 50:
                    band = "neutral"
                else:
                    band = "cold"

            breakdown = result.get("breakdown") or {}
            rationale = result.get("rationale") or result.get("reasoning") or ""

            lead.write(
                {
                    "x_lead_score": max(0, min(100, score)),
                    "x_lead_score_band": band,
                    "x_scoring_done": True,
                    "x_lead_score_breakdown": json.dumps(breakdown, ensure_ascii=False)
                    if breakdown
                    else False,
                    "x_lead_score_rationale": rationale or False,
                }
            )

            _logger.info(
                "sales_ai: Lead %s scored %d (%s) — %s",
                lead.id,
                score,
                band,
                (rationale or "")[:100],
            )
            if rationale:
                lead.message_post(
                    body=_(
                        "AI lead scoring: <b>%d/100 (%s)</b><br/>%s",
                        score,
                        band,
                        rationale,
                    ),
                    subtype_xmlid="mail.mt_note",
                )

            # After scoring (ICP score done), push latest enrichment and key fit
            # signals down to the linked contact so the partner record always
            # reflects the final state of the lead.
            if lead.partner_id:
                lead._sync_partner_from_lead(lead.partner_id)

            # Follow-up activities will now be scheduled only AFTER the auto-ack
            # email has been sent (stage moved to "Contacted"), so we do not
            # create them immediately at scoring time.

    # =========================================================================
    # PHASE 3: AUTO-ACK EMAIL + FOLLOW-UP SCHEDULING
    # =========================================================================

    def action_send_auto_ack(self):
        """
        Prepare an AI-generated acknowledgment email draft for the assigned rep.

        Mindmap alignment:
        - [4] LEAD ASSIGNMENT: rep gets an activity to review & send auto-ack.
        - [5] AUTO-ACK: AI drafts a personalized email; rep reviews & sends.

        This method now creates a review activity with the AI draft instead of
        immediately sending the email, so the rep stays in control.
        """
        for lead in self:
            # Require assigned rep, enrichment and scoring to be completed, and
            # lead classified as genuine before drafting auto-ack.
            if not lead.user_id:
                _logger.warning(
                    "sales_ai: [AUTO-ACK] SKIP lead_id=%s — missing user_id (no assigned rep).",
                    lead.id,
                )
                continue
            if not lead.x_enrichment_done or not lead.x_scoring_done:
                _logger.info(
                    "sales_ai: [AUTO-ACK] SKIP lead_id=%s — enrichment/scoring not done yet.",
                    lead.id,
                )
                continue
            if lead.x_classification not in ("genuine",):
                _logger.info(
                    "sales_ai: [AUTO-ACK] SKIP lead_id=%s — classification=%s (only genuine leads get auto-ack).",
                    lead.id,
                    lead.x_classification,
                )
                continue

            # Prefer partner email if present; fall back to lead.email_from. If still missing,
            # we cannot draft a meaningful auto-ack.
            client_email = (
                (lead.partner_id and lead.partner_id.email)
                or lead.email_from
                or ""
            )
            if not client_email:
                _logger.warning(
                    "sales_ai: [AUTO-ACK] SKIP lead_id=%s — no client email found on partner or lead.",
                    lead.id,
                )
                continue

            calendar_link = lead.user_id.x_calendar_link or "[CALENDAR_LINK]"
            if calendar_link == "[CALENDAR_LINK]":
                _logger.warning(
                    "sales_ai: [AUTO-ACK] WARNING lead_id=%s — rep %s has no x_calendar_link set. "
                    "Email will be sent without a booking link. "
                    "Fix: Users → rep profile → Calendar Booking Link field.",
                    lead.id, lead.user_id.name,
                )
            context_data = {
                "lead_id": lead.id,
                "client_name": lead.contact_name
                or (lead.partner_id and lead.partner_id.name)
                or (lead.name or "there"),
                "client_company": (lead.partner_id and lead.partner_id.name) or "",
                "client_role": getattr(lead, "function", "") or "",
                "original_inquiry": lead.description or "",
                "enriched_fields": {
                    "company_industry": (
                        lead.x_industry
                        or (
                            getattr(lead.partner_id, "industry_id", False)
                            and lead.partner_id.industry_id.name
                        )
                        or ""
                    ),
                    "likely_pain_point": getattr(lead, "x_pain_point", False) or "",
                },
                "client_email": client_email,
                "rep_name": lead.user_id.name or "",
                "rep_designation": lead.user_id.job_title or "Account Executive",
                "rep_calendar_link": calendar_link,
                "company_value_prop": "",
                "lead_score_band": lead.x_lead_score_band or "warm",
            }
            try:
                resp = self._claude().call(
                    tier="sonnet",
                    system_prompt=prompts.PROMPTS["auto_ack_system"],
                    user_message=json.dumps(context_data, ensure_ascii=False),
                    expect_json=True,
                )
            except Exception:
                _logger.error(
                    "sales_ai: Auto-ack generation failed for lead %s",
                    lead.id,
                    exc_info=True,
                )
                continue

            subject = resp.get("subject") or _("Thank you for your inquiry")
            body_raw = resp.get("body_html") or resp.get("body") or ""
            body_html = tools.plaintext2html(body_raw)

            # Send the auto-ack email directly to the client using Odoo's mail
            # thread (requires a partner recipient, not raw email_to).
            email_from = (
                lead.user_id.partner_id.email
                or self.env.user.partner_id.email
                or ""
            )

            # Ensure we have a partner to send to; create or reuse based on email
            partner_ids = []
            partner = lead.partner_id
            if not partner:
                Partner = self.env["res.partner"].sudo()
                partner = Partner.search([("email", "=", client_email)], limit=1)
                if not partner:
                    partner = Partner.create(
                        {
                            "name": context_data["client_name"],
                            "email": client_email,
                        }
                    )
                lead.partner_id = partner
            partner_ids = [partner.id]

            try:
                lead.message_post(
                    body=body_html,
                    subject=subject,
                    message_type="email",
                    email_from=email_from,
                    partner_ids=partner_ids,
                )
                _logger.info(
                    "sales_ai: Auto-ack email SENT for lead %s to %s",
                    lead.id,
                    client_email,
                )
            except Exception:
                _logger.error(
                    "sales_ai: Failed to send auto-ack email for lead %s",
                    lead.id,
                    exc_info=True,
                )

    def action_create_followup_activities(self, base_date=None):
        """Create the 3 scheduled follow-ups based on x_lead_score_band."""
        Activity = self.env["mail.activity"].sudo()
        followup_type = self.env.ref(
            "sales_ai_integration.activity_type_followup_email", raise_if_not_found=False
        )

        for lead in self:
            if lead.x_unsubscribed:
                _logger.info(
                    "sales_ai: Skipping follow-up creation for lead %s — unsubscribed",
                    lead.id,
                )
                continue

            if not lead.user_id or not lead.x_lead_score_band:
                _logger.warning(
                    "sales_ai: Skipping follow-up creation for lead %s — user: %s, band: %s",
                    lead.id, lead.user_id.id if lead.user_id else None, lead.x_lead_score_band,
                )
                continue

            if base_date is None:
                # context_timestamp expects a naive datetime in UTC; avoid double-localizing
                naive_utc_now = datetime.utcnow()
                base_dt = fields.Datetime.context_timestamp(self, naive_utc_now)
            else:
                base_dt = base_date

            if lead.x_lead_score_band == "hot":
                gaps = [1, 3, 7]
            elif lead.x_lead_score_band == "cold":
                gaps = [3, 7, 14]
            else:
                gaps = [2, 5, 10]

            for idx, days in enumerate(gaps, start=1):
                deadline = self._business_day_offset(base_dt, days).date()
                Activity.create(
                    {
                        'res_model_id': self.env.ref('crm.model_crm_lead').id,
                        "res_id": lead.id,
                        "user_id": lead.user_id.id,
                        "activity_type_id": followup_type.id if followup_type else False,
                        "date_deadline": deadline,
                        # Draft content will be generated by the 9 AM cron only.
                        "note": "[AI-FOLLOWUP-PENDING] Draft generation scheduled by cron.",
                    }
                )
            lead.x_followup_stage = 1
            _logger.info(
                "sales_ai: Created 3 follow-up activities for lead %s (band=%s, gaps=%s)",
                lead.id, lead.x_lead_score_band, gaps,
            )

    def _cancel_pending_followups(self):
        """Cancel all pending follow-up activities for these leads."""
        Activity = self.env["mail.activity"].sudo()
        followup_type = self.env.ref(
            "sales_ai_integration.activity_type_followup_email",
            raise_if_not_found=False,
        )
        if not followup_type:
            return
        for lead in self:
            pending = Activity.search([
                ("res_model", "=", "crm.lead"),
                ("res_id", "=", lead.id),
                ("activity_type_id", "=", followup_type.id),
            ])
            if pending:
                _logger.info(
                    "sales_ai: Canceling %d pending follow-ups for lead %s",
                    len(pending), lead.id,
                )
                pending.unlink()

    # =========================================================================
    # PHASE 4: FOLLOW-UP EMAIL DRAFTER
    # =========================================================================

    @api.model
    def cron_draft_followup_emails(self):
        """Backward-compatible alias for older server actions.

        Some databases may still have a scheduled action calling
        model.cron_draft_followup_emails(). Keep it as a thin wrapper
        around cron_generate_followup_drafts().
        """
        return self.cron_generate_followup_drafts()

    @api.model
    def cron_generate_followup_drafts(self):
        """Daily 09:00 cron — generate / refresh follow-up drafts due today or earlier.

        This implements the spec:
          - activities are scheduled at auto-ack time
          - drafts are created on (or just before) their due dates.
        """
        Activity = self.env["mail.activity"].sudo()
        followup_type = self.env.ref(
            "sales_ai_integration.activity_type_followup_email",
            raise_if_not_found=False,
        )
        if not followup_type:
            return

        today = fields.Date.today()
        pending_activities = Activity.search(
            [
                ("res_model", "=", "crm.lead"),
                ("activity_type_id", "=", followup_type.id),
                ("date_deadline", "<=", today),
                # Either no note or one of our pending markers
                ("note", "ilike", "[AI-FOLLOWUP-PENDING]%"),
            ]
        )
        if not pending_activities:
            return

        _logger.info(
            "sales_ai: [FOLLOWUP-CRON] Generating drafts for %d pending follow-up activities",
            len(pending_activities),
        )
        leads_by_id = {
            lead.id: lead
            for lead in self.browse(pending_activities.mapped("res_id")).sudo()
        }
        for act in pending_activities:
            lead = leads_by_id.get(act.res_id)
            if not lead:
                continue
            try:
                self._draft_single_followup_email(lead, act)
            except Exception:
                _logger.error(
                    "sales_ai: Failed to draft follow-up via cron for lead %s (activity %s)",
                    act.res_id,
                    act.id,
                    exc_info=True,
                )
                act.note = "[AI-FOLLOWUP-PENDING] Draft generation failed."

    def _draft_single_followup_email(self, lead, activity):
        """Generate one follow-up draft email into the activity note."""
        done_count = self.env["mail.activity"].search_count(
            [
                ("res_model", "=", "crm.lead"),
                ("res_id", "=", lead.id),
                ("activity_type_id", "=", activity.activity_type_id.id),
                ("date_deadline", "<", activity.date_deadline),
            ]
        )
        followup_no = done_count + 1

        messages = lead.message_ids.sorted("date", reverse=False)
        outbound: List[Dict[str, str]] = []
        inbound: List[Dict[str, str]] = []
        for msg in messages[-20:]:
            entry = {
                "subject": msg.subject or "",
                "snippet": (msg.body or "")[:400],
                "date": str(msg.date),
            }
            if msg.message_type == "email" and msg.author_id.user_ids:
                outbound.append(entry)
            elif msg.message_type == "email":
                inbound.append(entry)

        context_data = {
            "followup_number": followup_no,
            "lead_score": lead.x_lead_score,
            "lead_score_band": lead.x_lead_score_band,
            "company_name": lead.partner_id.name if lead.partner_id else "",
            "contact_name": lead.contact_name or "",
            "previous_outbound": outbound[-5:],
            "recent_replies": inbound[-3:],
            "calendar_link": lead.user_id.x_calendar_link or "",
        }

        # Include attachment context if available
        att_context = lead._get_attachment_context()
        if att_context:
            context_data["attachment_context"] = att_context[:2000]

        try:
            resp = self._claude().call(
                tier="sonnet",
                system_prompt=prompts.PROMPTS["followup_email_system"],
                user_message=json.dumps(context_data, ensure_ascii=False),
                max_tokens=800,
                expect_json=True,
            )
        except Exception:
            _logger.error(
                "sales_ai: Follow-up draft generation failed for lead %s (JSON call)",
                lead.id,
                exc_info=True,
            )
            activity.note = (
                "<p><b>[AI DRAFT — Follow-up %s]</b></p>"
                "<p><i>Draft generation failed. Please compose manually or wait for daily retry.</i></p>"
            ) % followup_no
            return

        subject = ""
        body_text = ""
        angle = ""
        cta = ""

        if isinstance(resp, dict):
            subject = resp.get("subject") or ""
            body_text = resp.get("body") or resp.get("body_html") or ""
            angle = resp.get("angle") or ""
            cta = resp.get("cta") or ""

        # If JSON response had no usable body, fall back to a plain-text call
        if not body_text:
            _logger.warning(
                "sales_ai: Follow-up #%d JSON draft empty for lead %s — falling back to plain text",
                followup_no,
                lead.id,
            )
            try:
                raw = self._claude().call(
                    tier="sonnet",
                    system_prompt=(
                        "You are writing a single follow-up email in plain text only. "
                        "Do not output JSON, analysis, or commentary — only the email body. "
                        "Use the provided JSON as context to write the best possible email."
                    ),
                    user_message=json.dumps(context_data, ensure_ascii=False),
                    max_tokens=800,
                    expect_json=False,
                )
            except Exception:
                _logger.error(
                    "sales_ai: Follow-up draft generation failed for lead %s (plain-text fallback)",
                    lead.id,
                    exc_info=True,
                )
                activity.note = (
                    "<p><b>[AI DRAFT — Follow-up %s]</b></p>"
                    "<p><i>Draft generation failed. Please compose manually or wait for daily retry.</i></p>"
                ) % followup_no
                return

            if raw:
                body_text = raw
            else:
                _logger.warning(
                    "sales_ai: Follow-up #%d plain-text draft empty for lead %s — leaving pending",
                    followup_no,
                    lead.id,
                )
                activity.note = (
                    "<p><b>[AI DRAFT — Follow-up %s]</b></p>"
                    "<p><i>AI draft generation returned empty. Please compose manually or wait for daily retry.</i></p>"
                ) % followup_no
                return

        subject = subject or _("Quick follow-up on your inquiry")

        body_html = tools.plaintext2html(body_text)
        note_parts = [
            "<p><b>[AI DRAFT — Follow-up %s]</b></p>" % followup_no,
            "<p><b>Subject:</b> %s</p>" % subject,
            body_html,
        ]
        if angle:
            note_parts.append("<p><b>Angle:</b> %s</p>" % tools.plaintext2html(angle))
        if cta:
            note_parts.append("<p><b>CTA:</b> %s</p>" % tools.plaintext2html(cta))

        activity.note = "".join(note_parts)
        _logger.info("sales_ai: Follow-up #%d draft created for lead %s", followup_no, lead.id)

    # =========================================================================
    # PHASE 5: PRESALE ON LEAD
    # =========================================================================

    def action_start_presale(self):
        """
        TicketGistAgent (Sonnet) — generate a discussion gist from all prior lead history.
        Called by action_open_presale. Stores gist in x_ticket_gist and posts to chatter.
        """
        for lead in self:
            # Assign reference if not set
            if not lead.x_presale_ref:
                lead.x_presale_ref = "PST-%d" % lead.id
            if lead.x_presale_status == "none":
                lead.x_presale_status = "open"

            # Gather last 50 messages (emails + comments)
            msgs = lead.message_ids.sorted("date", reverse=False)[-50:]
            lines = []
            for m in msgs:
                if m.message_type not in ("email", "comment"):
                    continue
                snippet = (m.body or "").replace("\n", " ")
                lines.append("[%s] %s: %s" % (m.date, m.author_id.display_name or "", snippet[:400]))

            if not lines:
                lead.message_post(
                    body=_("<b>[%s] Presale opened.</b> No prior discussions found.") % lead.x_presale_ref,
                    subtype_xmlid="mail.mt_note",
                )
                _logger.info("sales_ai: Presale opened for lead %s — ref %s (no history)", lead.id, lead.x_presale_ref)
                continue

            try:
                summary = self._claude().call(
                    tier="sonnet",
                    system_prompt=prompts.PROMPTS["ticket_gist_system"],
                    user_message="\n\n".join(lines)[:120000],
                    max_tokens=1500,
                    expect_json=False,
                )
            except Exception:
                _logger.error("sales_ai: Presale gist generation failed for lead %s", lead.id, exc_info=True)
                continue

            # Store gist on lead field
            lead.x_ticket_gist = summary or ""
            lead.message_post(
                body="<h3>[%s] Presale Discussion Gist</h3>%s" % (
                    lead.x_presale_ref, summary or "No gist generated."
                ),
                subtype_xmlid="mail.mt_note",
            )
            _logger.info("sales_ai: Presale gist generated for lead %s — ref %s", lead.id, lead.x_presale_ref)

    @api.model
    def cron_generate_presale_agenda(self):
        """10:30 AM cron — generate daily agenda for each lead in active presale."""
        _logger.info("sales_ai: [CRON] Presale agenda generator started")
        today = fields.Date.today()
        leads = self.search([
            ("x_presale_status", "in", ["open", "ready_for_wbs", "wbs_done"]),
        ])
        _logger.info("sales_ai: [CRON] Found %d leads with active presale", len(leads))

        generated = 0
        for lead in leads:
            try:
                lead._generate_single_presale_agenda(today)
                generated += 1
            except Exception:
                _logger.error("sales_ai: Agenda generation failed for lead %s", lead.id, exc_info=True)

        _logger.info("sales_ai: [CRON] Presale agenda completed — %d/%d generated", generated, len(leads))

    def _generate_single_presale_agenda(self, today):
        """Generate agenda for one lead's presale."""
        self.ensure_one()
        since = self.x_last_agenda_date or (today - relativedelta(days=2))
        msgs = self.message_ids.filtered(
            lambda m: m.date and m.date.date() >= since
        ).sorted("date", reverse=False)

        lines = ["[Recent Lead Activity]"]
        for m in msgs:
            lines.append(f"[{m.date}] {m.author_id.display_name}: {(m.body or '')[:400]}")

        try:
            agenda_html = self._claude().call(
                tier="haiku",
                system_prompt=prompts.PROMPTS["presale_agenda_system"],
                user_message="\n".join(lines)[:160000],
                max_tokens=800,
                expect_json=False,
            )
        except Exception:
            _logger.error("sales_ai: Agenda Claude call failed for lead %s", self.id, exc_info=True)
            return

        if agenda_html:
            self.message_post(body=agenda_html, subtype_xmlid="mail.mt_note")
            self.x_last_agenda_date = today
            _logger.info("sales_ai: Presale agenda posted on lead %s", self.id)

    def action_generate_presale_client_email(self, mom_content=None):
        """Draft a client-facing email based on presale discussion."""
        self.ensure_one()

        # Last 20 client conversations
        history_msgs = self.message_ids.sorted("date", reverse=False)[-20:]
        history = []
        for m in history_msgs:
            if m.message_type == "email":
                history.append(
                    f"[{m.date}] {m.author_id.display_name}: {m.subject or ''} :: {(m.body or '')[:400]}"
                )

        if mom_content is None:
            # Use last few internal notes
            notes = self.message_ids.filtered(
                lambda m: m.subtype_id and m.subtype_id.xml_id == "mail.mt_note"
            ).sorted("date", reverse=False)[-5:]
            mom_content = "\n\n".join((n.body or "")[:800] for n in notes)

        user_msg = json.dumps(
            {"presale_mom": mom_content, "client_history": history},
            ensure_ascii=False,
        )

        try:
            resp = self._claude().call(
                tier="sonnet",
                system_prompt=prompts.PROMPTS["presale_email_system"],
                user_message=user_msg,
                max_tokens=800,
                expect_json=True,
            )
        except Exception:
            _logger.error("sales_ai: Presale email draft failed for lead %s", self.id, exc_info=True)
            return

        subject = resp.get("subject") or _("Follow-up from our technical discussion")
        body_html = resp.get("body_html") or _(
            "<p>Following up on our recent technical discussion.</p>"
        )

        activity_type = self.env.ref(
            "sales_ai_integration.activity_type_presale_email", raise_if_not_found=False
        )
        self.env["mail.activity"].sudo().create(
            {
                'res_model_id': self.env.ref('crm.model_crm_lead').id,
                "res_id": self.id,
                "user_id": self.user_id.id,
                "activity_type_id": activity_type.id if activity_type else False,
                "note": "[AI DRAFT — Presale]\n\n" + subject + "\n\n" + body_html,
                "date_deadline": fields.Date.today(),
            }
        )
        _logger.info("sales_ai: Presale email draft activity created on lead %s", self.id)

    def action_request_proposal_from_ai(self):
        """
        ProposalGeneratorAgent (Opus) — generate a full sales proposal directly on this lead.
        Stores the result on the lead, posts executive summary to chatter,
        and sends to n8n to write the full document to Google Drive.
        """
        self.ensure_one()
        if self.x_presale_status not in ("wbs_done", "ready_for_proposal", "ready_for_wbs"):
            raise UserError(_("Complete WBS validation before requesting a proposal."))

        self.x_presale_status = "ready_for_proposal"

        # Gather all presale MOMs
        all_presale_moms = []
        if self.x_presale_mom_history:
            try:
                for entry in json.loads(self.x_presale_mom_history):
                    all_presale_moms.append(entry.get("mom") or "")
            except Exception:
                pass

        # WBS summary
        wbs_summary = []
        if self.x_wbs_json:
            try:
                wbs_data = json.loads(self.x_wbs_json)
                for phase in wbs_data.get("wbs_phases") or []:
                    wbs_summary.append({
                        "phase_name": phase.get("phase_name", ""),
                        "task_count": len(phase.get("tasks", [])),
                    })
            except Exception:
                pass

        # Enrichment fields summary
        enriched_fields = {
            "company_industry": self.x_industry or "",
            "company_employee_count": self.x_employee_count_range or str(self.x_employee_count or ""),
            "company_hq_country": self.x_hq_country_id.name if self.x_hq_country_id else "",
            "company_hq_city": self.x_hq_city or "",
            "contact_seniority": self.x_contact_seniority_structured or "",
            "likely_pain_point": self.x_likely_pain_point or "",
        }

        # Requirements from recent notes
        recent_notes = self.message_ids.filtered(
            lambda m: m.subtype_id and m.subtype_id.xml_id == "mail.mt_note"
        ).sorted("date", reverse=False)[-10:]
        requirements = [(n.body or "")[:500] for n in recent_notes if (n.body or "").strip()]

        proposal_input = {
            "lead_id": self.id,
            "ticket_id": self.x_presale_ref or ("PST-%d" % self.id),
            "client_company": self.partner_id.name or self.partner_name or "",
            "client_primary_contact": self.contact_name or "",
            "client_designation": self.function or "",
            "template_sections": [
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
            ],
            "requirements": requirements,
            "wbs_summary": wbs_summary,
            "wbs_sheet_url": self.x_wbs_sheet_url or "",
            "pricing_table": [],
            "tech_stack": [],
            "our_team_profiles": [],
            "timeline_weeks": "",
            "go_live_date": "",
            "enriched_fields": enriched_fields,
            "ticket_gist": self.x_ticket_gist or "",
            "all_presale_moms": all_presale_moms,
            "rep_name": self.user_id.name if self.user_id else "",
            "rep_designation": (self.user_id.job_title if self.user_id else "") or "Account Executive",
        }

        try:
            proposal_result = self._claude().call(
                tier="opus",
                system_prompt=prompts.PROMPTS["proposal_system"],
                user_message=json.dumps(proposal_input, ensure_ascii=False),
                max_tokens=6000,
                expect_json=True,
            )
        except Exception:
            _logger.error("sales_ai: Proposal generation (Opus) failed for lead %s", self.id, exc_info=True)
            raise UserError(_("Proposal generation failed. Please try again."))

        if not isinstance(proposal_result, dict):
            raise UserError(_("Proposal Agent returned an unexpected response."))

        exec_summary = proposal_result.get("executive_summary") or ""
        sections = proposal_result.get("proposal_sections") or {}
        word_count = proposal_result.get("word_count") or 0
        cover = proposal_result.get("cover_page") or {}

        # Post executive summary + section list to chatter
        chatter_parts = [
            "<h3>[%s] Proposal Draft Generated (%d words)</h3>" % (
                self.x_presale_ref or ("PST-%d" % self.id), word_count
            )
        ]
        if cover:
            chatter_parts.append("<p><b>%s</b><br/>%s</p>" % (
                cover.get("title", ""), cover.get("subtitle", "")
            ))
        if exec_summary:
            chatter_parts.append("<h4>Executive Summary</h4><p>%s</p>" % exec_summary)
        if sections:
            chatter_parts.append(
                "<p><b>Sections:</b> %s</p>" % ", ".join(sections.keys())
            )

        self.message_post(body="\n".join(chatter_parts), subtype_xmlid="mail.mt_note")
        _logger.info(
            "sales_ai: Proposal (Opus) generated for lead %s — %d words, %d sections",
            self.id, word_count, len(sections),
        )

        # Send to n8n to write to Google Drive
        try:
            self._n8n().post(
                "proposal_request",
                {
                    "lead_id": self.id,
                    "presale_ref": self.x_presale_ref or ("PST-%d" % self.id),
                    "proposal_result": proposal_result,
                    "wbs_sheet_url": self.x_wbs_sheet_url or "",
                },
            )
        except Exception:
            _logger.warning(
                "sales_ai: Proposal n8n send failed for lead %s (saved locally)", self.id,
                exc_info=True,
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Proposal Generated"),
                "type": "success",
                "message": _(
                    "AI proposal generated (%d words). "
                    "n8n will write to Google Drive and send back the URL."
                ) % word_count,
            },
        }

    # =========================================================================
    # PHASE 6: CLIENT MOM GENERATION
    # =========================================================================

    def action_generate_client_mom(
        self,
        transcript: str,
        meeting_date: str = "",
        meeting_duration: int = 0,
        attendees: list = None,
        conversation_id: str = "",
        conversation_url: str = "",
        source: str = "",
        meeting_name: str = "",
        request_payload_json: str | None = None,
    ):
        """Generate full MOM + client-safe draft email from meeting transcript.

        :param transcript: raw transcript text
        :param meeting_date: ISO date string (from n8n / Apollo)
        :param meeting_duration: duration in minutes
        :param attendees: list of dicts [{name, role, company, is_client}]
        :param conversation_url: Apollo conversation URL
        """
        self.ensure_one()
        _logger.info(
            "sales_ai: Generating client MOM for lead %s (transcript: %d chars)",
            self.id, len(transcript),
        )

        calendar_link = self.user_id.x_calendar_link if self.user_id else ""
        enrichment_fields = {}
        if self.x_apollo_data_raw:
            try:
                enrichment_fields = json.loads(self.x_apollo_data_raw)
            except Exception:
                pass

        claude_payload = json.dumps({
            "transcript": transcript[:120000],
            "meeting_date": meeting_date or str(fields.Date.today()),
            "meeting_duration": meeting_duration or 0,
            "attendees": attendees or [],
            "rep_name": self.user_id.name if self.user_id else "",
            "rep_designation": self.user_id.job_title if self.user_id else "Account Executive",
            "rep_calendar_link": calendar_link,
            "client_company": self.partner_name or (
                self.partner_id.name if self.partner_id else ""
            ),
            "enriched_fields": enrichment_fields,
        }, ensure_ascii=False)

        try:
            resp = self._claude().call(
                tier="sonnet",
                system_prompt=prompts.PROMPTS["client_mom_system"],
                user_message=claude_payload,
                max_tokens=3000,
                expect_json=True,
            )
        except Exception:
            _logger.error(
                "sales_ai: Client MOM generation failed for lead %s",
                self.id, exc_info=True,
            )
            return

        raw_mom_md = _clean_internal_mom_text(resp.get("internal_mom") or "")
        raw_mom_html = resp.get("full_mom_html") or ""
        if raw_mom_html:
            full_mom = raw_mom_html
        elif raw_mom_md:
            # Render plain/markdown-style text into HTML for chatter
            full_mom = tools.html_sanitize(tools.plaintext2html(raw_mom_md))
        else:
            full_mom = "<p>%s</p>" % _("No MOM generated.")

        email_subject = resp.get("client_email_subject") or _("Summary of our recent call")
        email_body_text = (
            resp.get("client_email_body")
            or resp.get("client_email_body_html")
            or "Thank you for your time."
        )
        action_items_rep = resp.get("action_items_rep") or []
        action_items_client = resp.get("action_items_client") or []
        next_meeting = resp.get("next_meeting_suggested", False)

        # --- Post internal MOM + action items in a single, well-formatted chatter note ---
        body_parts = [full_mom]
        if action_items_rep:
            body_parts.append(
                "<h4>%s</h4><ul>%s</ul>"
                % (
                    _("Rep action items"),
                    "".join("<li>%s</li>" % tools.html_escape(i) for i in action_items_rep),
                )
            )
        if action_items_client:
            body_parts.append(
                "<h4>%s</h4><ul>%s</ul>"
                % (
                    _("Client action items"),
                    "".join("<li>%s</li>" % tools.html_escape(i) for i in action_items_client),
                )
            )
        if next_meeting:
            body_parts.append(
                "<p><i>%s</i></p>"
                % _("Claude suggests scheduling a follow-up meeting.")
            )
        self.message_post(body="<br/>".join(body_parts), subtype_xmlid="mail.mt_note")

        # --- Update x_mom_history JSON ---
        mom_entry = {
            "date": meeting_date or str(fields.Date.today()),
            "internal_mom": full_mom,
            "client_email_subject": email_subject,
            "client_email_body": email_body_text,
            "action_items_rep": action_items_rep,
            "action_items_client": action_items_client,
            "next_meeting_suggested": next_meeting,
        }
        try:
            history = json.loads(self.x_mom_history or "[]")
        except Exception:
            history = []
        history.append(mom_entry)
        self.x_mom_history = json.dumps(history, ensure_ascii=False)

        # Persist raw transcript metadata in a separate notebook-style model so we
        # always have a record of what was processed.
        try:
            self.env["sales.ai.meeting.transcript"].sudo().create(
                {
                    "lead_id": self.id,
                    "meeting_name": meeting_name or self.name or "",
                    "meeting_date": meeting_date or str(fields.Date.today()),
                    "meeting_start": False,
                    "meeting_duration": meeting_duration or 0,
                    "conversation_id": conversation_id or "",
                    "conversation_url": conversation_url or "",
                    "source": source or "meeting_done",
                    "transcript": transcript[:150000],
                    "payload_json": claude_payload,
                    "request_payload_json": request_payload_json or "",
                }
            )
        except Exception:
            _logger.error(
                "sales_ai: Failed to log meeting transcript entry for lead %s", self.id, exc_info=True
            )

        # --- Create review activity for rep ---
        activity_type = self.env.ref(
            "sales_ai_integration.activity_type_client_mom", raise_if_not_found=False
        )
        note_html = """
<p><b>[AI DRAFT — Client MOM]</b></p>
<p><b>%s</b> %s</p>
<hr/>
%s
""" % (
            _("Subject:"),
            tools.html_escape(email_subject),
            tools.plaintext2html(email_body_text),
        )

        self.env["mail.activity"].sudo().create(
            {
                "res_model_id": self.env.ref("crm.model_crm_lead").id,
                "res_id": self.id,
                "user_id": self.user_id.id,
                "activity_type_id": activity_type.id if activity_type else False,
                "summary": _(
                    "Review & send meeting MOM to %s",
                    self.partner_name or self.contact_name or "client",
                ),
                "note": tools.html_sanitize(note_html),
                "date_deadline": fields.Date.today(),
            }
        )

        # # --- Notify n8n ---
        # try:
        #     self._n8n().post("mom_generated_notification", {
        #         "lead_id": self.id,
        #         "lead_name": self.name,
        #         "company": self.partner_name or "",
        #         "contact_name": self.contact_name or "",
        #         "rep_name": self.user_id.name if self.user_id else "",
        #         "rep_email": self.user_id.email if self.user_id else "",
        #         "meeting_date": meeting_date or str(fields.Date.today()),
        #         "email_subject": email_subject,
        #         "action_items_count": len(action_items_rep) + len(action_items_client),
        #         "next_meeting_suggested": next_meeting,
        #         "source": "transcript_processing",
        #     })
        # except Exception:
        #     _logger.error(
        #         "sales_ai: n8n mom_generated notification failed for lead %s",
        #         self.id, exc_info=True,
        #     )

        _logger.info(
            "sales_ai: Client MOM posted + review activity created for lead %s",
            self.id,
        )

    # ------------------------------------------------------------------
    # Transcript request (manual button + cron)
    # ------------------------------------------------------------------

    def action_request_meeting_transcript(self):
        """Button handler: ask n8n to fetch the transcript for this lead's latest meeting."""
        self.ensure_one()
        event = self._find_latest_linked_meeting()
        if not event:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No linked meeting"),
                    "message": _("No calendar event is linked to this lead."),
                    "type": "warning",
                    "sticky": False,
                },
            }
        # if event.x_transcript_requested:
        #     return {
        #         "type": "ir.actions.client",
        #         "tag": "display_notification",
        #         "params": {
        #             "title": _("Already requested"),
        #             "message": _(
        #                 "Transcript for '%s' was already requested. "
        #                 "Check back shortly or re-sync from n8n.",
        #                 event.name or "",
        #             ),
        #             "type": "info",
        #             "sticky": False,
        #         },
        #     }

        _logger.info(
            "sales_ai: [TRANSCRIPT-BTN] Manual transcript request started for lead %s / event %s",
            self.id,
            event.id,
        )
        try:
            print('jjjjjjjjjjjjjjjjjj')
            self._post_transcript_request(event, source="manual_button")
        except Exception as exc:
            _logger.error(
                "sales_ai: [TRANSCRIPT-BTN] Error requesting transcript for lead %s / event %s: %s",
                self.id,
                event.id,
                exc,
                exc_info=True,
            )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Transcript request failed"),
                    "message": _(
                        "Could not request transcript for '%s'. "
                        "Please check Sales AI → n8n settings and server logs.",
                        event.name or "",
                    ),
                    "type": "danger",
                    "sticky": False,
                },
            }

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Transcript requested"),
                "message": _(
                    "n8n has been asked to fetch the transcript for '%s'. "
                    "MOM will be generated automatically once received.",
                    event.name or "",
                ),
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def cron_request_meeting_transcripts(self):
        """Every 30 min: request transcripts for meetings that ended ~1 hour ago."""
        from datetime import timedelta

        now = fields.Datetime.now()
        window_start = now - timedelta(minutes=90)
        window_end = now - timedelta(minutes=30)

        Event = self.env["calendar.event"].sudo()
        events = Event.search([
            ("stop", ">=", window_start),
            ("stop", "<=", window_end),
            ("opportunity_id", "!=", False),
            ("x_transcript_requested", "=", False),
            ("x_is_presale_meeting", "=", False),
        ])

        if not events:
            return

        _logger.info(
            "sales_ai: [TRANSCRIPT-CRON] Found %d meetings that ended ~1h ago, requesting transcripts",
            len(events),
        )
        for event in events:
            lead = event.opportunity_id
            if not lead or not lead.active:
                continue
            try:
                lead._post_transcript_request(event, source="cron")
            except Exception:
                _logger.error(
                    "sales_ai: Transcript request failed for event %s (lead %s)",
                    event.id, lead.id, exc_info=True,
                )

    def _find_latest_linked_meeting(self):
        """Return the most recent calendar.event linked to this lead."""
        self.ensure_one()
        return self.env["calendar.event"].sudo().search(
            [("opportunity_id", "=", self.id)],
            order="start desc",
            limit=1,
        )

    def _post_transcript_request(self, event, source="cron"):
        """POST to n8n asking it to fetch the meeting transcript from Apollo."""
        attendees = [p for p in event.partner_ids if p.email or p.name]
        attendee_emails = [p.email for p in attendees if p.email]
        attendee_names = [p.name for p in attendees if p.name]
        payload = {
            "lead_id": self.id,
            "lead_name": self.name,
            "company": self.partner_name or "",
            "contact_name": self.contact_name or "",
            "contact_email": self.email_from or "",
            "rep_name": self.user_id.name if self.user_id else "",
            "rep_email": self.user_id.email if self.user_id else "",
            "lead_url": f"/web#id={self.id}&model=crm.lead&view_type=form",
            "meeting_id": event.id,
            "meeting_name": event.name or "",
            "meeting_start": str(event.start) if event.start else "",
            "meeting_stop": str(event.stop) if event.stop else "",
            "attendee_emails": attendee_emails,
            "participants": attendee_names,
            "calendar_owner": event.user_id.name if event.user_id else "",
            "calendar_owner_email": event.user_id.email if event.user_id else "",
            "source": source,
        }
        _logger.info(
            "sales_ai: [TRANSCRIPT-REQ] lead_id=%s event_id=%s source=%s attendees=%s participants=%s",
            self.id,
            event.id,
            source,
            attendee_emails,
            attendee_names,
        )

        resp = self._n8n().post("request_meeting_transcript", payload)
        _logger.info(
            "sales_ai: [TRANSCRIPT-REQ] n8n response for lead %s / event %s: %s",
            self.id,
            event.id,
            repr(resp)[:500],
        )

        event.x_transcript_requested = True

        self.message_post(
            body=_(
                "Transcript requested for meeting '%s' (source: %s). "
                "MOM will be generated once n8n returns the transcript.",
                event.name or "", source,
            ),
            subtype_xmlid="mail.mt_note",
        )
        _logger.info(
            "sales_ai: Transcript requested for event %s (lead %s, source=%s)",
            event.id, self.id, source,
        )

    # =========================================================================
    # PHASE 7: LEAD CLOSURE RETROSPECTIVE
    # =========================================================================

    def action_generate_closure_retro(self):
        """Generate a Won/Lost retrospective and post to the lead."""
        for lead in self:
            outcome = "Won" if lead.stage_id.is_won else "Lost"
            _logger.info("sales_ai: Generating %s retrospective for lead %s", outcome, lead.id)

            msgs = lead.message_ids.sorted("date", reverse=False)
            history_lines: List[str] = []
            for m in msgs[-200:]:
                if not m.date:
                    continue
                who = m.author_id.display_name or ""
                subj = m.subject or ""
                body = (m.body or "").replace("\n", " ")[:600]
                history_lines.append(f"[{m.date}] {who}: {subj} :: {body}")

            data = {
                "outcome": outcome,
                "lead_name": lead.name,
                "company": lead.partner_id.name if lead.partner_id else "",
                "salesperson": lead.user_id.name if lead.user_id else "",
                "create_date": str(lead.create_date),
                "close_date": str(lead.write_date),
                "stage": lead.stage_id.display_name,
                "presale_status": lead.x_presale_status,
                "history": history_lines,
            }

            try:
                html = self._claude().call(
                    tier="sonnet",
                    system_prompt=prompts.PROMPTS["retro_system"],
                    user_message=json.dumps(data, ensure_ascii=False)[:160000],
                    max_tokens=3000,
                    expect_json=False,
                )
            except Exception:
                _logger.error("sales_ai: Closure retro failed for lead %s", lead.id, exc_info=True)
                continue

            lead.message_post(
                body=html or "<p>Retro not generated.</p>",
                subtype_xmlid="mail.mt_note",
            )
            lead.x_retro_logged = True
            _logger.info("sales_ai: %s retrospective posted for lead %s", outcome, lead.id)

    # =========================================================================
    # PHASE 8: ESCALATION CRON
    # =========================================================================

    @api.model
    def cron_check_human_pause_escalations(self):
        """Daily 08:00 cron: check overdue AI drafts, MOMs, stale WBS."""
        _logger.info("sales_ai: [CRON] Escalation check started")
        today = fields.Date.today()
        now = fields.Datetime.now()

        Activity = self.env["mail.activity"].sudo()
        n8n = self._n8n()

        # HP1 & HP3: overdue AI email drafts
        overdue_drafts = Activity.search(
            [
                (
                    "activity_type_id",
                    "in",
                    [
                        self.env.ref("sales_ai_integration.activity_type_followup_email").id,
                        self.env.ref("sales_ai_integration.activity_type_presale_email").id,
                    ],
                ),
                ("date_deadline", "<", today),
                ("note", "ilike", "AI DRAFT%"),
            ]
        )
        for act in overdue_drafts:
            days_overdue = (today - act.date_deadline).days
            lead = self.browse(act.res_id)
            if not lead.exists():
                continue
            payload = {
                "lead_id": lead.id,
                "lead_name": lead.name,
                "rep": act.user_id.name,
                "days_overdue": days_overdue,
            }
            if days_overdue == 1:
                payload["level"] = "warning"
                n8n.post("teams_followup_overdue", payload)
            elif days_overdue >= 2:
                payload["level"] = "urgent"
                n8n.post("teams_followup_overdue_manager", payload)

        # HP2: overdue MOM reviews
        mom_type = self.env.ref(
            "sales_ai_integration.activity_type_client_mom", raise_if_not_found=False
        )
        if mom_type:
            overdue_moms = Activity.search(
                [("activity_type_id", "=", mom_type.id), ("date_deadline", "<", today)]
            )
            for act in overdue_moms:
                lead = self.browse(act.res_id)
                if not lead.exists():
                    continue
                hours_since = (
                    now - fields.Datetime.from_string(str(act.date_deadline) + " 00:00:00")
                ).total_seconds() / 3600.0
                payload = {
                    "lead_id": lead.id,
                    "lead_name": lead.name,
                    "rep": act.user_id.name,
                    "hours_overdue": hours_since,
                }
                if 4 <= hours_since < 24:
                    payload["level"] = "warning"
                    n8n.post("teams_mom_overdue", payload)
                elif hours_since >= 24:
                    payload["level"] = "urgent"
                    n8n.post("teams_mom_overdue_manager", payload)

        # HP4: WBS validation stale leads (ready_for_wbs for too long)
        stale_wbs = self.search([
            ("x_presale_status", "=", "ready_for_wbs"),
            ("write_date", "<", now - relativedelta(days=2)),
        ])
        for lead in stale_wbs:
            days_waiting = (now.date() - lead.write_date.date()).days
            payload = {
                "lead_id": lead.id,
                "lead_name": lead.name,
                "days_waiting": days_waiting,
            }
            if days_waiting in (2, 4, 7):
                payload["level"] = "warning" if days_waiting == 2 else "urgent"
                n8n.post("teams_wbs_stale", payload)

        _logger.info("sales_ai: [CRON] Escalation check completed")


# =============================================================================
# LIFECYCLE HOOKS
# =============================================================================

class CrmLeadLifecycle(models.Model):
    """
    Lost lead retro via write override.
    base.automation on_write skips archived records, so we intercept here.
    """

    _inherit = "crm.lead"

    def write(self, vals):
        going_lost = self.env["crm.lead"]
        if "active" in vals and not vals["active"]:
            going_lost = self.filtered(
                lambda l: l.active and not l.stage_id.is_won
            )

        # Detect leads gaining a new owner (lead assignment event)
        new_owner_ids = None
        if "user_id" in vals and vals["user_id"]:
            # Many2one write semantics: an int or (x, id, 0); only handle simple int
            new_owner_ids = self.filtered(lambda l: not l.user_id and vals["user_id"])

        res = super().write(vals)

        # Trigger closure retrospective for lost / archived leads
        # if going_lost:
        #     try:
        #         _logger.info(
        #             "sales_ai: Triggering lost-lead retro for %d leads", len(going_lost)
        #         )
        #         going_lost.with_context(active_test=False).action_generate_closure_retro()
        #     except Exception:
        #         _logger.error("sales_ai: Lost-lead retro failed", exc_info=True)

        # After write, create assignment activity + auto-ack draft for newly assigned leads
        if new_owner_ids:
            for lead in new_owner_ids.exists():
                try:
                    # Only generate assignment + auto-ack when enrichment + scoring
                    # are already done and the lead is genuine. Otherwise, wait until
                    # the pipeline completes.
                    if lead.x_enrichment_done and lead.x_scoring_done and lead.x_classification == "genuine":
                        # Activity = self.env["mail.activity"].sudo()
                        # activity_type = self.env.ref(
                        #     "mail.mail_activity_data_email", raise_if_not_found=False
                        # )
                        # Activity.create(
                        #     {
                        #         "res_model_id": self.env.ref('crm.model_crm_lead').id,
                        #         "res_id": lead.id,
                        #         "user_id": lead.user_id.id,
                        #         "activity_type_id": activity_type.id if activity_type else False,
                        #         "summary": _("New lead assigned — review & send auto-ack"),
                        #         "note": _(
                        #             "Lead %s assigned to you. Review the AI-generated auto-ack draft and send today.",
                        #             lead.name or "",
                        #         ),
                        #         "date_deadline": fields.Date.today(),
                        #     }
                        # )
                        # Generate the AI draft for the auto-ack (does not send email)
                        lead.action_send_auto_ack()
                    else:
                        _logger.info(
                            "sales_ai: [AUTO-ACK] Delay assignment/auto-ack for lead %s "
                            "(enriched=%s, scored=%s, classification=%s).",
                            lead.id,
                            lead.x_enrichment_done,
                            lead.x_scoring_done,
                            lead.x_classification,
                        )
                except Exception:
                    _logger.error(
                        "sales_ai: Failed to create assignment activity / auto-ack draft for lead %s",
                        lead.id,
                        exc_info=True,
                    )
        return res


# =============================================================================
# MESSAGE POST OVERRIDE (reply detection + discussion sync)
# =============================================================================

class CrmLeadMessage(models.Model):
    """
    Extend message_post to:
      - detect customer replies → classify intent → reset follow-ups
      - sync external discussions to presale (internal note on same lead)
    """

    _inherit = "crm.lead"

    def message_post(self, **kwargs):
        is_incoming_email = False
        body = kwargs.get("body") or ""
        author_id = kwargs.get("author_id")
        message_type = kwargs.get("message_type", "comment")

        if message_type == "email":
            if author_id:
                partner = self.env["res.partner"].browse(author_id)
            else:
                partner = False
            is_incoming_email = bool(partner and not partner.user_ids)

        # Guard against recursive calls from our own message_post calls
        if self.env.context.get("_sales_ai_message_post_lock"):
            return super().message_post(**kwargs)

        result = super().message_post(**kwargs)

        if is_incoming_email:
            _logger.info("sales_ai: External reply detected on lead(s) %s", self.ids)
            reply_from = kwargs.get("email_from") or ""
            reply_subject = kwargs.get("subject") or ""
            self.with_context(
                _sales_ai_message_post_lock=True
            )._handle_external_reply(body, reply_from=reply_from, reply_subject=reply_subject)
        else:
            # Outgoing email: if this is the first outbound after scoring, treat it
            # as the auto-ack send event and schedule follow-ups from this date.
            if message_type == "email":
                for lead in self:
                    if lead.x_lead_score_band and lead.x_followup_stage == 0:
                        _logger.info(
                            "sales_ai: [AUTO-ACK] Detected outbound email for lead %s — "
                            "scheduling follow-up sequence based on ack date.",
                            lead.id,
                        )
                        # Use this email as base date for follow-up schedule
                        # (context_timestamp handles timezone correctly).
                        email_dt = fields.Datetime.context_timestamp(
                            lead, fields.Datetime.now()
                        )
                        lead.action_create_followup_activities(base_date=email_dt)

        return result

    def _handle_external_reply(self, body_text: str, reply_from: str = "", reply_subject: str = ""):
        """
        Full ReplyClassifierAgent — classifies inbound reply into 10 intents
        and takes appropriate CRM actions.
        """
        service = self.env["claude.service"]
        Activity = self.env["mail.activity"].sudo()
        reply_received_type = self.env.ref(
            "sales_ai_integration.activity_type_reply_received",
            raise_if_not_found=False,
        )

        for lead in self:
            lead.x_last_reply_date = fields.Datetime.now()

            if not body_text:
                continue

            classify_payload = {
                "reply_body": body_text[:3000],
                "reply_from": reply_from,
                "reply_subject": reply_subject,
                "lead_stage": lead.stage_id.name if lead.stage_id else "",
                "lead_score_band": lead.x_lead_score_band or "warm",
                "emails_sent": lead.x_followup_stage or 0,
            }
            try:
                result = service.call(
                    tier="haiku",
                    system_prompt=prompts.PROMPTS["reply_intent_system"],
                    user_message=json.dumps(classify_payload, ensure_ascii=False),
                    max_tokens=300,
                    expect_json=True,
                )
            except Exception:
                _logger.error(
                    "sales_ai: Reply intent classification failed for lead %s",
                    lead.id, exc_info=True,
                )
                continue

            if not isinstance(result, dict):
                result = {}

            intent = (result.get("intent") or "interested").lower()
            confidence = float(result.get("confidence") or 0)
            note_for_rep = result.get("note_for_rep") or ""
            ooo_return_date = result.get("ooo_return_date")
            new_contact_hint = result.get("new_contact_hint")
            priority = result.get("priority_flag", False)

            valid_intents = (
                "interested", "meeting_booked", "not_interested", "ooo",
                "wrong_person", "referral", "generic_positive", "unsubscribe",
                "question", "negotiating",
            )
            if intent not in valid_intents:
                intent = "interested"

            lead.x_reply_intent = intent
            if priority:
                lead.priority = "3"

            _logger.info(
                "sales_ai: Lead %s reply classified as %s (conf=%.0f%%)",
                lead.id, intent, confidence,
            )

            lead.message_post(
                body=_(
                    "<b>Reply received:</b> %s (confidence: %.0f%%)<br/>%s",
                    intent.replace("_", " ").title(), confidence, note_for_rep,
                ),
                subtype_xmlid="mail.mt_note",
            )

            if reply_received_type and lead.user_id:
                Activity.create({
                    'res_model_id': self.env.ref('crm.model_crm_lead').id,
                    "res_id": lead.id,
                    "user_id": lead.user_id.id,
                    "activity_type_id": reply_received_type.id,
                    "summary": _("Reply received — %s", intent.replace("_", " ").title()),
                    "note": note_for_rep,
                    "date_deadline": fields.Date.today(),
                })

            lead._cancel_pending_followups()

            # --- Intent-specific actions ---

            if intent in ("interested", "generic_positive"):
                lead.x_followup_stage = 0
                lead.action_create_followup_activities(base_date=fields.Datetime.now())

            elif intent == "question":
                todo_type = self.env.ref(
                    "mail.mail_activity_data_todo", raise_if_not_found=False
                )
                if lead.user_id:
                    Activity.create({
                        'res_model_id': self.env.ref('crm.model_crm_lead').id,
                        "res_id": lead.id,
                        "user_id": lead.user_id.id,
                        "activity_type_id": todo_type.id if todo_type else False,
                        "summary": _("Answer customer question (priority)"),
                        "note": note_for_rep,
                        "date_deadline": fields.Date.today(),
                    })

            elif intent == "negotiating":
                stage_negotiation = self.env.ref(
                    "sales_ai_integration.stage_negotiation",
                    raise_if_not_found=False,
                )
                if stage_negotiation:
                    lead.stage_id = stage_negotiation
                todo_type = self.env.ref(
                    "mail.mail_activity_data_todo", raise_if_not_found=False
                )
                if lead.user_id:
                    Activity.create({
                        'res_model_id': self.env.ref('crm.model_crm_lead').id,
                        "res_id": lead.id,
                        "user_id": lead.user_id.id,
                        "activity_type_id": todo_type.id if todo_type else False,
                        "summary": _("Negotiation follow-up — respond today"),
                        "note": note_for_rep,
                        "date_deadline": fields.Date.today(),
                    })

            elif intent == "meeting_booked":
                stage_meeting = self.env.ref(
                    "sales_ai_integration.stage_meeting",
                    raise_if_not_found=False,
                )
                if stage_meeting:
                    lead.stage_id = stage_meeting
                try:
                    self._n8n().post("meeting_booked_notification", {
                        "lead_id": lead.id,
                        "lead_name": lead.name,
                        "company": lead.partner_name or "",
                        "contact_name": lead.contact_name or "",
                        "contact_email": lead.email_from or "",
                        "rep_name": lead.user_id.name if lead.user_id else "",
                        "rep_email": lead.user_id.email if lead.user_id else "",
                        "meeting_name": "",
                        "meeting_start": "",
                        "source": "reply_classification",
                    })
                except Exception:
                    _logger.error(
                        "sales_ai: n8n meeting_booked notification failed for lead %s",
                        lead.id, exc_info=True,
                    )

            elif intent == "not_interested":
                lead.action_set_lost(
                    lost_reason_id=self.env.ref(
                        "crm.crm_lost_reason3", raise_if_not_found=False
                    ),
                )

            elif intent == "ooo":
                days_to_wait = 7
                if ooo_return_date:
                    try:
                        return_dt = fields.Date.from_string(ooo_return_date)
                        days_to_wait = max(
                            3, (return_dt - fields.Date.today()).days + 2
                        )
                        lead.x_ooo_return_date = return_dt
                    except Exception:
                        pass
                ooo_base_dt = lead._business_day_offset(
                    fields.Datetime.now(), days_to_wait
                )
                lead.x_followup_stage = 0
                lead.action_create_followup_activities(base_date=ooo_base_dt)

            elif intent == "wrong_person":
                if lead.user_id:
                    todo_type = self.env.ref(
                        "mail.mail_activity_data_todo", raise_if_not_found=False
                    )
                    Activity.create({
                        'res_model_id': self.env.ref('crm.model_crm_lead').id,
                        "res_id": lead.id,
                        "user_id": lead.user_id.id,
                        "activity_type_id": todo_type.id if todo_type else False,
                        "summary": _("Find the right contact"),
                        "note": note_for_rep + (
                            "\n\nContact hint: %s" % new_contact_hint if new_contact_hint else ""
                        ),
                        "date_deadline": fields.Date.today(),
                    })

            elif intent == "referral":
                if new_contact_hint:
                    lead.message_post(
                        body=_("Referred to: %s", new_contact_hint),
                        subtype_xmlid="mail.mt_note",
                    )
                if lead.user_id:
                    todo_type = self.env.ref(
                        "mail.mail_activity_data_todo", raise_if_not_found=False
                    )
                    Activity.create({
                        'res_model_id': self.env.ref('crm.model_crm_lead').id,
                        "res_id": lead.id,
                        "user_id": lead.user_id.id,
                        "activity_type_id": todo_type.id if todo_type else False,
                        "summary": _("Follow up with referred contact"),
                        "note": note_for_rep + (
                            "\n\nReferred contact: %s" % new_contact_hint if new_contact_hint else ""
                        ),
                        "date_deadline": fields.Date.today(),
                    })

            elif intent == "unsubscribe":
                lead.x_unsubscribed = True
                tag = self.env["crm.tag"].sudo().search(
                    [("name", "=", "unsubscribed")], limit=1
                )
                if not tag:
                    tag = self.env["crm.tag"].sudo().create({"name": "unsubscribed"})
                lead.tag_ids = [(4, tag.id)]

            # n8n reply event notification (all intents)
            try:
                self._n8n().post("reply_event_notification", {
                    "lead_id": lead.id,
                    "lead_name": lead.name,
                    "company": lead.partner_name or "",
                    "intent": intent,
                    "confidence": confidence,
                    "note_for_rep": note_for_rep,
                    "rep_name": lead.user_id.name if lead.user_id else "",
                    "rep_email": lead.user_id.email if lead.user_id else "",
                    "priority": priority,
                })
            except Exception:
                _logger.error(
                    "sales_ai: n8n reply_event notification failed for lead %s",
                    lead.id, exc_info=True,
                )

            # Discussion sync for presale: finance-free summary note posted to lead
            if lead.x_presale_status not in ("none", False):
                try:
                    sync_payload = service.call(
                        tier="sonnet",
                        system_prompt=prompts.PROMPTS["discussion_sync_system"],
                        user_message=body_text[:4000],
                        max_tokens=600,
                        expect_json=True,
                    )
                    if isinstance(sync_payload, dict) and sync_payload.get("has_content"):
                        summary_html = sync_payload.get("summary_html") or ""
                        if summary_html:
                            lead.message_post(
                                body=_("<b>Presale note (auto-synced from %s)</b><br/>%s",
                                       lead.x_presale_ref or "presale", summary_html),
                                subtype_xmlid="mail.mt_note",
                            )
                except Exception:
                    _logger.error(
                        "sales_ai: Discussion sync failed for lead %s", lead.id, exc_info=True
                    )

    # =========================================================================
    # PHASE: OPEN PRESALE (no separate project.task — everything on the lead)
    # =========================================================================

    def action_open_presale(self):
        """
        Open the presale phase on this lead.
        Assigns a PST reference number and triggers the TicketGistAgent.
        All presale work (agenda, MOM, WBS, proposal) stays on the lead record.
        """
        self.ensure_one()
        if self.x_presale_status != "none":
            raise UserError(
                _("Presale is already open for this lead (%s)." % self.x_presale_ref)
            )
        # Assign reference number
        self.x_presale_ref = "PST-%d" % self.id
        self.x_presale_status = "open"
        self.action_start_presale()
        _logger.info("sales_ai: Presale opened for lead %s — ref %s", self.id, self.x_presale_ref)

    # =========================================================================
    # PHASE: NO-SHOW FOLLOW-UP
    # =========================================================================

    def action_no_show_followup(self, no_show_count=1):
        """Generate a no-show follow-up email draft when client misses a meeting."""
        self.ensure_one()
        calendar_link = self.user_id.x_calendar_link if self.user_id else "[CALENDAR_LINK]"

        payload = {
            "client_name": self.contact_name or (self.partner_id.name if self.partner_id else ""),
            "client_company": self.partner_id.name if self.partner_id else "",
            "meeting_date": str(fields.Date.today()),
            "meeting_topic": self.name or "",
            "rep_name": self.user_id.name if self.user_id else "",
            "rep_designation": self.user_id.job_title if self.user_id else "Account Executive",
            "rep_calendar_link": calendar_link,
            "lead_score_band": self.x_lead_score_band or "warm",
            "no_show_count": no_show_count,
            "prior_interaction": "Previous emails and meeting scheduled",
            "enriched_fields": {
                "company_industry": self.x_industry or "",
                "contact_seniority": self.x_contact_seniority_structured or "",
            },
        }

        try:
            resp = self._claude().call(
                tier="sonnet",
                system_prompt=prompts.PROMPTS["no_show_followup_system"],
                user_message=json.dumps(payload, ensure_ascii=False),
                max_tokens=400,
                expect_json=True,
            )
        except Exception:
            _logger.error("sales_ai: No-show follow-up failed for lead %s", self.id, exc_info=True)
            return

        subject = resp.get("subject") or _("Following up — our calendars didn't align")
        body = resp.get("body") or ""

        activity_type = self.env.ref(
            "sales_ai_integration.activity_type_no_show_followup", raise_if_not_found=False
        ) or self.env.ref("mail.mail_activity_data_email", raise_if_not_found=False)

        self.env["mail.activity"].sudo().create({
            'res_model_id': self.env.ref('crm.model_crm_lead').id,
            "res_id": self.id,
            "user_id": self.user_id.id if self.user_id else self.env.uid,
            "activity_type_id": activity_type.id if activity_type else False,
            "summary": _("Review & send no-show follow-up"),
            "note": "[AI DRAFT — No-show follow-up]\n\nSubject: %s\n\n%s" % (subject, body),
            "date_deadline": fields.Date.today(),
        })
        _logger.info("sales_ai: No-show follow-up draft created for lead %s", self.id)

    # =========================================================================
    # PHASE: MEETING PREP BRIEF (cron before meetings)
    # =========================================================================

    @api.model
    def cron_meeting_prep_brief(self):
        """
        Daily 8:00 AM cron: generate meeting prep briefs for meetings
        scheduled in the next 24 hours.
        """
        _logger.info("sales_ai: [CRON] Meeting prep brief started")
        from datetime import timedelta
        now = fields.Datetime.now()
        cutoff = now + timedelta(hours=24)

        # Find meetings with linked leads
        events = self.env["calendar.event"].sudo().search([
            ("start", ">=", now),
            ("start", "<=", cutoff),
            ("opportunity_id", "!=", False),
        ])
        _logger.info("sales_ai: [CRON] Found %d upcoming meetings with linked leads", len(events))

        for event in events:
            lead = event.opportunity_id
            if not lead or not lead.user_id:
                continue
            try:
                lead._generate_meeting_prep_brief(event)
            except Exception:
                _logger.error(
                    "sales_ai: Meeting prep brief failed for lead %s event %s",
                    lead.id, event.id, exc_info=True,
                )

        _logger.info("sales_ai: [CRON] Meeting prep brief completed")

    def _generate_meeting_prep_brief(self, event=None):
        """Generate a 2-minute pre-meeting brief and post to lead."""
        self.ensure_one()

        # Gather last 5 emails
        emails = []
        for m in self.message_ids.sorted("date", reverse=True)[:10]:
            if m.message_type == "email":
                emails.append({
                    "subject": m.subject or "",
                    "snippet": (m.body or "")[:300],
                    "date": str(m.date),
                })
            if len(emails) >= 5:
                break

        # Prior MOMs
        prior_moms = []
        for m in self.message_ids.filtered(lambda x: "Meeting Minutes" in (x.body or "")):
            prior_moms.append((m.body or "")[:500])

        payload = {
            "client_name": self.contact_name or (self.partner_id.name if self.partner_id else ""),
            "client_company": self.partner_id.name if self.partner_id else "",
            "client_role": self.function or self.x_contact_job_title or "",
            "meeting_type": "follow-up",
            "meeting_duration": int((event.stop - event.start).total_seconds() / 60) if event and event.start and event.stop else 60,
            "meeting_agenda": event.description or event.name or "" if event else "",
            "enriched_fields": {
                "company_industry": self.x_industry or "",
                "company_size": self.x_employee_count_range or "",
                "contact_seniority": self.x_contact_seniority_structured or "",
                "likely_pain_point": self.x_likely_pain_point or "",
            },
            "email_thread": emails,
            "lead_score": self.x_lead_score or 0,
            "rep_name": self.user_id.name if self.user_id else "",
            "prior_moms": prior_moms[-3:],
            "open_questions": [],
        }

        try:
            resp = self._claude().call(
                tier="sonnet",
                system_prompt=prompts.PROMPTS["meeting_prep_brief_system"],
                user_message=json.dumps(payload, ensure_ascii=False),
                max_tokens=600,
                expect_json=False,
            )
        except Exception:
            _logger.error("sales_ai: Meeting prep brief failed for lead %s", self.id, exc_info=True)
            return

        if resp:
            self.message_post(
                body=_("<h4>Meeting Prep Brief</h4>%s", resp),
                subtype_xmlid="mail.mt_note",
            )
            _logger.info("sales_ai: Meeting prep brief posted for lead %s", self.id)

    # =========================================================================
    # PHASE: PRESALE MOM FROM TRANSCRIPT (webhook target)
    # =========================================================================

    def action_generate_presale_mom_from_transcript(self, transcript: str, meeting_date=None,
                                                      meeting_duration=None, attendees=None,
                                                      prior_open_items=None):
        """
        PresaleMOMAgent (Sonnet) — generate internal presale MOM from transcript.
        Everything posted to the lead chatter. No project.task involved.
        """
        self.ensure_one()
        _logger.info(
            "sales_ai: Generating presale MOM for lead %s — ref %s (transcript=%d chars)",
            self.id, self.x_presale_ref or "no-ref", len(transcript),
        )

        # Build context from lead
        ticket_context = self.x_ticket_gist or self.x_likely_pain_point or self.description or ""

        # Prior open items from last few internal notes
        prior_items = prior_open_items or []
        if not prior_items:
            recent_notes = self.message_ids.filtered(
                lambda m: m.subtype_id and m.subtype_id.xml_id == "mail.mt_note"
            ).sorted("date", reverse=True)[:5]
            prior_items = [(m.body or "")[:300] for m in recent_notes]

        payload = {
            "lead_id": self.id,
            "ticket_id": self.x_presale_ref or ("PST-%d" % self.id),
            "transcript": transcript[:150000],
            "meeting_date": meeting_date or str(fields.Date.today()),
            "meeting_duration": meeting_duration or 60,
            "attendees": attendees or [],
            "ticket_context": ticket_context[:2000],
            "prior_open_items": prior_items,
            "presale_stage": self.x_presale_status or "open",
        }

        try:
            resp = self._claude().call(
                tier="sonnet",
                system_prompt=prompts.PROMPTS["presale_mom_system"],
                user_message=json.dumps(payload, ensure_ascii=False),
                max_tokens=3000,
                expect_json=True,
            )
        except Exception:
            _logger.error("sales_ai: Presale MOM generation failed for lead %s", self.id, exc_info=True)
            return

        mom_md = resp.get("internal_mom_markdown") or resp.get("internal_mom") or str(resp)
        technical_decisions = resp.get("technical_decisions") or []
        stage_rec = resp.get("stage_recommendation") or ""

        # Store MOM in history
        try:
            history = json.loads(self.x_presale_mom_history or "[]")
        except Exception:
            history = []
        history.append({
            "date": meeting_date or str(fields.Date.today()),
            "mom": mom_md[:3000],
            "decisions": technical_decisions,
        })
        self.x_presale_mom_history = json.dumps(history, ensure_ascii=False)

        # Post internal MOM to lead chatter
        self.message_post(
            body="<pre>%s</pre>" % mom_md,
            subtype_xmlid="mail.mt_note",
        )

        # Post action items summary
        us_items = resp.get("new_action_items_us") or []
        client_items = resp.get("new_action_items_client") or []
        if us_items or client_items or stage_rec:
            parts = ["<b>Presale MOM Action Items [%s]</b><ul>" % (self.x_presale_ref or "")]
            for item in us_items:
                parts.append("<li><b>[Our Team]</b> %s</li>" % item)
            for item in client_items:
                parts.append("<li><b>[Client]</b> %s</li>" % item)
            parts.append("</ul>")
            if stage_rec:
                parts.append("<p><b>Stage recommendation:</b> %s</p>" % stage_rec)
            self.message_post(body="\n".join(parts), subtype_xmlid="mail.mt_note")

        _logger.info(
            "sales_ai: Presale MOM posted on lead %s — %d technical decisions",
            self.id, len(technical_decisions),
        )

        # Auto-trigger client-facing presale email draft
        self.action_generate_presale_client_email(mom_content=mom_md)

    # =========================================================================
    # PHASE: WBS GENERATION (button on lead)
    # =========================================================================

    def action_generate_wbs(self):
        """
        WBSGeneratorAgent (Sonnet) — generate a full WBS directly on the lead.
        Stores JSON in x_wbs_json, posts readable summary to chatter,
        then sends to n8n for Google Sheets write-back.
        """
        self.ensure_one()
        if self.x_presale_status not in ("open", "ready_for_wbs", "ready_for_proposal"):
            raise UserError(_("Lead must be in presale mode to generate WBS."))

        # Gather requirements from recent presale notes + MOM history
        requirements = []
        technical_decisions = []
        if self.x_presale_mom_history:
            try:
                for entry in json.loads(self.x_presale_mom_history):
                    for d in entry.get("decisions") or []:
                        technical_decisions.append(d)
            except Exception:
                pass

        recent_notes = self.message_ids.filtered(
            lambda m: m.subtype_id and m.subtype_id.xml_id == "mail.mt_note"
        ).sorted("date", reverse=False)[-20:]
        for note in recent_notes:
            body = (note.body or "").strip()
            if body and len(body) > 50:
                requirements.append(body[:500])

        if self.x_likely_pain_point:
            requirements.insert(0, self.x_likely_pain_point[:500])

        user_msg = json.dumps(
            {
                "lead_id": self.id,
                "ticket_id": self.x_presale_ref or ("PST-%d" % self.id),
                "client_company": self.partner_id.name or self.partner_name or "",
                "project_type": self.x_inquiry_category or "new-implementation",
                "requirements": requirements or ["Requirements to be gathered from presale discussions"],
                "technical_decisions": technical_decisions,
                "client_existing_systems": [],
                "modules_in_scope": [],
                "integrations_in_scope": [],
                "constraints": {},
                "wbs_template_phases": [
                    "Phase 1: Discovery & Gap Analysis",
                    "Phase 2: System Design & Prototype",
                    "Phase 3: Core Development",
                    "Phase 4: Integrations",
                    "Phase 5: UAT & Training",
                    "Phase 6: Go-Live & Hypercare",
                ],
            },
            ensure_ascii=False,
        )

        try:
            wbs_result = self._claude().call(
                tier="sonnet",
                system_prompt=prompts.PROMPTS["wbs_system"],
                user_message=user_msg,
                max_tokens=4000,
                expect_json=True,
            )
        except Exception:
            _logger.error("sales_ai: WBS generation failed for lead %s", self.id, exc_info=True)
            raise UserError(_("WBS generation failed. Please try again."))

        if not isinstance(wbs_result, dict):
            raise UserError(_("WBS Agent returned an unexpected response. Please retry."))

        # Store JSON on lead
        self.x_wbs_json = json.dumps(wbs_result, ensure_ascii=False, indent=2)
        self.x_presale_status = "ready_for_wbs"

        # Build readable HTML summary
        phases = wbs_result.get("wbs_phases") or []
        total_tasks = wbs_result.get("total_tasks") or sum(len(p.get("tasks", [])) for p in phases)
        html_parts = [
            "<h3>[%s] WBS Generated — %d phases, %d tasks</h3>" % (
                self.x_presale_ref or ("PST-%d" % self.id), len(phases), total_tasks
            )
        ]
        for phase in phases:
            html_parts.append("<h4>%s</h4><ul>" % phase.get("phase_name", ""))
            for task in phase.get("tasks", []):
                html_parts.append(
                    "<li><b>[%s]</b> %s — Owner: %s — Deliverable: %s</li>" % (
                        task.get("task_id", ""),
                        task.get("task_name", ""),
                        task.get("owner", ""),
                        task.get("deliverable", ""),
                    )
                )
            html_parts.append("</ul>")

        assumptions = wbs_result.get("assumptions") or []
        if assumptions:
            html_parts.append("<h4>Assumptions</h4><ul>")
            html_parts.extend("<li>%s</li>" % a for a in assumptions)
            html_parts.append("</ul>")

        risks = wbs_result.get("risks") or []
        if risks:
            html_parts.append("<h4>Risks</h4><ul>")
            html_parts.extend("<li>%s</li>" % r for r in risks)
            html_parts.append("</ul>")

        self.message_post(body="\n".join(html_parts), subtype_xmlid="mail.mt_note")
        _logger.info(
            "sales_ai: WBS generated for lead %s — %d phases, %d tasks",
            self.id, len(phases), total_tasks,
        )

        # Send to n8n to write to Google Sheets
        try:
            wbs_summary = [
                {"phase_name": p.get("phase_name", ""), "task_count": len(p.get("tasks", []))}
                for p in phases
            ]
            self._n8n().post(
                "wbs_generated",
                {
                    "lead_id": self.id,
                    "presale_ref": self.x_presale_ref or ("PST-%d" % self.id),
                    "wbs_json": wbs_result,
                    "wbs_summary": wbs_summary,
                },
            )
        except Exception:
            _logger.warning(
                "sales_ai: WBS n8n notification failed for lead %s (WBS saved locally)", self.id,
                exc_info=True,
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("WBS Generated"),
                "type": "success",
                "message": _(
                    "WBS created — %d phases, %d tasks. Review and validate before requesting proposal."
                ) % (len(phases), total_tasks),
            },
        }
