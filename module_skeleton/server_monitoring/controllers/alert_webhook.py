# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class AlertWebhookController(http.Controller):

    @http.route('/api/monitoring/alert_webhook', type='json', auth='none', csrf=False, methods=['POST'])
    def receive_alert(self, **kwargs):
        """Receive alert webhooks from Prometheus Alertmanager."""
        try:
            payload = json.loads(request.httprequest.data)
        except (json.JSONDecodeError, TypeError):
            payload = kwargs

        alerts = payload.get('alerts', [])
        Server = request.env['server.monitoring.server'].sudo()
        Alert = request.env['server.monitoring.alert'].sudo()

        for alert in alerts:
            labels = alert.get('labels', {})
            annotations = alert.get('annotations', {})
            instance = labels.get('instance', '')
            ip = instance.split(':')[0] if instance else ''

            server = Server.search([('ip_address', '=', ip)], limit=1) if ip else Server

            existing = Alert.search([
                ('server_id', '=', server.id if server else False),
                ('alert_name', '=', labels.get('alertname', '')),
                ('state', '=', 'firing'),
            ], limit=1)

            status = alert.get('status', 'firing')

            if existing and status == 'resolved':
                existing.write({
                    'state': 'resolved',
                    'resolved_at': alert.get('endsAt'),
                })
            elif not existing and status == 'firing':
                new_alert = Alert.create({
                    'server_id': server.id if server else False,
                    'alert_name': labels.get('alertname', 'Unknown'),
                    'severity': labels.get('severity', 'warning'),
                    'state': 'firing',
                    'description': annotations.get('description', annotations.get('summary', '')),
                    'started_at': alert.get('startsAt'),
                    'raw_payload': json.dumps(alert),
                })

                if server:
                    self._trigger_ai_alert_analysis(new_alert, server)

        return {'status': 'ok', 'processed': len(alerts)}

    def _trigger_ai_alert_analysis(self, alert_record, server):
        """Asynchronously analyze alert with AI."""
        try:
            config = request.env['server.monitoring.config'].sudo().get_config()
            if not config or not config.ai_api_key:
                return

            from ..services.ai_service import AIService
            ai = AIService(
                api_key=config.ai_api_key,
                model=config.ai_model or 'gpt-4o-mini',
                base_url=config.ai_base_url or None,
            )

            alert_data = {
                'name': alert_record.alert_name,
                'severity': alert_record.severity,
                'description': alert_record.description,
            }
            server_metrics = {
                'name': server.name,
                'cpu': server.cpu_usage_percent,
                'ram': server.ram_usage_percent,
                'disk': server.disk_usage_percent,
                'load': [server.load_average_1m, server.load_average_5m, server.load_average_15m],
            }

            analysis = ai.explain_alert(alert_data, server_metrics)
            alert_record.write({
                'ai_analysis': analysis.get('explanation', ''),
                'ai_action_taken': '\n'.join(analysis.get('immediate_actions', [])),
            })
        except Exception as e:
            _logger.error(f"AI alert analysis failed: {e}")
