# Dashboard Design & API Integration Guide

## Part 1: Dashboard Layout Design

The dashboard is the centerpiece of the system — it replaces Grafana with a native Odoo experience.

### Dashboard Wireframe

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  SERVER MONITORING DASHBOARD                                    [⟳ Refresh] │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 47           │ │ 41           │ │  4           │ │  2           │       │
│  │ Total Servers│ │ Healthy ✓    │ │ Warning ⚠    │ │ Critical ✗   │       │
│  │              │ │ (87%)        │ │ (9%)         │ │ (4%)         │       │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 5            │ │ 3            │ │ $12,450      │ │ AI Score     │       │
│  │ Idle Servers │ │ Active Alerts│ │ Monthly Cost │ │ 78/100 ■■■■░ │       │
│  │              │ │              │ │              │ │ Fleet Health │       │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                                              │
│  ┌─── AI SUMMARY ──────────────────────────────────────────────────────┐    │
│  │ "Fleet is generally healthy. 2 critical servers need immediate       │    │
│  │  attention: db-replica-02 (disk 94%) and app-server-prod (CPU 92%). │    │
│  │  5 idle servers identified — potential savings of $1,200/month.      │    │
│  │  Recommendation: Prioritize disk cleanup on db-replica-02."         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─── SERVER HEALTH MAP ─────────────────────────────────────────────┐      │
│  │                                                                    │      │
│  │  ■ ■ ■ ■ ■ ■ ■ ■ ■ ■   (Each square = 1 server)                │      │
│  │  ■ ■ ■ ■ ■ ■ ■ ■ ■ ■   Green = Healthy                         │      │
│  │  ■ ■ ■ ■ ■ ■ ■ ■ ■ ■   Yellow = Warning                        │      │
│  │  ■ ■ ■ ■ ■ ■ ■ ■ ■ ■   Red = Critical                          │      │
│  │  ■ ■ ■ ■ ■ ■ ■         Gray = Idle                              │      │
│  │                          Click any square for server details       │      │
│  └────────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  ┌─── CPU USAGE (All Servers) ──────┐ ┌─── RAM USAGE (All Servers) ──────┐ │
│  │                                   │ │                                   │ │
│  │  100% ─┐                         │ │  100% ─┐                         │ │
│  │        │    ╱╲                    │ │        │  ___                     │ │
│  │   50% ─┤ ╱╱  ╲╲___              │ │   50% ─┤ /   \___               │ │
│  │        │╱          ╲__           │ │        │/          \__           │ │
│  │    0% ─┴─────────────────        │ │    0% ─┴─────────────────        │ │
│  │        6h    4h    2h   now      │ │        6h    4h    2h   now      │ │
│  │                                   │ │                                   │ │
│  │  ── Server-08  ── Server-31      │ │  ── Server-15  ── Server-31      │ │
│  └───────────────────────────────────┘ └───────────────────────────────────┘ │
│                                                                              │
│  ┌─── TOP SERVERS BY CPU ───────────┐ ┌─── ACTIVE ALERTS ────────────────┐ │
│  │                                   │ │                                   │ │
│  │  app-server-prod   ████████░ 92% │ │  🔴 db-replica-02: Disk 94%     │ │
│  │  web-server-01     ██████░░░ 67% │ │  🔴 app-server-prod: CPU 92%    │ │
│  │  db-primary        █████░░░░ 58% │ │  🟡 web-server-01: Memory 88%   │ │
│  │  api-gateway       ████░░░░░ 45% │ │  🟡 Server-22: Network errors   │ │
│  │  cache-server      ███░░░░░░ 33% │ │  ℹ️  Server-12: Idle 23 days    │ │
│  │                                   │ │                                   │ │
│  └───────────────────────────────────┘ └───────────────────────────────────┘ │
│                                                                              │
│  ┌─── SERVER CARDS (Scrollable) ──────────────────────────────────────┐     │
│  │                                                                     │     │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐      │     │
│  │  │ 🔴 db-replica-02│ │ 🔴 app-srv-prod │ │ 🟡 web-srv-01  │      │     │
│  │  │ 192.168.1.11    │ │ 192.168.1.31    │ │ 192.168.1.10   │      │     │
│  │  │                 │ │                 │ │                 │      │     │
│  │  │ CPU: ██░ 23%    │ │ CPU: █████ 92%  │ │ CPU: ████ 67%  │      │     │
│  │  │ RAM: ███ 45%    │ │ RAM: ███░ 71%   │ │ RAM: █████ 88% │      │     │
│  │  │ DSK: █████ 94%  │ │ DSK: ██░ 35%    │ │ DSK: ███░ 55%  │      │     │
│  │  │                 │ │                 │ │                 │      │     │
│  │  │ AI: Disk full   │ │ AI: Scale up    │ │ AI: Memory leak│      │     │
│  │  │ in ~3 days      │ │ recommended     │ │ suspected      │      │     │
│  │  └─────────────────┘ └─────────────────┘ └─────────────────┘      │     │
│  │  ◄ ─────────────── scroll for more ─────────────────── ►          │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌─── AI CHAT ──────────────────────────────────────────────────────┐       │
│  │  💬 Ask AI about your servers...                                  │       │
│  │                                                                    │       │
│  │  You: Which servers should I decommission?                        │       │
│  │                                                                    │       │
│  │  AI: Based on the last 30 days of data, I recommend               │       │
│  │      decommissioning these 3 servers:                              │       │
│  │      1. Server-12 (test-env-old) - Idle 23 days, $180/mo         │       │
│  │      2. Server-35 (demo-env) - Idle 18 days, $120/mo             │       │
│  │      3. Server-44 (staging-v1) - Idle 14 days, $60/mo            │       │
│  │      Total savings: $360/month ($4,320/year)                      │       │
│  │                                                                    │       │
│  │  [Type your question...                              ] [Send]     │       │
│  └────────────────────────────────────────────────────────────────────┘       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 2: Dashboard Implementation Approach

