# -*- coding: utf-8 -*-
from odoo import models, fields


class ServerMonitoringAlert(models.Model):
    _name = 'server.monitoring.alert'
    _description = 'Server Alert'
    _inherit = ['mail.thread']
    _order = 'started_at desc'

    server_id = fields.Many2one(
        'server.monitoring.server', string='Server', index=True, tracking=True)
    alert_name = fields.Char(string='Alert Name', required=True)
    severity = fields.Selection([
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ], string='Severity', default='warning', tracking=True)
    state = fields.Selection([
        ('firing', 'Firing'),
        ('resolved', 'Resolved'),
        ('acknowledged', 'Acknowledged'),
    ], string='State', default='firing', tracking=True)
    description = fields.Text(string='Description')
    started_at = fields.Datetime(string='Started At', index=True)
    resolved_at = fields.Datetime(string='Resolved At')
    acknowledged_by = fields.Many2one('res.users', string='Acknowledged By')
    acknowledged_at = fields.Datetime(string='Acknowledged At')
    ai_analysis = fields.Text(string='AI Analysis')
    ai_action_taken = fields.Text(string='AI Recommended Action')
    raw_payload = fields.Text(string='Raw Alert Payload (JSON)')

    def action_acknowledge(self):
        self.write({
            'state': 'acknowledged',
            'acknowledged_by': self.env.user.id,
            'acknowledged_at': fields.Datetime.now(),
        })
