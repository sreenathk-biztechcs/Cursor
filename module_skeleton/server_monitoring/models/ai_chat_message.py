# -*- coding: utf-8 -*-
from odoo import models, fields


class ServerMonitoringAIChat(models.Model):
    _name = 'server.monitoring.ai.chat'
    _description = 'AI Chat Message'
    _order = 'timestamp asc'

    user_id = fields.Many2one('res.users', string='User', index=True)
    session_id = fields.Char(string='Session ID', index=True)
    role = fields.Selection([
        ('user', 'User'),
        ('assistant', 'AI Assistant'),
        ('system', 'System'),
    ], string='Role', required=True)
    message = fields.Text(string='Message', required=True)
    context_server_ids = fields.Many2many(
        'server.monitoring.server', string='Referenced Servers')
    model_used = fields.Char(string='AI Model')
    tokens_used = fields.Integer(string='Tokens Used')
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)
