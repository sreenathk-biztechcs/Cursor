# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ServerMonitoringConfig(models.Model):
    _name = 'server.monitoring.config'
    _description = 'Server Monitoring Configuration'

    name = fields.Char(default='Default Configuration', required=True)

    # Prometheus
    prometheus_url = fields.Char(string='Prometheus URL', default='http://localhost:9090')
    prometheus_username = fields.Char(string='Prometheus Username')
    prometheus_password = fields.Char(string='Prometheus Password')
    scrape_interval_min = fields.Integer(string='Metric Collection Interval (min)', default=5)
    snapshot_retention_days = fields.Integer(string='Snapshot Retention (days)', default=30)

    # Grafana (optional)
    grafana_url = fields.Char(string='Grafana URL')
    grafana_api_key = fields.Char(string='Grafana API Key')

    # AI configuration
    ai_provider = fields.Selection([
        ('openai', 'OpenAI'),
        ('ollama', 'Ollama (Local)'),
        ('azure', 'Azure OpenAI'),
    ], string='AI Provider', default='openai')
    ai_api_key = fields.Char(string='AI API Key')
    ai_model = fields.Char(string='AI Model', default='gpt-4o-mini')
    ai_base_url = fields.Char(string='AI Base URL',
                              help='For Ollama: http://localhost:11434/v1')
    ai_auto_analysis = fields.Boolean(string='Enable Auto Analysis', default=True)
    ai_analysis_interval_min = fields.Integer(string='AI Analysis Interval (min)', default=30)

    # Alert webhook
    alert_webhook_secret = fields.Char(string='Alert Webhook Secret')

    # Thresholds
    idle_threshold_cpu = fields.Float(string='Idle CPU Threshold (%)', default=5.0)
    idle_threshold_days = fields.Integer(string='Idle Duration Threshold (days)', default=7)
    cpu_warning_threshold = fields.Float(string='CPU Warning (%)', default=80.0)
    cpu_critical_threshold = fields.Float(string='CPU Critical (%)', default=95.0)
    ram_warning_threshold = fields.Float(string='RAM Warning (%)', default=85.0)
    disk_warning_threshold = fields.Float(string='Disk Warning (%)', default=80.0)

    @api.model
    def get_config(self):
        """Return the singleton configuration record."""
        config = self.search([], limit=1)
        if not config:
            config = self.create({'name': 'Default Configuration'})
        return config