### JavaScript Chart Library: ECharts (Recommended)

**Why ECharts over Chart.js:**
- Richer chart types (heatmaps, gauges, treemaps — perfect for server monitoring)
- Better performance with large datasets
- Built-in dark/light themes
- Excellent documentation
- Used by Apache, Alibaba, Baidu

**Include ECharts in your module:**

```xml
<!-- In __manifest__.py assets -->
'assets': {
    'web.assets_backend': [
        'server_monitoring/static/lib/echarts/echarts.min.js',
        'server_monitoring/static/src/js/dashboard.js',
        'server_monitoring/static/src/css/dashboard.css',
    ],
},
```

### Chart Types to Implement

| Chart | Library Feature | Purpose |
|-------|----------------|---------|
| **KPI Cards** | Custom HTML/CSS | Total servers, health counts, cost |
| **Health Heatmap** | ECharts heatmap | Visual grid of all servers color-coded |
| **Line Charts** | ECharts line | CPU/RAM/Disk over time |
| **Gauge Charts** | ECharts gauge | Current CPU/RAM per server |
| **Bar Charts** | ECharts bar | Top N servers by resource usage |
| **Pie/Donut** | ECharts pie | Server distribution by health/department |
| **Treemap** | ECharts treemap | Resource allocation visualization |
| **Server Cards** | Custom HTML/CSS | Individual server status cards |

### Real-Time Updates

**Approach 1: Polling (Simpler — recommended to start)**
```javascript
// Poll every 30 seconds for updated data
setInterval(async () => {
    const data = await this.rpc('/api/monitoring/dashboard');
    this.updateCharts(data);
}, 30000);
```

**Approach 2: WebSocket / Odoo Bus (More Advanced)**
```javascript
// Use Odoo's built-in bus (long polling) for real-time updates
// Odoo 14: use bus.Bus
// Odoo 19: use bus service
this.busService.subscribe('server_monitoring.update', (payload) => {
    this.updateCharts(payload);
});
```

---

## Part 3: API Endpoints (Controllers)

### Endpoint 1: Dashboard Data

```
GET /api/monitoring/dashboard
```

Returns all data needed for the dashboard in a single call:

