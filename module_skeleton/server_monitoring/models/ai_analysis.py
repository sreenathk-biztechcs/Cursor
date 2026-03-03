# -*- coding: utf-8 -*-
from odoo import models, fields


class ServerMonitoringAIAnalysis(models.Model):
    _name = 'server.monitoring.ai.analysis'
    _description = 'AI Analysis Log'
    _order = 'create_date desc'

    server_id = fields.Many2one('server.monitoring.server', string='Server', index=True)
    analysis_type = fields.Selection([
        ('health_check', 'Health Check'),
        ('anomaly', 'Anomaly Detection'),
        ('prediction', 'Capacity Prediction'),
        ('recommendation', 'Recommendation'),
        ('fleet_overview', 'Fleet Overview'),
        ('alert_analysis', 'Alert Analysis'),
    ], string='Analysis Type', required=True)
    trigger = fields.Selection([
        ('scheduled', 'Scheduled (Cron)'),
        ('alert', 'Alert Triggered'),
        ('manual', 'Manual'),
        ('threshold', 'Threshold Breach'),
    ], string='Trigger', default='scheduled')
    input_data = fields.Text(string='Input Data (JSON)')
    ai_response = fields.Text(string='AI Response (JSON)')
    summary = fields.Char(string='Summary')
    risk_score = fields.Float(string='Risk Score (0-100)')
    recommendations = fields.Text(string='Recommendations')
    model_used = fields.Char(string='AI Model Used')
    tokens_used = fields.Integer(string='Tokens Used')
    cost = fields.Float(string='Estimated Cost ($)')
