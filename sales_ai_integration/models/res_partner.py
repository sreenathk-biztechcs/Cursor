from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Contact-level enrichment fields mirroring crm.lead
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
    x_contact_job_title = fields.Char("Contact Job Title")
    x_contact_decision_authority = fields.Selection(
        [("yes", "Yes"), ("no", "No"), ("unknown", "Unknown")],
        string="Decision-making Authority",
    )
    x_is_decision_maker = fields.Boolean("Is Decision Maker?")
    x_direct_email = fields.Char("Direct Email")
    x_direct_phone = fields.Char("Direct Phone")
    x_contact_linkedin_url = fields.Char("Contact LinkedIn URL")
    x_contact_score = fields.Integer("Contact Score (0-100)")
    x_intent_score = fields.Integer("Intent Score (0-100)")

    # Company / org-level enrichment
    x_industry = fields.Char("Industry")
    x_sub_industry = fields.Char("Sub-industry")
    x_employee_count_range = fields.Char("Employee Count Range")
    x_employee_count = fields.Integer("Employee Count")
    x_annual_revenue_range = fields.Char("Annual Revenue Range")
    x_annual_revenue = fields.Float("Annual Revenue")
    x_is_it_company = fields.Boolean("Is IT Company?")
    x_funding_stage = fields.Char("Funding Stage")
    x_company_linkedin_url = fields.Char("Company LinkedIn URL")
    x_hq_country_id = fields.Many2one("res.country", string="HQ Country")
    x_hq_city = fields.Char("HQ City")
    x_founded_year = fields.Integer("Founded Year")
    x_website = fields.Char("Website")

    # AI / ICP signals
    x_likely_pain_point = fields.Text("Likely Pain Point")
    x_similar_companies_won = fields.Text("Similar Companies We've Won")
    x_icp_match_signals = fields.Text("ICP Match Signals (JSON/List)")
    x_icp_disqualify_signals = fields.Text("ICP Disqualifying Signals (JSON/List)")
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
    x_lead_language = fields.Char("Lead Language")
    x_enrichment_conf = fields.Float("Enrichment Confidence (0-100)")
    x_enrichment_source = fields.Char("Enrichment Source")
    x_enrichment_date = fields.Datetime("Enrichment Date")

    # Key Fit Signals at contact/company level
    x_fit_industry = fields.Char("Fit Industry")
    x_fit_company_size = fields.Char("Fit Company Size")
    x_fit_revenue_range = fields.Char("Fit Revenue Range")
    x_fit_geography = fields.Char("Fit Geography")
    x_fit_contact_seniority = fields.Char("Fit Contact Seniority")
    x_fit_decision_authority = fields.Char("Fit Decision Authority")
    x_fit_urgency = fields.Char("Fit Urgency")

