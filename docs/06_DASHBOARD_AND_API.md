# 06 — Dashboard & API Design

## Building a Grafana-Style Dashboard Inside Odoo

This document covers how to build dynamic, real-time dashboards in Odoo that rival Grafana's look and feel.

---

## Why Build Inside Odoo (Instead of Using Grafana Directly)?

| Factor | Grafana Standalone | Dashboard in Odoo |
|---|---|---|
| **Unified platform** | Separate tool, separate login | Everything in one place |
| **Server records** | No CRUD for server management | Full lifecycle management |
| **AI integration** | Limited | Deep integration with AI chat and analysis |
| **Approval workflow** | Not possible | Built into Odoo |
| **Access control** | Separate user management | Odoo's built-in access rights |
| **Customization** | Dashboard customization only | Full application customization |
| **SaaS tracking** | Manual setup | Integrated with server data |
| **Reporting** | Limited | Odoo's full reporting engine |

You get the **visualization power** of Grafana with the **business logic** of Odoo.

---

## Dashboard Component Architecture

### Odoo 19 (OWL Framework)

```
┌──────────────────────────────────────────────────────────────┐
│  ServerDashboard (OWL Component - Main)                      │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  DashboardHeader                                         ││
│  │  - Title, time range selector, refresh button            ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐│
│  │ StatsCard    │ │ StatsCard    │ │ StatsCard            ││
│  │ Total: 48    │ │ Active: 39   │ │ Alerts: 5            ││
│  └──────────────┘ └──────────────┘ └──────────────────────┘│
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  ServerGrid (Clickable server cards)                     ││
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         ││
│  │  │ SRV1 │ │ SRV2 │ │ SRV3 │ │ SRV4 │ │ SRV5 │         ││
│  │  │ 45%  │ │ 82%  │ │ 12%  │ │ DOWN │ │ 67%  │         ││
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘         ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────┐ ┌────────────────────────────┐│
│  │  LineChart (CPU Trends)  │ │ LineChart (RAM Trends)     ││
│  │  [Chart.js canvas]       │ │ [Chart.js canvas]          ││
│  └──────────────────────────┘ └────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────┐ ┌────────────────────────────┐│
│  │  GaugeChart (Disk Usage) │ │ AlertList (Recent Alerts)  ││
│  │  [Chart.js doughnut]     │ │ - PROD-DB-03: Disk 94%    ││
│  └──────────────────────────┘ │ - PROD-WEB-05: CPU 91%    ││
│                                └────────────────────────────┘│
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  AIInsights (AI-generated insights panel)                ││
│  │  "3 servers idle > 7 days. SRV-DB-03 disk critical."    ││
│  └─────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

### Odoo 14 (Legacy Widget Framework)

Same layout, but implemented using:
- `Widget` class instead of OWL Component
- `QWeb` templates instead of OWL templates
- `ajax.rpc` for data fetching instead of OWL services
- Same Chart.js library for charts

---

## Dashboard Data Flow

```
┌─────────────┐    ┌──────────────────┐    ┌────────────────┐
│  Dashboard  │    │  Odoo Controller │    │  Odoo Models   │
│  (Browser)  │    │  (Python)        │    │  (PostgreSQL)  │
│             │    │                  │    │                │
│  On Load:   │───>│ GET /dashboard/  │───>│ server.server  │
│  fetch data │    │     data         │    │ server.metric  │
│             │<───│                  │<───│ server.alert   │
│  Render     │    │  Returns JSON:   │    │                │
│  charts     │    │  {servers: [...],│    │                │
│             │    │   metrics: [...],│    │                │
│  Every 30s: │    │   alerts: [...]} │    │                │
│  re-fetch   │───>│                  │───>│                │
│  update     │<───│                  │<───│                │
└─────────────┘    └──────────────────┘    └────────────────┘
```

---

## API Endpoints for Dashboard

### `GET /api/v1/dashboard/overview`

Returns the summary data for the main dashboard.

```json
{
  "summary": {
    "total_servers": 48,
    "active": 39,
    "idle": 5,
    "underutilized": 3,
    "down": 1,
    "active_alerts": 5,
    "critical_alerts": 2
  },
  "servers": [
    {
      "id": 1,
      "name": "PROD-WEB-01",
      "ip": "10.0.1.10",
      "category": "Web Server",
      "monitoring_state": "healthy",
      "cpu_current": 45.2,
      "ram_current": 68.5,
      "disk_current": 42.0,
      "ai_classification": "active",
      "ai_health_score": 87,
      "last_seen": "2026-02-20T10:29:30Z",
      "alert_count": 0
    },
    ...
  ],
  "recent_alerts": [
    {
      "id": 101,
      "server_name": "PROD-DB-03",
      "alert_type": "disk_full",
      "severity": "critical",
      "message": "Disk usage at 94%",
      "triggered_at": "2026-02-20T09:15:00Z"
    },
    ...
  ],
  "ai_insights": [
    "3 servers have been idle for more than 7 days",
    "PROD-DB-03 disk will be full in approximately 3 days",
    "Overall fleet CPU utilization is 62% — healthy range"
  ]
}
```

### `GET /api/v1/dashboard/server/<id>/metrics`

Returns time-series metrics for a specific server.

```json
{
  "server": {"id": 42, "name": "PROD-WEB-01"},
  "period": "24h",
  "metrics": {
    "cpu": {
      "data": [
        {"t": "2026-02-19T10:30:00Z", "v": 45.2},
        {"t": "2026-02-19T10:31:00Z", "v": 47.8},
        ...
      ],
      "avg": 52.3,
      "max": 94.1,
      "min": 12.3
    },
    "ram": {
      "data": [...],
      "avg": 68.5,
      "max": 81.2,
      "min": 65.0
    },
    "disk": {
      "data": [...],
      "current": 45.0,
      "trend_daily": 0.2
    },
    "network": {
      "in": {"data": [...], "avg_mbps": 120.5},
      "out": {"data": [...], "avg_mbps": 85.3}
    }
  }
}
```

---

## Chart Types Used

### 1. Line Chart — Metric Trends Over Time

**Use for**: CPU, RAM, Network bandwidth over time

```
Chart.js Configuration Concept:
  type: 'line'
  data: time-series from API
  options:
    - Smooth curves (tension: 0.3)
    - Fill area under line (fill: true, with gradient)
    - Tooltip showing exact value + time
    - Multiple datasets (overlay servers or metrics)
    - Time scale on X-axis (auto-formatted)
    - Responsive