```json
{
    "summary": {
        "total_servers": 47,
        "healthy": 41,
        "warning": 4,
        "critical": 2,
        "idle": 5,
        "unreachable": 0,
        "active_alerts": 3,
        "monthly_cost": 12450.00,
        "ai_fleet_score": 78,
        "ai_summary": "Fleet is generally healthy..."
    },
    "servers": [
        {
            "id": 1,
            "name": "db-replica-02",
            "ip": "192.168.1.11",
            "health": "critical",
            "cpu": 23.5,
            "ram": 45.2,
            "disk": 94.1,
            "network_in": 12.5,
            "network_out": 8.3,
            "uptime_days": 45,
            "ai_summary": "Disk full in ~3 days",
            "ai_risk_score": 92,
            "active_alerts": ["DiskSpaceLow"]
        }
    ],
    "alerts": [
        {
            "id": 1,
            "server_name": "db-replica-02",
            "alert_name": "DiskSpaceLow",
            "severity": "critical",
            "started_at": "2026-02-20T08:30:00",
            "description": "Disk usage at 94%"
        }
    ],
    "charts": {
        "cpu_history": {
            "timestamps": ["2026-02-20T06:00:00", "..."],
            "series": [
                {"name": "db-replica-02", "data": [23, 24, 22, ...]},
                {"name": "app-server-prod", "data": [90, 92, 88, ...]}
            ]
        },
        "ram_history": { "..." : "..." },
        "top_cpu": [
            {"name": "app-server-prod", "value": 92},
            {"name": "web-server-01", "value": 67}
        ]
    },
    "ai_recommendations": [
        "Prioritize disk cleanup on db-replica-02",
        "Scale up app-server-prod or distribute load",
        "Investigate memory leak on web-server-01"
    ]
}
```

### Endpoint 2: Server Detail

```
GET /api/monitoring/server/<int:server_id>
```

Returns detailed metrics and history for a single server.

### Endpoint 3: Server Metrics History

```
GET /api/monitoring/server/<int:server_id>/metrics?hours=24
```

Returns historical metrics for charts.

### Endpoint 4: AI Chat

```
POST /api/monitoring/ai_chat
Body: {
    "message": "Which servers are idle?",
    "session_id": "abc123"
}

Response: {
    "response": "Based on the metrics, 5 servers are idle...",
    "session_id": "abc123",
    "context_servers": [12, 15, 22, 31, 35]
}
```

### Endpoint 5: Alert Webhook (Receives from Alertmanager)

```
POST /api/monitoring/alert_webhook
Body: (Alertmanager webhook payload)
```

### Endpoint 6: Trigger AI Analysis

```
POST /api/monitoring/ai_analyze
Body: {
    "server_ids": [1, 2, 3],  // or empty for all
    "analysis_type": "health_check"
}
```

---

## Part 4: Prometheus API Integration Details

### How Odoo Talks to Prometheus

```python
import requests
import json
from datetime import datetime, timedelta

class PrometheusService:
    """Handles all communication with Prometheus API."""

    def __init__(self, base_url, username=None, password=None):
        self.base_url = base_url.rstrip('/')
        self.auth = (username, password) if username else None
        self.session = requests.Session()
        if self.auth:
            self.session.auth = self.auth

    def instant_query(self, query):
        """Execute an instant PromQL query."""
        response = self.session.get(
            f'{self.base_url}/api/v1/query',
            params={'query': query},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        if data['status'] != 'success':
            raise Exception(f"Prometheus query failed: {data.get('error', 'Unknown')}")
        return data['data']['result']

    def range_query(self, query, start, end, step='5m'):
        """Execute a range PromQL query (for charts)."""
        response = self.session.get(
            f'{self.base_url}/api/v1/query_range',
            params={
                'query': query,
                'start': start.isoformat() + 'Z',
                'end': end.isoformat() + 'Z',
                'step': step,
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data['data']['result']

    def get_targets(self):
        """Get all configured scrape targets and their status."""
        response = self.session.get(
            f'{self.base_url}/api/v1/targets',
            timeout=10
        )
        response.raise_for_status()
        return response.json()['data']['activeTargets']

    def get_server_metrics(self, instance):
        """Get all key metrics for a specific server."""
        queries = {
            'cpu_usage': f'100 - (avg by(instance) (rate(node_cpu_seconds_total{{mode="idle",instance="{instance}"}}[5m])) * 100)',
            'ram_usage': f'(1 - node_memory_MemAvailable_bytes{{instance="{instance}"}} / node_memory_MemTotal_bytes{{instance="{instance}"}}) * 100',
            'ram_total': f'node_memory_MemTotal_bytes{{instance="{instance}"}}',
            'disk_usage': f'(1 - node_filesystem_avail_bytes{{instance="{instance}",fstype!="tmpfs",mountpoint="/"}} / node_filesystem_size_bytes{{instance="{instance}",fstype!="tmpfs",mountpoint="/"}}) * 100',
            'load_1m': f'node_load1{{instance="{instance}"}}',
            'load_5m': f'node_load5{{instance="{instance}"}}',
            'load_15m': f'node_load15{{instance="{instance}"}}',
            'network_in': f'rate(node_network_receive_bytes_total{{instance="{instance}",device!="lo"}}[5m])',
            'network_out': f'rate(node_network_transmit_bytes_total{{instance="{instance}",device!="lo"}}[5m])',
            'uptime': f'time() - node_boot_time_seconds{{instance="{instance}"}}',
            'processes': f'node_procs_running{{instance="{instance}"}}',
        }

        results = {}
        for key, query in queries.items():
            try:
                result = self.instant_query(query)
                if result:
                    results[key] = float(result[0]['value'][1])
                else:
                    results[key] = None
            except Exception:
                results[key] = None

        return results

    def get_cpu_history(self, instance, hours=6):
        """Get CPU usage history for charts."""
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)
        query = f'100 - (avg by(instance) (rate(node_cpu_seconds_total{{mode="idle",instance="{instance}"}}[5m])) * 100)'
        return self.range_query(query, start, end, step='5m')

    def is_server_up(self, instance):
        """Check if a specific server is reachable."""
        result = self.instant_query(f'up{{instance="{instance}"}}')
        if result:
            return int(result[0]['value'][1]) == 1
        return False

    def get_all_servers_status(self):
        """Get up/down status for all servers."""
        result = self.instant_query('up{job="servers"}')
        return {
            r['metric']['instance']: int(r['value'][1]) == 1
            for r in result
        }
```

