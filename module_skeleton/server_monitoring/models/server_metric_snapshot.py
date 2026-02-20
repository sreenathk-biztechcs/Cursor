# -*- coding: utf-8 -*-
from odoo import models, fields


class ServerMonitoringMetricSnapshot(models.Model):
    _name = 'server.monitoring.metric.snapshot'
    _description = 'Server Metric Snapshot'
    _order = 'timestamp desc'

    server_id = fields.Many2one(
        'server.monitoring.server', string='Server',
        required=True, ondelete='cascade', index=True)
    timestamp = fields.Datetime(string='Timestamp', required=True, index=True)
    cpu_usage_percent = fields.Float(string='CPU Usage (%)')
    ram_usage_percent = fields.Float(string='RAM Usage (%)')
    ram_used_bytes = fields.Float(string='RAM Used (bytes)')
    disk_usage_percent = fields.Float(string='Disk Usage (%)')
    disk_used_bytes = fields.Float(string='Disk Used (bytes)')
    network_in_bytes = fields.Float(string='Network In (bytes/s)')
    network_out_bytes = fields.Float(string='Network Out (bytes/s)')
    load_average_1m = fields.Float(string='Load Avg (1m)')
    load_average_5m = fields.Float(string='Load Avg (5m)')
    load_average_15m = fields.Float(string='Load Avg (15m)')
    process_count = fields.Integer(string='Process Count')
    io_read_bytes = fields.Float(string='Disk Read (bytes/s)')
    io_write_bytes = fields.Float(string='Disk Write (bytes/s)')
    raw_data = fields.Text(string='Raw JSON Data')
