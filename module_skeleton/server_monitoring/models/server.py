# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json
import logging

_logger = logging.getLogger(__name__)

SERVER_STATES = [
    ('draft', 'Draft'),
    ('active', 'Active'),
    ('maintenance', 'Maintenance'),
    ('inactive', 'Inactive'),
    ('decommissioned', 'Decommissioned'),
]

HEALTH_STATES = [
    ('healthy', 'Healthy'),
    ('warning', 'Warning'),
    ('critical', 'Critical'),
    ('unknown', 'Unknown'),
    ('unreachable', 'Unreachable'),
]

OS_TYPES = [
    ('linux', 'Linux'),
    ('windows', 'Windows'),
    ('macos', 'macOS'),
    ('other', 'Other'),
]

CLOUD_PROVIDERS = [
    ('on_premise', 'On-Premise'),
    ('aws', 'AWS'),
    ('azure', 'Azure'),
    ('gcp', 'Google Cloud'),
    ('digitalocean', 'DigitalOcean'),
    ('other', 'Other'),
]


class ServerMonitoringTag(models.Model):
    _name = 'server.monitoring.tag'
    _description = 'Server Tag'

    name = fields.Char(required=True)
    color = fields.Integer(string='Color Index')


class ServerMonitoringServer(models.Model):
    _name = 'server.monitoring.server'
    _description = 'Monitored Server'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'health_status desc, name'

    name = fields.Char(string='Hostname', required=True, tracking=True)
    ip_address = fields.Char(string='IP Address', required=True, tracking=True)
    ip_address_internal = fields.Char(string='Internal IP')
    fqdn = fields.Char(string='FQDN')
    port = fields.Integer(string='Exporter Port', default=9100)

    # Server specifications
    os_type = fields.Selection(OS_TYPES, string='OS Type', default='linux', tracking=True)
    os_version = fields.Char(string='OS Version')
    cpu_cores = fields.Integer(string='CPU Cores')
    ram_total_gb = fields.Float(string='Total RAM (GB)')
    disk_total_gb = fields.Float(string='Total Disk (GB)')
    purpose = fields.Char(string='Purpose', tracking=True)
    description = fields.Text(string='Description')
    tag_ids = fields.Many2many('server.monitoring.tag', string='Tags')

    # Ownership
    department_id = fields.Many2one('hr.department', string='Department', tracking=True)
    owner_id = fields.Many2one('res.users', string='Owner', tracking=True)
    team_ids = fields.Many2many('res.users', string='Team Members')

    # Location
    datacenter = fields.Char(string='Data Center')
    rack_number = fields.Char(string='Rack Number')
    cloud_provider = fields.Selection(CLOUD_PROVIDERS, string='Cloud Provider', default='on_premise')
    cloud_region = fields.Char(string='Cloud Region')
    cloud_instance_type = fields.Char(string='Instance Type')
    cost_per_month = fields.Float(string='Monthly Cost ($)')

    # Status
    state = fields.Selection(SERVER_STATES, string='State', default='draft', tracking=True)
    health_status = fields.Selection(HEALTH_STATES, string='Health', default='unknown', tracking=True)
    is_monitored = fields.Boolean(string='Monitored', default=True)
    last_seen = fields.Datetime(string='Last Seen')
    uptime_seconds = fields.Float(string='Uptime (seconds)')

    # Live metrics (updated by cron)
    cpu_usage_percent = fields.Float(string='CPU Usage (%)')
    ram_usage_percent = fields.Float(string='RAM Usage (%)')
    disk_usage_percent = fields.Float(string='Disk Usage (%)')
    network_in_mbps = fields.Float(string='Network In (Mbps)')
    network_out_mbps = fields.Float(string='Network Out (Mbps)')
    load_average_1m = fields.Float(string='Load Avg (1m)')
    load_average_5m = fields.Float(string='Load Avg (5m)')
    load_average_15m = fields.Float(string='Load Avg (15m)')
    process_count = fields.Integer(string='Running Processes')

    # AI fields
    ai_summary = fields.Text(string='AI Summary')
    ai_recommendation = fields.Text(string='AI Recommendation')
    ai_risk_score = fields.Float(string='AI Risk Score (0-100)')
    ai_last_analysis = fields.Datetime(string='Last AI Analysis')

    # Relations
    metric_snapshot_ids = fields.One2many(
        'server.monitoring.metric.snapshot', 'server_id', string='Metric Snapshots')
    allocation_ids = fields.One2many(
        'server.monitoring.allocation', 'server_id', string='Allocations')
    alert_ids = fields.One2many(
        'server.monitoring.alert', 'server_id', string='Alerts')
    ai_analysis_ids = fields.One2many(
        'server.monitoring.ai.analysis', 'server_id', string='AI Analyses')

    # Computed fields
    is_idle = fields.Boolean(string='Is Idle', compute='_compute_is_idle', store=True)
    active_alerts_count = fields.Integer(
        string='Active Alerts', compute='_compute_active_alerts_count')
    uptime_display = fields.Char(string='Uptime', compute='_compute_uptime_display')

    @api.depends('cpu_usage_percent')
    def _compute_is_idle(self):
        config = self.env['server.monitoring.config'].sudo().get_config()
        threshold = config.idle_threshold_cpu if config else 5.0
        for rec in self:
            rec.is_idle = rec.cpu_usage_percent < threshold and rec.state == 'active'

    def _compute_active_alerts_count(self):
        for rec in self:
            rec.active_alerts_count = len(
                rec.alert_ids.filtered(lambda a: a.state == 'firing'))

    def _compute_uptime_display(self):
        for rec in self:
            if not rec.uptime_seconds:
                rec.uptime_display = 'Unknown'
                continue
            days = int(rec.uptime_seconds // 86400)
            hours = int((rec.uptime_seconds % 86400) // 3600)
            rec.uptime_display = f'{days}d {hours}h'

    def _compute_health_status(self, metrics):
        """Determine health based on metric thresholds."""
        config = self.env['server.monitoring.config'].sudo().get_config()
        cpu = metrics.get('cpu_usage', 0) or 0
        ram = metrics.get('ram_usage', 0) or 0
        disk = metrics.get('disk_usage', 0) or 0

        if cpu > (config.cpu_critical_threshold or 95) or \
           ram > 95 or disk > 95:
            return 'critical'
        if cpu > (config.cpu_warning_threshold or 80) or \
           ram > (config.ram_warning_threshold or 85) or \
           disk > (config.disk_warning_threshold or 80):
            return 'warning'
        return 'healthy'

    # State transition buttons
    def action_activate(self):
        self.write({'state': 'active'})

    def action_maintenance(self):
        self.write({'state': 'maintenance'})

    def action_decommission(self):
        self.write({'state': 'decommissioned', 'is_monitored': False})

    def action_set_inactive(self):
        self.write({'state': 'inactive'})

    def action_run_ai_analysis(self):
        """Manually trigger AI analysis for selected servers."""
        self.env['server.monitoring.server']._run_ai_analysis(self)

    def _get_prometheus_instance(self):
        """Return the Prometheus instance identifier (ip:port)."""
        self.ensure_one()
        return f'{self.ip_address}:{self.port}'

    def _get_recent_metrics(self, hours=1):
        """Get recent metric snapshots for AI analysis."""
        self.ensure_one()
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), hours=hours)
        snapshots = self.metric_snapshot_ids.filtered(
            lambda s: s.timestamp >= cutoff
        ).sorted('timestamp')
        return [{
            'timestamp': str(s.timestamp),
            'cpu': s.cpu_usage_percent,
            'ram': s.ram_usage_percent,
            'disk': s.disk_usage_percent,
            'load_1m': s.load_average_1m,
            'network_in': s.network_in_bytes,
            'network_out': s.network_out_bytes,
        } for s in snapshots]

    # Cron job entry points
    @api.model
    def _cron_collect_metrics(self):
        """Scheduled action: Collect metrics from Prometheus for all monitored servers."""
        from ..services.prometheus_service import PrometheusService
        config = self.env['server.monitoring.config'].sudo().get_config()
        if not config or not config.prometheus_url:
            _logger.warning("Prometheus URL not configured. Skipping metric collection.")
            return

        prom = PrometheusService(
            base_url=config.prometheus_url,
            username=config.prometheus_username,
            password=config.prometheus_password,
        )

        servers = self.search([
            ('state', 'in', ['active', 'maintenance']),
            ('is_monitored', '=', True),
        ])

        for server in servers:
            try:
                instance = server._get_prometheus_instance()
                metrics = prom.get_server_metrics(instance)

                server.write({
                    'cpu_usage_percent': metrics.get('cpu_usage') or 0,
                    'ram_usage_percent': metrics.get('ram_usage') or 0,
                    'disk_usage_percent': metrics.get('disk_usage') or 0,
                    'network_in_mbps': (metrics.get('network_in') or 0) / 1048576,
                    'network_out_mbps': (metrics.get('network_out') or 0) / 1048576,
                    'load_average_1m': metrics.get('load_1m') or 0,
                    'load_average_5m': metrics.get('load_5m') or 0,
                    'load_average_15m': metrics.get('load_15m') or 0,
                    'uptime_seconds': metrics.get('uptime') or 0,
                    'last_seen': fields.Datetime.now(),
                    'health_status': server._compute_health_status(metrics),
                })

                self.env['server.monitoring.metric.snapshot'].create({
                    'server_id': server.id,
                    'timestamp': fields.Datetime.now(),
                    'cpu_usage_percent': metrics.get('cpu_usage') or 0,
                    'ram_usage_percent': metrics.get('ram_usage') or 0,
                    'disk_usage_percent': metrics.get('disk_usage') or 0,
                    'network_in_bytes': metrics.get('network_in') or 0,
                    'network_out_bytes': metrics.get('network_out') or 0,
                    'load_average_1m': metrics.get('load_1m') or 0,
                    'load_average_5m': metrics.get('load_5m') or 0,
                    'load_average_15m': metrics.get('load_15m') or 0,
                    'io_read_bytes': metrics.get('io_read') or 0,
                    'io_write_bytes': metrics.get('io_write') or 0,
                    'process_count': int(metrics.get('processes') or 0),
                    'raw_data': json.dumps(metrics),
                })
            except Exception as e:
                _logger.error(f"Failed to collect metrics for {server.name}: {e}")
                server.write({'health_status': 'unreachable'})

        self.env.cr.commit()

    @api.model
    def _cron_ai_analysis(self):
        """Scheduled action: Run AI analysis on all active servers."""
        self._run_ai_analysis()

    @api.model
    def _run_ai_analysis(self, servers=None):
        """Execute AI analysis for given servers (or all active servers)."""
        from ..services.ai_service import AIService
        config = self.env['server.monitoring.config'].sudo().get_config()
        if not config or not config.ai_api_key:
            _logger.warning("AI API key not configured. Skipping AI analysis.")
            return

        ai = AIService(
            api_key=config.ai_api_key,
            model=config.ai_model or 'gpt-4o-mini',
            base_url=config.ai_base_url or None,
        )

        if servers is None:
            servers = self.search([('state', '=', 'active'), ('is_monitored', '=', True)])

        all_data = []
        for server in servers:
            all_data.append({
                'id': server.id,
                'name': server.name,
                'ip': server.ip_address,
                'os': server.os_type,
                'cpu_cores': server.cpu_cores,
                'ram_total_gb': server.ram_total_gb,
                'current': {
                    'cpu': server.cpu_usage_percent,
                    'ram': server.ram_usage_percent,
                    'disk': server.disk_usage_percent,
                    'load': [server.load_average_1m, server.load_average_5m, server.load_average_15m],
                },
                'recent_history': server._get_recent_metrics(hours=1),
                'active_alerts': [a.alert_name for a in server.alert_ids.filtered(lambda a: a.state == 'firing')],
                'uptime_days': (server.uptime_seconds or 0) / 86400,
            })

        try:
            fleet_analysis = ai.analyze_fleet(all_data)

            for server_result in fleet_analysis.get('servers', []):
                server = self.browse(server_result.get('id'))
                if server.exists():
                    server.write({
                        'ai_summary': server_result.get('summary', ''),
                        'ai_recommendation': '\n'.join(server_result.get('recommendations', [])),
                        'ai_risk_score': server_result.get('risk_score', 0),
                        'ai_last_analysis': fields.Datetime.now(),
                    })

            self.env['server.monitoring.ai.analysis'].create({
                'analysis_type': 'fleet_overview',
                'trigger': 'scheduled',
                'input_data': json.dumps(all_data),
                'ai_response': json.dumps(fleet_analysis),
                'summary': fleet_analysis.get('daily_summary', ''),
                'model_used': config.ai_model or 'gpt-4o-mini',
            })
        except Exception as e:
            _logger.error(f"AI analysis failed: {e}")

    @api.model
    def _cron_cleanup_snapshots(self):
        """Scheduled action: Clean up old metric snapshots per retention policy."""
        config = self.env['server.monitoring.config'].sudo().get_config()
        retention_days = config.snapshot_retention_days if config else 30

        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=retention_days)
        old_snapshots = self.env['server.monitoring.metric.snapshot'].search([
            ('timestamp', '<', cutoff),
        ])
        count = len(old_snapshots)
        old_snapshots.unlink()
        _logger.info(f"Cleaned up {count} old metric snapshots (older than {retention_days} days)")

    def _sync_prometheus_targets(self):
        """Update Prometheus file-based service discovery targets."""
        servers = self.search([
            ('state', 'in', ['active', 'maintenance']),
            ('is_monitored', '=', True),
        ])

        targets = []
        for server in servers:
            targets.append({
                'targets': [server._get_prometheus_instance()],
                'labels': {
                    'hostname': server.name,
                    'department': server.department_id.name or '',
                    'owner': server.owner_id.name or '',
                    'purpose': server.purpose or '',
                    'odoo_server_id': str(server.id),
                },
            })

        config = self.env['server.monitoring.config'].sudo().get_config()
        if not config:
            return

        target_file = '/etc/prometheus/targets/odoo_servers.json'
        try:
            with open(target_file, 'w') as f:
                json.dump(targets, f, indent=2)
            _logger.info(f"Updated Prometheus targets file with {len(targets)} servers")

            import requests
            requests.post(f'{config.prometheus_url}/-/reload', timeout=5)
        except Exception as e:
            _logger.warning(f"Could not update Prometheus targets: {e}")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_prometheus_targets()
        return records

    def write(self, vals):
        result = super().write(vals)
        if any(f in vals for f in ['ip_address', 'port', 'state', 'is_monitored']):
            self._sync_prometheus_targets()
        return result
