# -*- coding: utf-8 -*-
"""
Prometheus API client service.
Handles all communication with Prometheus for metric collection.
"""
import requests
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class PrometheusService:

    def __init__(self, base_url, username=None, password=None):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        if username and password:
            self.session.auth = (username, password)
        self.session.headers.update({'Accept': 'application/json'})

    def instant_query(self, query):
        """Execute an instant PromQL query. Returns list of result dicts."""
        resp = self.session.get(
            f'{self.base_url}/api/v1/query',
            params={'query': query},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data['status'] != 'success':
            raise RuntimeError(f"PromQL error: {data.get('error', 'unknown')}")
        return data['data']['result']

    def range_query(self, query, start, end, step='5m'):
        """Execute a range PromQL query for time-series charts."""
        resp = self.session.get(
            f'{self.base_url}/api/v1/query_range',
            params={
                'query': query,
                'start': start.isoformat() + 'Z',
                'end': end.isoformat() + 'Z',
                'step': step,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data['status'] != 'success':
            raise RuntimeError(f"PromQL range error: {data.get('error', 'unknown')}")
        return data['data']['result']

    def get_targets(self):
        """Return list of active scrape targets from Prometheus."""
        resp = self.session.get(f'{self.base_url}/api/v1/targets', timeout=10)
        resp.raise_for_status()
        return resp.json()['data']['activeTargets']

    def is_server_up(self, instance):
        result = self.instant_query(f'up{{instance="{instance}"}}')
        return bool(result) and int(result[0]['value'][1]) == 1

    def _safe_float(self, result):
        """Extract float value from a PromQL instant result, or None."""
        if result and len(result) > 0:
            try:
                return float(result[0]['value'][1])
            except (IndexError, ValueError, TypeError):
                return None
        return None

    def get_server_metrics(self, instance):
        """Collect all key metrics for a single server instance (ip:port)."""
        queries = {
            'cpu_usage': (
                f'100 - (avg by(instance) '
                f'(rate(node_cpu_seconds_total{{mode="idle",instance="{instance}"}}[5m])) * 100)'
            ),
            'ram_usage': (
                f'(1 - node_memory_MemAvailable_bytes{{instance="{instance}"}} '
                f'/ node_memory_MemTotal_bytes{{instance="{instance}"}}) * 100'
            ),
            'ram_total': f'node_memory_MemTotal_bytes{{instance="{instance}"}}',
            'disk_usage': (
                f'(1 - node_filesystem_avail_bytes{{instance="{instance}",fstype!="tmpfs",mountpoint="/"}} '
                f'/ node_filesystem_size_bytes{{instance="{instance}",fstype!="tmpfs",mountpoint="/"}}) * 100'
            ),
            'load_1m': f'node_load1{{instance="{instance}"}}',
            'load_5m': f'node_load5{{instance="{instance}"}}',
            'load_15m': f'node_load15{{instance="{instance}"}}',
            'network_in': (
                f'sum(rate(node_network_receive_bytes_total'
                f'{{instance="{instance}",device!="lo"}}[5m]))'
            ),
            'network_out': (
                f'sum(rate(node_network_transmit_bytes_total'
                f'{{instance="{instance}",device!="lo"}}[5m]))'
            ),
            'uptime': f'time() - node_boot_time_seconds{{instance="{instance}"}}',
            'processes': f'node_procs_running{{instance="{instance}"}}',
            'io_read': f'sum(rate(node_disk_read_bytes_total{{instance="{instance}"}}[5m]))',
            'io_write': f'sum(rate(node_disk_written_bytes_total{{instance="{instance}"}}[5m]))',
        }

        results = {}
        for key, query in queries.items():
            try:
                result = self.instant_query(query)
                results[key] = self._safe_float(result)
            except Exception as e:
                _logger.debug(f"Prometheus query failed for {key} on {instance}: {e}")
                results[key] = None

        return results

    def get_metric_history(self, instance, metric_query, hours=6, step='5m'):
        """Get historical data for a metric (used for dashboard charts)."""
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)
        return self.range_query(metric_query, start, end, step)

    def get_all_servers_cpu(self, hours=6, step='5m'):
        """Get CPU history for ALL servers (for dashboard overview chart)."""
        query = '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)
        return self.range_query(query, start, end, step)