### How the Cron Job Uses This Service

```python
# Simplified flow of the metric collection cron job

def _cron_collect_metrics(self):
    """Called every 5 minutes by ir.cron."""
    config = self.env['server.monitoring.config'].get_config()
    prom = PrometheusService(
        base_url=config.prometheus_url,
        username=config.prometheus_username,
        password=config.prometheus_password
    )

    servers = self.env['server.monitoring.server'].search([
        ('state', '=', 'active'),
        ('is_monitored', '=', True),
    ])

    for server in servers:
        instance = f'{server.ip_address}:{server.port}'
        metrics = prom.get_server_metrics(instance)

        # Update server record
        server.write({
            'cpu_usage_percent': metrics.get('cpu_usage', 0),
            'ram_usage_percent': metrics.get('ram_usage', 0),
            'disk_usage_percent': metrics.get('disk_usage', 0),
            'network_in_mbps': (metrics.get('network_in', 0) or 0) / 1048576,
            'network_out_mbps': (metrics.get('network_out', 0) or 0) / 1048576,
            'load_average_1m': metrics.get('load_1m', 0),
            'load_average_5m': metrics.get('load_5m', 0),
            'load_average_15m': metrics.get('load_15m', 0),
            'uptime_seconds': metrics.get('uptime', 0),
            'last_seen': fields.Datetime.now(),
            'health_status': server._compute_health_status(metrics),
        })

        # Create snapshot
        self.env['server.monitoring.metric.snapshot'].create({
            'server_id': server.id,
            'timestamp': fields.Datetime.now(),
            'cpu_usage_percent': metrics.get('cpu_usage', 0),
            'ram_usage_percent': metrics.get('ram_usage', 0),
            'disk_usage_percent': metrics.get('disk_usage', 0),
            'network_in_bytes': metrics.get('network_in', 0),
            'network_out_bytes': metrics.get('network_out', 0),
            'load_average_1m': metrics.get('load_1m', 0),
            'load_average_5m': metrics.get('load_5m', 0),
            'load_average_15m': metrics.get('load_15m', 0),
            'raw_data': json.dumps(metrics),
        })

    self.env.cr.commit()
```

---

## Part 5: Dynamic API Integration

### Adding New Data Sources

The system is designed to be **extensible**. Want to add monitoring for something new? Here is the pattern:

#### Example: Add Cursor AI Usage Monitoring

```python
class CursorAPIService:
    """Monitor Cursor AI usage statistics."""

    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = 'https://api.cursor.com/v1'  # hypothetical

    def get_usage(self):
        response = requests.get(
            f'{self.base_url}/usage',
            headers={'Authorization': f'Bearer {self.api_key}'},
            timeout=10
        )
        return response.json()
```

#### Example: Add ChatGPT API Usage Monitoring

```python
class OpenAIUsageService:
    """Monitor OpenAI API usage and costs."""

    def __init__(self, api_key):
        self.api_key = api_key

    def get_usage(self, date):
        response = requests.get(
            'https://api.openai.com/v1/usage',
            headers={'Authorization': f'Bearer {self.api_key}'},
            params={'date': date},
            timeout=10
        )
        return response.json()

    def get_billing(self):
        response = requests.get(
            'https://api.openai.com/dashboard/billing/usage',
            headers={'Authorization': f'Bearer {self.api_key}'},
            timeout=10
        )
        return response.json()
```