```

### 2. Doughnut/Gauge — Current Values

**Use for**: Current CPU %, RAM %, Disk % for a single server

```
Chart.js Configuration Concept:
  type: 'doughnut'
  data: [used, free]
  options:
    - Color: green (<70%), yellow (70-90%), red (>90%)
    - Center text showing percentage
    - Animated on load
```

### 3. Bar Chart — Comparison

**Use for**: Comparing CPU usage across all servers

```
Chart.js Configuration Concept:
  type: 'bar'
  data: one bar per server
  options:
    - Horizontal bars
    - Color-coded by health status
    - Sorted by value (highest first)
    - Click to navigate to server detail
```

### 4. Stacked Area — Resource Breakdown

**Use for**: Per-core CPU usage, per-disk usage

```
Chart.js Configuration Concept:
  type: 'line'
  data: multiple datasets stacked
  options:
    - fill: 'origin' or stack
    - Different colors per core/disk
```

### 5. Heatmap — Fleet Overview (ECharts)

**Use for**: Overview of all servers, all metrics at once

```
ECharts Configuration Concept:
  type: 'heatmap'
  x-axis: servers
  y-axis: metrics (CPU, RAM, Disk, Network)
  color: green → yellow → red based on value
```

---

## Real-Time Updates

### Option 1: Polling (Simple, Recommended)

```
Every 30 seconds:
  Browser → GET /api/v1/dashboard/overview → Update charts

