from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    x_calendar_link = fields.Char(
        string="Calendar Booking Link",
        help="Personal booking URL (e.g., Calendly) to include in AI-generated emails.",
    )

