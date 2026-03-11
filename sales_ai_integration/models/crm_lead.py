import base64
import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from . import prompts

_logger = logging.getLogger("sales_ai")  # unified logger prefix


class CrmLead(models.Model):
    _inherit = "crm.lead"

    # -------------------------------------------------------------------------
    # Custom fields – Lead qualification & enrichment
    # -------------------------------------------------------------------------

    x_lead_quality = fields.Selection(
        [("genuine", "Genuine"), ("marketing", "Marketing"), ("junk", "Junk")],
        string="Lead Quality",
        tracking=True,
    )
    x_lead_score = fields.Integer("Lead Score (0-100)", tracking=True)
    x_lead_score_band = fields.Selection(
        [("hot", "Hot"), ("warm", "Warm"), ("cold", "Cold")],
        string="Lead Score Band",
        tracking=True,
    )
    x_followup_stage = fields.Integer("Follow-up Stage", default=0, tracking=True)
    x_last_reply_date = fields.Datetime("Last Reply Date", tracking=True)
    x_reply_intent = fields.Selection(
        [
            ("interested", "Interested"),
            ("not_interested", "Not Interested"),
            ("ooo", "Out of Office"),
            ("referral", "Referral"),
        ],
        string="Reply Intent",
        tracking=True,
    )

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

    # Backward compat: optional link to project.task if team uses tickets
    x_presale_ticket_id = fields.Many2one(
        "project.task", string="Presale Ticket (optional)",
        help="Optional link to a project task if the team uses tickets alongside lead-based presale.",
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
        """Move forward `days` business days from base_date."""
        date = base_date
        added = 0
        while added < days:
            date += relativedelta(days=1)
            if date.weekday() < 5:
                added += 1
        return date

    def _claude(self):
        return self.env["claude.service"]

    def _n8n(self):
        return self.env["sales.ai.n8n"]

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

    def action_trigger_lead_intake(self):
        """
        Send lead data to n8n for Apollo enrichment + classification.
        Called by automation rule on lead creation.
        """
        for lead in self:
            email = lead.email_from or ""
            domain = email.split("@")[-1] if "@" in email else ""
            payload = {
                "lead_id": lead.id,
                "email": email,
                "name": lead.contact_name or lead.name or "",
                "company": lead.partner_id.name if lead.partner_id else "",
                "domain": domain,
                "phone": lead.phone or lead.mobile or "",
                "description": (lead.description or "")[:2000],
                "source": lead.source_id.display_name if lead.source_id else "",
            }
            _logger.info(
                "sales_ai: Lead intake triggered for lead %s (%s) → sending to n8n",
                lead.id, lead.name,
            )
            self._n8n().post("lead_intake", payload)

    def action_lead_intake_complete(self, apollo_person_data, apollo_org_data, apollo_match):
        """
        Unified callback from n8n after Apollo API lookup.

        :param apollo_person_data: dict from Apollo People Enrichment API (or {})
        :param apollo_org_data: dict from Apollo Organization Enrichment API (or {})
        :param apollo_match: bool — True if Apollo found a match
        """
        self.ensure_one()
        _logger.info(
            "sales_ai: Lead intake complete for lead %s — Apollo match: %s",
            self.id, apollo_match,
        )

        # Store raw data
        raw_combined = {
            "person": apollo_person_data or {},
            "organization": apollo_org_data or {},
        }
        self.x_apollo_data_raw = json.dumps(raw_combined, ensure_ascii=False)
        self.x_apollo_match = bool(apollo_match)

        # Step 1: Enrich fields from Apollo data (if match found)
        if apollo_match and (apollo_person_data or apollo_org_data):
            self._enrich_from_apollo(apollo_person_data or {}, apollo_org_data or {})

        # Step 2: Classify (genuine / marketing / junk)
        self._classify_lead_quality(apollo_match)

        # Step 3: If genuine → score → follow-ups happen after scoring
        if self.x_lead_quality == "genuine":
            self.action_run_lead_scoring()

    def _enrich_from_apollo(self, person: dict, org: dict):
        """Map Apollo API response fields to lead custom fields."""
        vals = {}

        # Person enrichment (from POST /api/v1/people/match)
        if person:
            vals["x_linkedin_url"] = person.get("linkedin_url") or self.x_linkedin_url
            vals["x_seniority"] = self._map_apollo_seniority(person.get("seniority"))
            vals["x_is_decision_maker"] = person.get("seniority") in (
                "c_suite", "vp", "director", "owner", "founder"
            )

            # Contact/intent scores from Apollo
            p_org = person.get("organization") or {}
            if p_org.get("estimated_num_employees"):
                vals["x_employee_count"] = p_org["estimated_num_employees"]

        # Organization enrichment (from GET /api/v1/organizations/enrich)
        if org:
            if org.get("estimated_num_employees"):
                vals["x_employee_count"] = org["estimated_num_employees"]
            if org.get("annual_revenue"):
                vals["x_annual_revenue"] = org["annual_revenue"]
            if org.get("current_technologies"):
                tech_names = [t.get("name", "") for t in (org["current_technologies"] or []) if t.get("name")]
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

    def _classify_lead_quality(self, has_apollo_data: bool):
        """
        Classify lead as genuine / marketing / junk.

        If Apollo had data → use enriched fields + email content for classification.
        If no Apollo data → classify from email content only (more conservative).
        """
        settings = self.env["ir.config_parameter"].sudo()
        marketing_user_id = int(
            settings.get_param("sales_ai.marketing_user_id", default="0") or 0
        )

        payload = {
            "name": self.name,
            "email_from": self.email_from,
            "description": (self.description or "")[:2000],
            "source": self.source_id.display_name if self.source_id else None,
            "apollo_match": has_apollo_data,
        }

        # Include enrichment data if available
        if has_apollo_data:
            payload.update({
                "employee_count": self.x_employee_count,
                "is_it_company": self.x_is_it_company,
                "seniority": self.x_seniority,
                "is_decision_maker": self.x_is_decision_maker,
                "linkedin_url": self.x_linkedin_url,
                "tech_stack": self.x_tech_stack,
            })

        try:
            text = self._claude().call(
                tier="haiku",
                system_prompt=prompts.PROMPTS["junk_filter_system"],
                user_message=json.dumps(payload, ensure_ascii=False),
                max_tokens=16,
                expect_json=False,
            )
        except Exception:
            _logger.warning(
                "sales_ai: Junk filter failed for lead %s; defaulting to genuine",
                self.id,
                exc_info=True,
            )
            quality = "genuine"
            self.x_lead_quality = quality
            return

        quality = "genuine"
        if text:
            upper = text.strip().upper()
            if "MARKETING" in upper:
                quality = "marketing"
            elif "JUNK" in upper:
                quality = "junk"
            elif "GENUINE" in upper:
                quality = "genuine"

        self.x_lead_quality = quality
        _logger.info(
            "sales_ai: Lead %s classified as %s (Apollo match: %s)",
            self.id, quality, has_apollo_data,
        )

        if quality in ("marketing", "junk") and marketing_user_id:
            self.user_id = self.env["res.users"].browse(marketing_user_id)
            self.message_post(
                body=_("Classified as <b>%s</b> by AI (Apollo match: %s); routed to Marketing User.",
                       quality, "Yes" if has_apollo_data else "No"),
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
        ICP = self.env["ir.config_parameter"].sudo()
        icp_json = ICP.get_param("sales_ai.icp_criteria_json", default="{}")
        try:
            icp = json.loads(icp_json)
        except Exception:
            icp = {}

        for lead in self.filtered(lambda l: not l.x_scoring_done):
            if not icp:
                lead.x_lead_score = 50
                lead.x_lead_score_band = "warm"
                lead.x_scoring_done = True
                _logger.info(
                    "sales_ai: Lead %s scored 50 (warm) — no ICP criteria configured",
                    lead.id,
                )
                continue

            payload = {
                "name": lead.name,
                "company": lead.partner_id.name if lead.partner_id else None,
                "email_from": lead.email_from,
                "industry": getattr(lead.partner_id, "industry_id", False)
                and lead.partner_id.industry_id.name,
                "employee_count": lead.x_employee_count,
                "annual_revenue": lead.x_annual_revenue,
                "is_it_company": lead.x_is_it_company,
                "seniority": lead.x_seniority,
                "is_decision_maker": lead.x_is_decision_maker,
                "tech_stack": lead.x_tech_stack,
                "intent_score": lead.x_intent_score,
                "apollo_match": lead.x_apollo_match,
            }
            try:
                result = self._claude().call(
                    tier="haiku",
                    system_prompt=prompts.PROMPTS["lead_scoring_system"],
                    user_message=json.dumps(
                        {"icp": icp, "lead": payload}, ensure_ascii=False
                    ),
                    max_tokens=512,
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
            if band not in ("hot", "warm", "cold"):
                band = "warm"

            lead.x_lead_score = max(0, min(100, score))
            lead.x_lead_score_band = band
            lead.x_scoring_done = True

            reasoning = result.get("reasoning") or ""
            _logger.info(
                "sales_ai: Lead %s scored %d (%s) — %s",
                lead.id,
                score,
                band,
                reasoning[:100],
            )
            if reasoning:
                lead.message_post(
                    body=_("AI lead scoring: <b>%d/100 (%s)</b><br/>%s", score, band, reasoning),
                    subtype_xmlid="mail.mt_note",
                )

            # If lead is already assigned but follow-ups were skipped
            # (because band was not set at assignment time), create them now.
            if lead.user_id:
                followup_type = self.env.ref(
                    "sales_ai_integration.activity_type_followup_email",
                    raise_if_not_found=False,
                )
                if followup_type:
                    existing = self.env["mail.activity"].sudo().search_count(
                        [
                            ("res_model", "=", "crm.lead"),
                            ("res_id", "=", lead.id),
                            ("activity_type_id", "=", followup_type.id),
                        ]
                    )
                    if not existing:
                        _logger.info(
                            "sales_ai: Creating follow-ups for lead %s after post-scoring",
                            lead.id,
                        )
                        lead.action_create_followup_activities()

    # =========================================================================
    # PHASE 3: AUTO-ACK EMAIL + FOLLOW-UP SCHEDULING
    # =========================================================================

    def action_send_auto_ack(self):
        """Send AI-generated acknowledgment email from the assigned rep."""
        for lead in self:
            if not lead.user_id or not lead.partner_id or not lead.partner_id.email:
                _logger.warning("sales_ai: Skipping auto-ack for lead %s — missing user/partner/email", lead.id)
                continue

            calendar_link = lead.user_id.x_calendar_link or "[CALENDAR_LINK]"
            context_data = {
                "company_name": lead.partner_id.name or "",
                "contact_name": lead.contact_name or lead.partner_id.name or "",
                "inquiry_description": lead.description or "",
                "industry": getattr(lead.partner_id, "industry_id", False)
                and lead.partner_id.industry_id.name
                or "",
                "calendar_link": calendar_link,
            }
            try:
                resp = self._claude().call(
                    tier="sonnet",
                    system_prompt=prompts.PROMPTS["auto_ack_system"],
                    user_message=json.dumps(context_data, ensure_ascii=False),
                    max_tokens=512,
                    expect_json=True,
                )
            except Exception:
                _logger.error("sales_ai: Auto-ack generation failed for lead %s", lead.id, exc_info=True)
                continue

            subject = resp.get("subject") or _("Thank you for your inquiry")
            body_html = resp.get("body_html") or _(
                "<p>Thank you for reaching out. We will get back to you shortly.</p>"
            )

            mail_values = {
                "subject": subject,
                "body_html": body_html,
                "email_from": lead.user_id.email_formatted,
                "email_to": lead.partner_id.email,
                "author_id": lead.user_id.partner_id.id,
                "auto_delete": False,
            }
            mail = self.env["mail.mail"].sudo().create(mail_values)
            mail.send()

            lead.message_post(
                body=_("Auto-ack email sent by AI.<br/><b>Subject:</b> %s", subject),
                subtype_xmlid="mail.mt_note",
            )
            _logger.info("sales_ai: Auto-ack email sent for lead %s to %s", lead.id, lead.partner_id.email)

    def action_create_followup_activities(self, base_date=None):
        """Create the 3 scheduled follow-ups based on x_lead_score_band."""
        Activity = self.env["mail.activity"].sudo()
        followup_type = self.env.ref(
            "sales_ai_integration.activity_type_followup_email", raise_if_not_found=False
        )

        for lead in self:
            if not lead.user_id or not lead.x_lead_score_band:
                _logger.warning(
                    "sales_ai: Skipping follow-up creation for lead %s — user: %s, band: %s",
                    lead.id, lead.user_id.id if lead.user_id else None, lead.x_lead_score_band,
                )
                continue

            if base_date is None:
                base_dt = fields.Datetime.context_timestamp(self, datetime.utcnow())
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
                        "res_model": "crm.lead",
                        "res_id": lead.id,
                        "user_id": lead.user_id.id,
                        "activity_type_id": followup_type.id if followup_type else False,
                        "date_deadline": deadline,
                        "note": "[AI-FOLLOWUP-PENDING] Draft will be generated before this date.",
                    }
                )
            lead.x_followup_stage = 1
            _logger.info(
                "sales_ai: Created 3 follow-up activities for lead %s (band=%s, gaps=%s)",
                lead.id, lead.x_lead_score_band, gaps,
            )

    # =========================================================================
    # PHASE 4: FOLLOW-UP EMAIL DRAFTER (9 AM CRON)
    # =========================================================================

    @api.model
    def cron_draft_followup_emails(self):
        """Daily 09:00 cron to draft follow-up emails for due/near-due activities."""
        _logger.info("sales_ai: [CRON] Follow-up email drafter started")
        Activity = self.env["mail.activity"].sudo()
        today = fields.Date.today()
        tomorrow = today + relativedelta(days=1)
        activities = Activity.search(
            [
                ("activity_type_id", "=", self.env.ref(
                    "sales_ai_integration.activity_type_followup_email"
                ).id),
                ("date_deadline", ">=", today),
                ("date_deadline", "<=", tomorrow),
                ("note", "=like", "[AI-FOLLOWUP-PENDING]%"),
            ]
        )
        _logger.info("sales_ai: [CRON] Found %d follow-up activities to draft", len(activities))

        drafted = 0
        for act in activities:
            try:
                lead = self.browse(act.res_id)
                if not lead.exists():
                    continue
                self._draft_single_followup_email(lead, act)
                drafted += 1
            except Exception:
                _logger.error("sales_ai: Failed drafting follow-up for activity %s", act.id, exc_info=True)

        _logger.info("sales_ai: [CRON] Follow-up drafter completed — %d/%d drafted", drafted, len(activities))

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
            _logger.error("sales_ai: Follow-up draft generation failed for lead %s", lead.id, exc_info=True)
            return

        subject = resp.get("subject") or _("Quick follow-up on your inquiry")
        body_html = resp.get("body_html") or _(
            "<p>Just circling back on our previous message.</p>"
        )

        activity.note = "[AI DRAFT — Review before sending]\n\n" + subject + "\n\n" + body_html
        _logger.info("sales_ai: Follow-up #%d draft created for lead %s", followup_no, lead.id)

    # =========================================================================
    # PHASE 5: PRESALE ON LEAD
    # =========================================================================

    def action_start_presale(self):
        """Move lead into presale mode and generate a discussion gist."""
        for lead in self:
            if lead.x_presale_status != "none":
                continue
            lead.x_presale_status = "open"

            # Generate discussion gist from all prior lead history
            msgs = lead.message_ids.sorted("date", reverse=False)[-50:]
            lines = []
            for m in msgs:
                if m.message_type not in ("email", "comment"):
                    continue
                snippet = (m.body or "").replace("\n", " ")
                lines.append(f"[{m.date}] {m.author_id.display_name or ''}: {snippet[:400]}")

            if not lines:
                lead.message_post(
                    body=_("Presale opened. No prior discussions found on the lead."),
                    subtype_xmlid="mail.mt_note",
                )
                _logger.info("sales_ai: Presale opened for lead %s (no history)", lead.id)
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

            lead.message_post(
                body=_("<h3>Presale Discussion Gist</h3>%s", summary or "No gist generated."),
                subtype_xmlid="mail.mt_note",
            )
            _logger.info("sales_ai: Presale gist generated for lead %s", lead.id)

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
                "res_model": "crm.lead",
                "res_id": self.id,
                "user_id": self.user_id.id,
                "activity_type_id": activity_type.id if activity_type else False,
                "note": "[AI DRAFT — Presale]\n\n" + subject + "\n\n" + body_html,
                "date_deadline": fields.Date.today(),
            }
        )
        _logger.info("sales_ai: Presale email draft activity created on lead %s", self.id)

    def action_request_proposal_from_ai(self):
        """Button action: Request AI-generated proposal via n8n."""
        self.ensure_one()
        if self.x_presale_status != "wbs_done":
            raise UserError(_("Complete WBS validation before requesting a proposal."))
        if not self.x_wbs_sheet_url:
            raise UserError(_("WBS Google Sheet URL is missing."))

        self.x_presale_status = "ready_for_proposal"
        payload = {
            "lead_id": self.id,
            "lead_name": self.name,
            "description": self.description or "",
            "wbs_sheet_url": self.x_wbs_sheet_url,
        }
        self._n8n().post("proposal_request", payload)
        _logger.info("sales_ai: Proposal requested for lead %s → sent to n8n", self.id)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Proposal Requested"),
                "type": "success",
                "message": _(
                    "AI proposal generation triggered. Google Drive link will appear on the lead."
                ),
            },
        }

    # =========================================================================
    # PHASE 6: CLIENT MOM GENERATION
    # =========================================================================

    def action_generate_client_mom(self, transcript: str):
        """Generate full MOM + client-safe draft email from transcript."""
        self.ensure_one()
        _logger.info("sales_ai: Generating client MOM for lead %s (transcript: %d chars)", self.id, len(transcript))
        try:
            resp = self._claude().call(
                tier="sonnet",
                system_prompt=prompts.PROMPTS["client_mom_system"],
                user_message=transcript[:150000],
                max_tokens=3000,
                expect_json=True,
            )
        except Exception:
            _logger.error("sales_ai: Client MOM generation failed for lead %s", self.id, exc_info=True)
            return

        full_mom = resp.get("full_mom_html") or "<p>No MOM generated.</p>"
        email_subject = resp.get("client_email_subject") or _("Summary of our recent call")
        email_body = resp.get("client_email_body_html") or "<p>Thank you for your time.</p>"

        # Log full MOM internally
        self.message_post(body=full_mom, subtype_xmlid="mail.mt_note")

        # Create review activity for rep
        activity_type = self.env.ref(
            "sales_ai_integration.activity_type_client_mom", raise_if_not_found=False
        )
        self.env["mail.activity"].sudo().create(
            {
                "res_model": "crm.lead",
                "res_id": self.id,
                "user_id": self.user_id.id,
                "activity_type_id": activity_type.id if activity_type else False,
                "note": "[AI DRAFT — Client MOM]\n\n" + email_subject + "\n\n" + email_body,
                "date_deadline": fields.Date.today(),
            }
        )
        _logger.info("sales_ai: Client MOM posted + review activity created for lead %s", self.id)

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
        res = super().write(vals)
        if going_lost:
            try:
                _logger.info("sales_ai: Triggering lost-lead retro for %d leads", len(going_lost))
                going_lost.with_context(active_test=False).action_generate_closure_retro()
            except Exception:
                _logger.error("sales_ai: Lost-lead retro failed", exc_info=True)
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

        if is_incoming_email:
            _logger.info("sales_ai: External reply detected on lead(s) %s", self.ids)
            self = self.with_context(_sales_ai_message_post_lock=True)
            self._handle_external_reply(body)

        return super().message_post(**kwargs)

    def _handle_external_reply(self, body_text: str):
        service = self.env["claude.service"]
        for lead in self:
            # Cancel pending follow-ups
            activities = self.env["mail.activity"].search(
                [
                    ("res_model", "=", "crm.lead"),
                    ("res_id", "=", lead.id),
                    (
                        "activity_type_id",
                        "=",
                        self.env.ref(
                            "sales_ai_integration.activity_type_followup_email"
                        ).id,
                    ),
                ]
            )
            if activities:
                _logger.info(
                    "sales_ai: Canceling %d pending follow-ups for lead %s (customer replied)",
                    len(activities), lead.id,
            )
            activities.unlink()
            lead.x_last_reply_date = fields.Datetime.now()

            if not body_text:
                continue

            # 1) Classify reply intent and adjust follow-ups
            try:
                label = service.call(
                    tier="haiku",
                    system_prompt=prompts.PROMPTS["reply_intent_system"],
                    user_message=body_text[:2000],
                    max_tokens=8,
                    expect_json=False,
            )
            except Exception:
                _logger.error("sales_ai: Reply intent classification failed for lead %s", lead.id, exc_info=True)
                continue

            intent = "interested"
            if label:
                upper = label.strip().upper()
                if "NOT_INTERESTED" in upper:
                    intent = "not_interested"
                elif "OOO" in upper:
                    intent = "ooo"
                elif "REFERRAL" in upper:
                    intent = "referral"
                elif "INTERESTED" in upper:
                    intent = "interested"

            lead.x_reply_intent = intent
            _logger.info("sales_ai: Lead %s reply intent classified as %s", lead.id, intent)

            if intent == "interested":
                base_dt = fields.Datetime.context_timestamp(self, datetime.utcnow())
                lead.action_create_followup_activities(base_date=base_dt)
            elif intent == "not_interested":
                lead.message_post(
                    body=_("Customer indicated they are not interested."),
                    subtype_xmlid="mail.mt_note",
                )
            elif intent == "ooo":
                Activity = self.env["mail.activity"].sudo()
                followup_type = self.env.ref(
                    "sales_ai_integration.activity_type_followup_email",
                    raise_if_not_found=False,
                )
                base_dt = fields.Datetime.context_timestamp(self, datetime.utcnow())
                deadline = lead._business_day_offset(base_dt, 7).date()
                Activity.create(
                    {
                        "res_model": "crm.lead",
                        "res_id": lead.id,
                        "user_id": lead.user_id.id,
                        "activity_type_id": followup_type.id if followup_type else False,
                        "date_deadline": deadline,
                        "note": "[AI-FOLLOWUP-PENDING] OOO follow-up.",
                    }
                )
                _logger.info("sales_ai: OOO follow-up scheduled for lead %s on %s", lead.id, deadline)

            # 2) Discussion sync for presale: create an internal, finance-free summary
            #    note based on this reply, so presale sees a clean MOM.
            try:
                sync_payload = service.call(
                    tier="sonnet",
                    system_prompt=prompts.PROMPTS["discussion_sync_system"],
                    user_message=body_text[:4000],
                    max_tokens=600,
                    expect_json=True,
                )
            except Exception:
                _logger.error(
                    "sales_ai: Discussion sync failed for lead %s", lead.id, exc_info=True
                )
                sync_payload = {}

            if isinstance(sync_payload, dict) and sync_payload.get("has_content"):
                summary_html = sync_payload.get("summary_html") or ""
                if summary_html:
                    if lead.x_presale_ticket_id:
                        # Legacy ticket-based presale: keep syncing there.
                        lead.x_presale_ticket_id.message_post(
                            body=summary_html,
                            subtype_xmlid="mail.mt_note",
                        )
                        _logger.info(
                            "sales_ai: Discussion sync posted to presale ticket %s for lead %s",
                            lead.x_presale_ticket_id.id,
                            lead.id,
                        )
                    else:
                        # Lead-based presale: log as internal presale note on the lead.
                        lead.message_post(
                            body=_("<b>Presale note (auto-synced)</b><br/>%s", summary_html),
                            subtype_xmlid="mail.mt_note",
                        )
                        _logger.info(
                            "sales_ai: Discussion sync posted as presale note on lead %s",
                            lead.id,
                        )