Pros: Simple, works everywhere
Cons: 30-second delay, unnecessary requests if no changes
```

### Option 2: Long Polling (Medium)

```
Browser → GET /api/v1/dashboard/stream (waits for new data)
Server holds connection until new data arrives → responds immediately

Pros: Near real-time, fewer requests
Cons: More complex server-side
```

### Option 3: WebSocket (Advanced)

```
Browser ↔ WebSocket ↔ Odoo
Server pushes updates the instant new metrics arrive

Pros: True real-time, minimal latency
Cons: Most complex, requires WebSocket support in Odoo
Note: Odoo has built-in bus/longpolling service that can be leveraged
```

### Recommendation

Start with **polling** (Option 1). It's simple and works perfectly for 30-60 second metric intervals. Upgrade to WebSocket later if you need sub-second updates.

---

## Individual Server Detail Page

When you click a server card on the dashboard, you see a detailed view:

```
┌─────────────────────────────────────────────────────────────────┐
│  PROD-WEB-01                                    [Edit] [Alerts]│
│  10.0.1.10 | Ubuntu 22.04 | 8 cores, 16GB RAM                │
│  Status: ● Active | Health Score: 87/100 | Uptime: 45 days    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ CPU      │ │ RAM      │ │ Disk     │ │ Network  │         │
│  │  [Gauge] │ │  [Gauge] │ │  [Gauge] │ │  [Gauge] │         │
│  │   67%    │ │   72%    │ │   45%    │ │ 120Mb/s  │         │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘         │
│                                                                 │
│  Time Range: [1h] [6h] [24h] [7d] [30d] [Custom]              │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  CPU Usage Over Time                                       │ │
│  │  [Line chart with per-core breakdown option]               │ │
│  │  avg: 67% | min: 12% | max: 94% | p95: 89%               │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Memory Usage Over Time                                    │ │
│  │  [Line chart]                                              │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Disk Usage & I/O                                          │ │
│  │  [Combined: disk % line + I/O bar chart]                   │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Network Traffic                                           │ │
│  │  [Stacked area: inbound + outbound]                        │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌────────────────────────────┐ ┌────────────────────────────┐ │
│  │  AI Analysis               │ │  Recent Alerts             │ │
│  │                            │ │                            │ │
│  │  Classification: Active    │ │  Feb 20: CPU > 90% (15m)  │ │
│  │  Health Score: 87/100      │ │  Feb 18: CPU > 90% (8m)   │ │
│  │                            │ │  Feb 15: Disk > 85%       │ │
│  │  "Server is actively used  │ │                            │ │
│  │  with moderate to high CPU │ │  [View All Alerts]         │ │
│  │  load. CPU spikes during   │ │                            │ │
│  │  business hours suggest    │ │                            │ │
│  │  regular workload."        │ │                            │ │
│  └────────────────────────────┘ └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## AI Chat Panel

The AI Chat can be a sidebar panel accessible from any page:

```
┌──────────────────────────────────────┐
│  AI Assistant                    [X] │
├──────────────────────────────────────┤
│                                      │
│  ┌──────────────────────────────┐   │
│  │ You: Which servers are using  │   │
│  │ the most CPU right now?       │   │
│  └──────────────────────────────┘   │
│                                      │
│  ┌──────────────────────────────┐   │
│  │ AI: Top 5 servers by CPU:     │   │
│  │                               │   │
│  │ 1. PROD-WEB-05: 91.2%       │   │
│  │ 2. PROD-APP-03: 84.7%       │   │
│  │ 3. PROD-WEB-02: 78.3%       │   │
│  │ 4. PROD-DB-01:  72.1%       │   │
│  │ 5. DEV-APP-01:  65.4%       │   │
│  │                               │   │
│  │ PROD-WEB-05 has been above   │   │
│  │ 90% for 2 hours. Consider    │   │
│  │ investigating or scaling.     │   │
│  └──────────────────────────────┘   │
│                                      │
│  Suggested questions:                │
│  • "Show idle servers"               │
│  • "Monthly cost summary"            │
│  • "Compare SRV-01 vs SRV-02"       │
│                                      │
│  ┌──────────────────────┐ [Send]    │
│  │ Type your question... │           │
│  └──────────────────────┘           │
└──────────────────────────────────────┘
```

