from odoo import api, fields, models, _


class IcpCriteriaWizard(models.TransientModel):
    _name = "sales.ai.icp.criteria.wizard"
    _description = "ICP Criteria Editor"

    icp_json = fields.Text(
        string="ICP Criteria (JSON)",
        help="Edit the Ideal Customer Profile JSON used by AI lead scoring.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        icp_raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("sales_ai.icp_criteria_json", default="{}")
        )
        res.setdefault("icp_json", icp_raw)
        return res

    def action_save(self):
        self.ensure_one()
        self.env["ir.config_parameter"].sudo().set_param(
            "sales_ai.icp_criteria_json", self.icp_json or "{}"
        )
        return {"type": "ir.actions.act_window_close"}

