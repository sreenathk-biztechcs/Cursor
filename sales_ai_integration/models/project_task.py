"""
project_task.py — minimal stub.

All presale workflow (gist, agenda, MOM, WBS, proposal) lives on crm.lead.
This file exists only to preserve any existing x_linked_lead_id references
on project.task records that may have been created before the switch.
"""
import logging
from odoo import fields, models

_logger = logging.getLogger("sales_ai")


class ProjectTask(models.Model):
    _inherit = "project.task"

    # Read-only link to CRM lead — kept for backward compatibility only.
    # New presale work is managed entirely on crm.lead.
    x_linked_lead_id = fields.Many2one(
        "crm.lead",
        string="Linked Lead (legacy)",
        help="Legacy field — presale workflow is now on the CRM lead directly.",
        readonly=True,
    )