---

## Frontend Technology Details

### Odoo 19 (OWL)

```
Component hierarchy:
  ServerDashboard (action component, registered in action registry)
  ├── DashboardHeader (time range, refresh)
  ├── StatsCards (summary numbers)
  ├── ServerGrid (server cards with status)
  ├── MetricChart (wrapper around Chart.js)
  │   ├── Uses useEffect() to initialize Chart.js
  │   └── Re-renders on data change
  ├── AlertList (recent alerts)
  ├── AIInsights (AI panel)
  └── AIChatSidebar (slide-over chat panel)

Data fetching:
  Uses Odoo's rpc service (this.rpc('/api/v1/dashboard/overview'))
  Or ORM service (this.orm.searchRead('server.server', ...))
  
Auto-refresh:
  setInterval in onMounted() lifecycle hook
```

### Odoo 14 (Legacy Widgets)

```
Widget hierarchy:
  ServerDashboardAction (AbstractAction)
  ├── extends AbstractAction
  ├── template: 'ServerDashboard'
  ├── Renders sub-widgets in start()
  ├── Uses ajax.rpc for data fetching
  └── Chart.js initialized in start() or renderElement()

Registration:
  core.action_registry.add('server_dashboard', ServerDashboardAction)

XML menu action:
  <record model="ir.actions.client">
    <field name="name">Server Dashboard</field>
    <field name="tag">server_dashboard</field>
  </record>
```

### Chart.js Integration (Both Versions)

```
Module assets (in __manifest__.py):
  'assets': {
      'web.assets_backend': [
          'server_monitoring/static/lib/chart.js/chart.min.js',
          'server_monitoring/static/src/js/dashboard.js',
          'server_monitoring/static/src/css/dashboard.css',
          'server_monitoring/static/src/xml/dashboard.xml',
      ],
  }
```

---

## Color Scheme & Design Tokens

For a professional, Grafana-like look:

| Element | Color | Hex |
|---|---|---|
| Background (dark theme) | Dark gray | #1a1a2e |
| Card background | Slightly lighter | #16213e |
| Healthy/Active | Green | #00b894 |
| Warning | Yellow/Orange | #fdcb6e |
| Critical/Down | Red | #e17055 |
| Idle | Blue/Gray | #74b9ff |
| Text primary | White | #ffffff |
| Text secondary | Light gray | #b2bec3 |
| Chart line 1 | Cyan | #00cec9 |
| Chart line 2 | Purple | #a29bfe |
| Chart line 3 | Pink | #fd79a8 |
| Chart line 4 | Green | #55efc4 |

### Light Theme Alternative

If you prefer light theme (matches Odoo's default):

| Element | Color | Hex |
|---|---|---|
| Background | White | #ffffff |
| Card background | Light gray | #f8f9fa |
| Healthy | Green | #28a745 |
| Warning | Orange | #ffc107 |
| Critical | Red | #dc3545 |
| Text | Dark gray | #343a40 |

---

## Performance Optimization

### Frontend
- Only fetch visible time range data (don't load 30 days if showing 1 hour)
- Use Chart.js `decimation` plugin for large datasets (> 1000 points)
- Lazy-load server detail charts (only when scrolled into view)
- Cache dashboard data on frontend (invalidate on refresh)

### Backend
- Use database indexes on `(server_id, metric_type, timestamp)`
- Pre-compute summary statistics during aggregation cron
- Use `read_group()` for aggregations instead of loading all records
- Limit metric data points per chart (max 500 points, downsample if needed)
- Use PostgreSQL `generate_series` for time-bucketed queries
