# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


ALLOCATION_STATES = [
    ('draft', 'Draft'),
    ('submitted', 'Submitted'),
    ('approved', 'Approved'),
    ('allocated', 'Allocated'),
    ('rejected', 'Rejected'),
    ('returned', 'Returned'),
]


class ServerMonitoringAllocation(models.Model):
    _name = 'server.monitoring.allocation'
    _description = 'Server Allocation Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Reference', required=True, copy=False,
                       readonly=True, default=lambda self: _('New'))
    server_id = fields.Many2one('server.monitoring.server', string='Server', tracking=True)
    requester_id = fields.Many2one(
        'res.users', string='Requester', required=True,
        default=lambda self: self.env.user, tracking=True)
    approver_id = fields.Many2one('res.users', string='Approver', tracking=True)
    department_id = fields.Many2one('hr.department', string='Department', tracking=True)
    purpose = fields.Text(string='Purpose', required=True)
    specs_required = fields.Text(string='Required Specifications',
                                 help='Describe the required CPU, RAM, disk, OS, etc.')
    duration = fields.Selection([
        ('temporary', 'Temporary'),
        ('permanent', 'Permanent'),
    ], string='Duration', default='permanent')
    end_date = fields.Date(string='Expected End Date')
    state = fields.Selection(ALLOCATION_STATES, string='Status', default='draft', tracking=True)
    date_submitted = fields.Datetime(string='Submitted On')
    date_approved = fields.Datetime(string='Approved On')
    date_allocated = fields.Datetime(string='Allocated On')
    date_returned = fields.Datetime(string='Returned On')
    notes = fields.Text(string='Notes')
    ai_recommendation = fields.Text(string='AI Recommendation',
                                    help='AI-suggested server match based on requirements and available resources')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'server.monitoring.allocation') or _('New')
        return super().create(vals_list)

    def action_submit(self):
        self.write({
            'state': 'submitted',
            'date_submitted': fields.Datetime.now(),
        })
        self._trigger_ai_recommendation()

    def action_approve(self):
        self.write({
            'state': 'approved',
            'approver_id': self.env.user.id,
            'date_approved': fields.Datetime.now(),
        })

    def action_allocate(self):
        for rec in self:
            if not rec.server_id:
                raise UserError(_('Please select a server before allocating.'))
        self.write({
            'state': 'allocated',
            'date_allocated': fields.Datetime.now(),
        })
        for rec in self:
            rec.server_id.write({
                'owner_id': rec.requester_id.id,
                'department_id': rec.department_id.id,
                'purpose': rec.purpose,
            })

    def action_reject(self):
        self.write({'state': 'rejected'})

    def action_return(self):
        self.write({
            'state': 'returned',
            'date_returned': fields.Datetime.now(),
        })

    def _trigger_ai_recommendation(self):
        """Ask AI to suggest the best server for this allocation request."""
        from ..services.ai_service import AIService
        config = self.env['server.monitoring.config'].sudo().get_config()
        if not config or not config.ai_api_key:
            return

        ai = AIService(
            api_key=config.ai_api_key,
            model=config.ai_model or 'gpt-4o-mini',
            base_url=config.ai_base_url or None,
        )

        idle_servers = self.env['server.monitoring.server'].search([
            ('state', '=', 'active'),
            ('is_idle', '=', True),
        ])

        context = {
            'request': {
                'purpose': self.purpose,
                'specs_required': self.specs_required,
                'duration': self.duration,
                'department': self.department_id.name,
            },
            'available_idle_servers': [{
                'id': s.id,
                'name': s.name,
                'cpu_cores': s.cpu_cores,
                'ram_gb': s.ram_total_gb,
                'disk_gb': s.disk_total_gb,
                'os': s.os_type,
                'current_cpu': s.cpu_usage_percent,
                'current_ram': s.ram_usage_percent,
                'cost_per_month': s.cost_per_month,
            } for s in idle_servers],
        }

        try:
            recommendation = ai.recommend_server(context)
            self.write({'ai_recommendation': recommendation})
        except Exception:
            pass
