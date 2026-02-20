# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json


class ServerMonitoringAPI(http.Controller):

    @http.route('/api/monitoring/dashboard', type='json', auth='user')
    def dashboard_data(self, **kwargs):
        """Return all data needed for the dashboard in a single call."""
        Server = request.env['server.monitoring.server'].sudo()
        Alert = request.env['server.monitoring.alert'].sudo()

        all_servers = Server.search([('state', 'in', ['active', 'maintenance'])])
        active_alerts = Alert.search([('state', '=', 'firing')])

        healthy = all_servers.filtered(lambda s: s.health_status == 'healthy')
        warning = all_servers.filtered(lambda s: s.health_status == 'warning')
        critical = all_servers.filtered(lambda s: s.health_status == 'critical')
        idle = all_servers.filtered(lambda s: s.is_idle)

        config = request.env['server.monitoring.config'].sudo().get_config()

        ai_analysis = request.env['server.monitoring.ai.analysis'].sudo().search(
            [('analysis_type', '=', 'fleet_overview')], limit=1, order='create_date desc')

        return {
            'summary': {
                'total_servers': len(all_servers),
                'healthy': len(healthy),
                'warning': len(warning),
                'critical': len(critical),
                'idle': len(idle),
                'active_alerts': len(active_alerts),
                'monthly_cost': sum(all_servers.mapped('cost_per_month')),
                'ai_summary': ai_analysis.summary if ai_analysis else '',
            },
            'servers': [{
                'id': s.id,
                'name': s.name,
                'ip': s.ip_address,
                'health': s.health_status,
                'state': s.state,
                'cpu': round(s.cpu_usage_percent, 1),
                'ram': round(s.ram_usage_percent, 1),
                'disk': round(s.disk_usage_percent, 1),
                'network_in': round(s.network_in_mbps, 2),
                'network_out': round(s.network_out_mbps, 2),
                'uptime': s.uptime_display,
                'ai_summary': s.ai_summary or '',
                'ai_risk_score': s.ai_risk_score,
                'is_idle': s.is_idle,
                'department': s.department_id.name or '',
                'owner': s.owner_id.name or '',
            } for s in all_servers],
            'alerts': [{
                'id': a.id,
                'server_name': a.server_id.name or 'Unknown',
                'alert_name': a.alert_name,
                'severity': a.severity,
                'state': a.state,
                'started_at': str(a.started_at) if a.started_at else '',
                'description': a.description or '',
            } for a in active_alerts],
        }

    @http.route('/api/monitoring/server/<int:server_id>/metrics', type='json', auth='user')
    def server_metrics_history(self, server_id, hours=6, **kwargs):
        """Return metric history for a server (for detail charts)."""
        server = request.env['server.monitoring.server'].sudo().browse(server_id)
        if not server.exists():
            return {'error': 'Server not found'}

        from datetime import datetime, timedelta
        from odoo import fields as odoo_fields
        cutoff = odoo_fields.Datetime.subtract(odoo_fields.Datetime.now(), hours=hours)

        snapshots = request.env['server.monitoring.metric.snapshot'].sudo().search([
            ('server_id', '=', server_id),
            ('timestamp', '>=', cutoff),
        ], order='timestamp asc')

        return {
            'server': {
                'id': server.id,
                'name': server.name,
                'ip': server.ip_address,
            },
            'metrics': [{
                'timestamp': str(s.timestamp),
                'cpu': round(s.cpu_usage_percent, 1),
                'ram': round(s.ram_usage_percent, 1),
                'disk': round(s.disk_usage_percent, 1),
                'load_1m': round(s.load_average_1m, 2),
                'network_in': round(s.network_in_bytes, 0),
                'network_out': round(s.network_out_bytes, 0),
            } for s in snapshots],
        }
