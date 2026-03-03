# -*- coding: utf-8 -*-
"""
Orchestrator that ties Prometheus data collection and AI analysis together.
Called by Odoo cron jobs.
"""
import logging

_logger = logging.getLogger(__name__)


class MetricCollector:
    """High-level orchestrator for the metric collection pipeline."""

    def __init__(self, env):
        self.env = env

    def collect_and_store(self):
        """Full pipeline: pull from Prometheus, store in Odoo, detect anomalies."""
        self.env['server.monitoring.server']._cron_collect_metrics()

    def run_ai_analysis(self):
        """Run AI fleet analysis."""
        self.env['server.monitoring.server']._cron_ai_analysis()

    def cleanup_old_data(self):
        """Remove stale metric snapshots."""
        self.env['server.monitoring.server']._cron_cleanup_snapshots()