#### Generic Pattern for Any New API

```python
# 1. Create a new service class in services/
# 2. Add configuration fields to server.monitoring.config
# 3. Add a new cron job to collect data
# 4. Add new fields to the server model (or create a new model)
# 5. Add chart components to the dashboard
# 6. Update AI prompts to include the new data
```

---

## Part 6: Webhook Integration (Odoo Receives Data)

### Alertmanager → Odoo Webhook

When Prometheus detects an alert, Alertmanager sends it to Odoo:

```python
from odoo import http
import json
import hmac
import hashlib

class AlertWebhookController(http.Controller):

    @http.route('/api/monitoring/alert_webhook', type='json', auth='none', csrf=False)
    def receive_alert(self, **kwargs):
        """Receive alert webhooks from Prometheus Alertmanager."""
        # Verify webhook secret
        config = http.request.env['server.monitoring.config'].sudo().get_config()
        # ... verify HMAC signature ...

        payload = json.loads(http.request.httprequest.data)

        for alert in payload.get('alerts', []):
            instance = alert['labels'].get('instance', '')
            server = http.request.env['server.monitoring.server'].sudo().search([
                ('ip_address', '=', instance.split(':')[0])
            ], limit=1)

            http.request.env['server.monitoring.alert'].sudo().create({
                'server_id': server.id if server else False,
                'alert_name': alert['labels'].get('alertname', ''),
                'severity': alert['labels'].get('severity', 'warning'),
                'state': alert['status'],  # 'firing' or 'resolved'
                'description': alert['annotations'].get('description', ''),
                'started_at': alert.get('startsAt'),
                'resolved_at': alert.get('endsAt') if alert['status'] == 'resolved' else False,
                'raw_payload': json.dumps(alert),
            })

            # Trigger AI analysis for the alert
            if alert['status'] == 'firing' and server:
                server._trigger_ai_alert_analysis(alert)

        return {'status': 'ok'}
```

---

## Part 7: Odoo → Prometheus Dynamic Target Management

When you add a new server in Odoo, it automatically updates Prometheus targets:

```python
class ServerMonitoringServer(models.Model):
    _name = 'server.monitoring.server'

    def _sync_prometheus_targets(self):
        """Write Prometheus file_sd target file when servers change."""
        servers = self.search([
            ('state', 'in', ['active', 'maintenance']),
            ('is_monitored', '=', True),
        ])

        targets = []
        for server in servers:
            targets.append({
                'targets': [f'{server.ip_address}:{server.port}'],
                'labels': {
                    'hostname': server.name,
                    'department': server.department_id.name or '',
                    'owner': server.owner_id.name or '',
                    'purpose': server.purpose or '',
                    'odoo_server_id': str(server.id),
                    'environment': 'production',  # or derive from tags
                }
            })

        config = self.env['server.monitoring.config'].get_config()
        target_file = config.prometheus_targets_file or '/etc/prometheus/targets/odoo_servers.json'

        # Write to Prometheus target file
        # This requires the Odoo server to have write access to this path
        # OR use Prometheus HTTP API to reload config
        import json
        with open(target_file, 'w') as f:
            json.dump(targets, f, indent=2)

        # Trigger Prometheus config reload
        import requests
        requests.post(f'{config.prometheus_url}/-/reload', timeout=5)

    # Override create/write/unlink to auto-sync
    def write(self, vals):
        result = super().write(vals)
        if any(f in vals for f in ['ip_address', 'port', 'state', 'is_monitored']):
            self._sync_prometheus_targets()
        return result
```

---

## Summary: API & Dashboard Flow

```
┌──────────────────┐     ┌───────────────┐     ┌──────────────┐
│  Prometheus API   │────►│ Odoo Backend  │────►│ Odoo Frontend│
│  (Data source)    │     │ (Python)      │     │ (JS/ECharts) │
│                   │     │               │     │              │
│ /api/v1/query     │     │ Cron jobs     │     │ Dashboard    │
│ /api/v1/query_range     │ Controllers   │     │ Charts       │
│ /api/v1/targets   │     │ Services      │     │ AI Chat      │
└──────────────────┘     └───────┬───────┘     └──────────────┘
                                 │
                                 ▼
                         ┌───────────────┐
                         │  OpenAI API   │
                         │  (AI Engine)  │
                         │               │
                         │ Analysis      │
                         │ Chat          │
                         │ Predictions   │
                         └───────────────┘
```
