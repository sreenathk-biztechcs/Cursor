# Odoo Custom Module Design — Server Monitoring & Management

## Module Name: `server_monitoring`

This document defines the complete Odoo custom module for managing servers, displaying live metrics, and integrating AI analysis.

---

## Part 1: Module Structure

```
server_monitoring/
├── __init__.py
├── __manifest__.py
├── security/
│   ├── ir.model.access.csv
│   └── security_groups.xml
├── models/
│   ├── __init__.py
│   ├── server.py                    # Main server record
│   ├── server_metric_snapshot.py    # Point-in-time metric snapshots
│   ├── server_allocation.py         # Request/approval workflow
│   ├── monitoring_config.py         # Prometheus/AI configuration
│   ├── ai_analysis.py              # AI analysis logs
│   ├── ai_chat_message.py          # AI chat history
│   └── alert.py                    # Alert records from Prometheus
├── views/
│   ├── server_views.xml
│   ├── server_allocation_views.xml
│   ├── alert_views.xml
│   ├── ai_analysis_views.xml
│   ├── monitoring_config_views.xml
│   ├── dashboard_action.xml         # Dashboard client action
│   └── menu.xml
├── controllers/
│   ├── __init__.py
│   ├── alert_webhook.py            # Receives alerts from Alertmanager
│   ├── api.py                      # REST API endpoints
│   └── ai_chat.py                  # AI chat endpoint
├── wizards/
│   ├── __init__.py
│   ├── server_bulk_import.py       # Bulk import servers
│   └── ai_query_wizard.py         # AI query dialog
├── data/
│   ├── cron_jobs.xml               # Scheduled actions
│   ├── mail_templates.xml          # Email templates
│   └── default_data.xml           # Default configurations
├── static/
│   ├── src/
│   │   ├── js/
│   │   │   ├── dashboard.js        # Main dashboard (Odoo 14: Widget / Odoo 19: OWL)
│   │   │   ├── charts.js           # Chart rendering (ECharts/Chart.js)
│   │   │   ├── ai_chat_widget.js   # AI chat panel
│   │   │   └── server_card.js      # Server status card component
│   │   ├── css/
│   │   │   └── dashboard.css       # Dashboard styles
│   │   └── xml/
│   │       ├── dashboard_template.xml    # Dashboard HTML templates
│   │       └── ai_chat_template.xml     # Chat widget template
│   └── description/
│       ├── icon.png
│       └── index.html
└── services/
    ├── __init__.py
    ├── prometheus_service.py        # Prometheus API client
    ├── ai_service.py               # OpenAI / LLM service
    └── metric_collector.py         # Orchestrates data collection
```

---

## Part 2: Data Models (Database Tables)

### Model 1: `server.monitoring.server` — The Main Server Record

This is the central model. Every server you manage gets a record here.

```
┌─────────────────────────────────────────────────────────────────┐
│                   server.monitoring.server                        │
├─────────────────────────────────────────────────────────────────┤
│ FIELD                 │ TYPE        │ DESCRIPTION                │
├───────────────────────┼─────────────┼────────────────────────────┤
│ name                  │ Char        │ Server hostname/name       │
│ ip_address            │ Char        │ IP address                 │
│ ip_address_internal   │ Char        │ Internal/private IP        │
│ fqdn                  │ Char        │ Fully qualified domain     │
│ port                  │ Integer     │ Node Exporter port (9100)  │
│                       │             │                            │
│ # Server Details      │             │                            │
│ os_type               │ Selection   │ linux/windows/macos        │
│ os_version            │ Char        │ Ubuntu 22.04, CentOS 8... │
│ cpu_cores             │ Integer     │ Number of CPU cores        │
│ ram_total_gb          │ Float       │ Total RAM in GB            │
│ disk_total_gb         │ Float       │ Total disk in GB           │
│ purpose               │ Char        │ What the server is for     │
│ description           │ Text        │ Detailed description       │
│ tags                  │ Many2many   │ server.monitoring.tag      │
│                       │             │                            │
│ # Ownership           │             │                            │
│ department_id         │ Many2one    │ hr.department              │
│ owner_id              │ Many2one    │ res.users                  │
│ team_ids              │ Many2many   │ res.users (team members)   │
│                       │             │                            │
│ # Location            │             │                            │
│ datacenter            │ Char        │ Data center name           │
│ rack_number           │ Char        │ Physical rack location     │
│ cloud_provider        │ Selection   │ on-premise/aws/azure/gcp   │
│ cloud_region          │ Char        │ Cloud region (us-east-1)   │
│ cloud_instance_type   │ Char        │ Instance type (t3.medium)  │
│                       │             │                            │
│ # Status & Health     │             │                            │
│ state                 │ Selection   │ draft/active/maintenance/  │
│                       │             │ decommissioned/inactive    │
│ health_status         │ Selection   │ healthy/warning/critical/  │
│                       │             │ unknown/unreachable        │
│ is_monitored          │ Boolean     │ Is Prometheus monitoring?  │
│ last_seen             │ Datetime    │ Last successful scrape     │
│ uptime_seconds        │ Float       │ Current uptime             │
│                       │             │                            │
│ # Latest Metrics      │             │                            │
│ cpu_usage_percent     │ Float       │ Current CPU %              │
│ ram_usage_percent     │ Float       │ Current RAM %              │
│ disk_usage_percent    │ Float       │ Current disk %             │
│ network_in_mbps       │ Float       │ Network incoming Mbps      │
│ network_out_mbps      │ Float       │ Network outgoing Mbps      │
│ load_average_1m       │ Float       │ 1-minute load average      │
│ load_average_5m       │ Float       │ 5-minute load average      │
│ load_average_15m      │ Float       │ 15-minute load average     │
│ process_count         │ Integer     │ Running processes          │
│                       │             │                            │
│ # AI Fields           │             │                            │
│ ai_summary            │ Text        │ AI-generated status summary│
│ ai_recommendation     │ Text        │ AI-generated recommendation│
│ ai_risk_score         │ Float       │ AI risk score (0-100)      │
│ ai_last_analysis      │ Datetime    │ When AI last analyzed      │
│                       │             │                            │
│ # Relations           │             │                            │
│ metric_snapshot_ids   │ One2many    │ Historical metric snapshots│
│ allocation_ids        │ One2many    │ Allocation requests        │
│ alert_ids             │ One2many    │ Alert history              │
│ ai_analysis_ids       │ One2many    │ AI analysis history        │
│                       │             │                            │
│ # Computed            │             │                            │
│ is_idle               │ Boolean     │ Computed: CPU < 5% for 7d  │
│ days_since_last_login │ Integer     │ Computed from metrics      │
│ cost_per_month        │ Float       │ Monthly cost (cloud)       │
│ metric_count          │ Integer     │ Count of snapshots         │
│ active_alerts_count   │ Integer     │ Count of open alerts       │
└───────────────────────┴─────────────┴────────────────────────────┘
```

### Model 2: `server.monitoring.metric.snapshot` — Historical Metrics

Stores periodic snapshots of server metrics (every 5 minutes from Prometheus).

```
┌─────────────────────────────────────────────────────────────────┐
│              server.monitoring.metric.snapshot                    │
├─────────────────────────────────────────────────────────────────┤
│ FIELD                 │ TYPE        │ DESCRIPTION                │
├───────────────────────┼─────────────┼────────────────────────────┤
│ server_id             │ Many2one    │ Link to server record      │
│ timestamp             │ Datetime    │ When metrics were captured │
│ cpu_usage_percent     │ Float       │ CPU usage at that moment   │
│ ram_usage_percent     │ Float       │ RAM usage                  │
│ ram_used_bytes        │ Float       │ RAM bytes used             │
│ disk_usage_percent    │ Float       │ Disk usage                 │
│ disk_used_bytes       │ Float       │ Disk bytes used            │
│ network_in_bytes      │ Float       │ Network received bytes/s   │
│ network_out_bytes     │ Float       │ Network transmitted bytes/s│
│ load_average_1m       │ Float       │ 1-min load average         │
│ load_average_5m       │ Float       │ 5-min load average         │
│ load_average_15m      │ Float       │ 15-min load average        │
│ process_count         │ Integer     │ Running processes          │
│ io_read_bytes         │ Float       │ Disk read bytes/sec        │
│ io_write_bytes        │ Float       │ Disk write bytes/sec       │
│ raw_data              │ Text/JSON   │ Full raw JSON from Prom    │
└───────────────────────┴─────────────┴────────────────────────────┘
```

**Note:** This table grows fast. Implement automatic cleanup: keep 5-min snapshots for 7 days, then aggregate to hourly for 30 days, then daily for 1 year.

### Model 3: `server.monitoring.allocation` — Server Request & Approval Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│              server.monitoring.allocation                         │
├─────────────────────────────────────────────────────────────────┤
│ FIELD                 │ TYPE        │ DESCRIPTION                │
├───────────────────────┼─────────────┼────────────────────────────┤
│ name                  │ Char        │ Auto-generated sequence    │
│ server_id             │ Many2one    │ Server being allocated     │
│ requester_id          │ Many2one    │ Who requested (res.users)  │
│ approver_id           │ Many2one    │ Who approves (res.users)   │
│ department_id         │ Many2one    │ Requesting department      │
│ purpose               │ Text        │ Why the server is needed   │
│ specs_required        │ Text        │ Required specs (CPU, RAM)  │
│ duration              │ Selection   │ temporary/permanent        │
│ end_date              │ Date        │ If temporary              │
│ state                 │ Selection   │ draft/submitted/approved/  │
│                       │             │ allocated/rejected/returned│
│ date_submitted        │ Datetime    │ When submitted             │
│ date_approved         │ Datetime    │ When approved              │
│ date_allocated        │ Datetime    │ When server was assigned   │
│ date_returned         │ Datetime    │ When server was returned   │
│ notes                 │ Text        │ Additional notes           │
│ ai_recommendation     │ Text        │ AI suggestion for best fit │
└───────────────────────┴─────────────┴────────────────────────────┘
```

**Workflow:**
```
Draft → Submitted → Approved → Allocated → (In Use) → Returned
                  ↘ Rejected
```

### Model 4: `server.monitoring.alert` — Alerts from Prometheus

```
┌─────────────────────────────────────────────────────────────────┐
│                server.monitoring.alert                            │
├─────────────────────────────────────────────────────────────────┤
│ FIELD                 │ TYPE        │ DESCRIPTION                │
├───────────────────────┼─────────────┼────────────────────────────┤
│ server_id             │ Many2one    │ Which server               │
│ alert_name            │ Char        │ Alert name (HighCPU, etc)  │
│ severity              │ Selection   │ info/warning/critical      │
│ state                 │ Selection   │ firing/resolved/acknowledged│
│ description           │ Text        │ Alert description          │
│ started_at            │ Datetime    │ When alert started firing  │
│ resolved_at           │ Datetime    │ When alert resolved        │
│ acknowledged_by       │ Many2one    │ Who acknowledged (res.users│
│ acknowledged_at       │ Datetime    │ When acknowledged          │
│ ai_analysis           │ Text        │ AI explanation of alert    │
│ ai_action_taken       │ Text        │ AI recommended action      │
│ raw_payload           │ Text        │ Raw JSON from Alertmanager │
└───────────────────────┴─────────────┴────────────────────────────┘
```

### Model 5: `server.monitoring.ai.analysis` — AI Analysis Log

```
┌─────────────────────────────────────────────────────────────────┐
│             server.monitoring.ai.analysis                        │
├─────────────────────────────────────────────────────────────────┤
│ FIELD                 │ TYPE        │ DESCRIPTION                │
├───────────────────────┼─────────────┼────────────────────────────┤
│ server_id             │ Many2one    │ Which server (optional)    │
│ analysis_type         │ Selection   │ health_check/anomaly/      │
│                       │             │ prediction/recommendation/ │
│                       │             │ fleet_overview             │
│ trigger               │ Selection   │ scheduled/alert/manual/    │
│                       │             │ threshold                  │
│ input_data            │ Text        │ What data was sent to AI   │
│ ai_response           │ Text        │ Full AI response           │
│ summary               │ Char        │ One-line summary           │
│ risk_score            │ Float       │ 0-100 risk score           │
│ recommendations       │ Text        │ Action items               │
│ model_used            │ Char        │ gpt-4o, llama3, etc       │
│ tokens_used           │ Integer     │ API tokens consumed        │
│ cost                  │ Float       │ Estimated API cost         │
│ created_at            │ Datetime    │ When analysis was done     │
└───────────────────────┴─────────────┴────────────────────────────┘
```

### Model 6: `server.monitoring.ai.chat` — AI Chat Messages

```
┌─────────────────────────────────────────────────────────────────┐
│              server.monitoring.ai.chat                            │
├─────────────────────────────────────────────────────────────────┤
│ FIELD                 │ TYPE        │ DESCRIPTION                │
├───────────────────────┼─────────────┼────────────────────────────┤
│ user_id               │ Many2one    │ Who is chatting            │
│ session_id            │ Char        │ Chat session identifier    │
│ role                  │ Selection   │ user/assistant/system      │
│ message               │ Text        │ The message content        │
│ context_server_ids    │ Many2many   │ Servers referenced         │
│ model_used            │ Char        │ AI model used              │
│ tokens_used           │ Integer     │ Tokens consumed            │
│ timestamp             │ Datetime    │ Message timestamp          │
└───────────────────────┴─────────────┴────────────────────────────┘
```

### Model 7: `server.monitoring.config` — System Configuration

```
┌─────────────────────────────────────────────────────────────────┐
│              server.monitoring.config                             │
├─────────────────────────────────────────────────────────────────┤
│ FIELD                 │ TYPE        │ DESCRIPTION                │
├───────────────────────┼─────────────┼────────────────────────────┤
│ prometheus_url        │ Char        │ http://prometheus:9090     │
│ prometheus_username    │ Char       │ Basic auth username        │
│ prometheus_password    │ Char       │ Basic auth password        │
│ grafana_url           │ Char        │ http://grafana:3000        │
│ grafana_api_key       │ Char        │ Grafana API key            │
│ scrape_interval_min   │ Integer     │ How often to pull metrics  │
│ snapshot_retention_days│ Integer    │ How long to keep snapshots │
│ ai_provider           │ Selection   │ openai/ollama/azure/local  │
│ ai_api_key            │ Char        │ OpenAI API key             │
│ ai_model              │ Char        │ gpt-4o, gpt-4o-mini, etc │
│ ai_base_url           │ Char        │ API base URL (for Ollama)  │
│ ai_auto_analysis      │ Boolean     │ Enable automatic analysis  │
│ ai_analysis_interval  │ Integer     │ Minutes between analyses   │
│ alert_webhook_secret  │ Char        │ Secret for webhook auth    │
│ idle_threshold_cpu    │ Float       │ CPU % below = idle (5%)    │
│ idle_threshold_days   │ Integer     │ Days idle before flagging  │
│ cpu_warning_threshold │ Float       │ CPU % for warning (80%)    │
│ cpu_critical_threshold│ Float       │ CPU % for critical (95%)   │
│ ram_warning_threshold │ Float       │ RAM % for warning (85%)    │
│ disk_warning_threshold│ Float       │ Disk % for warning (80%)   │
└───────────────────────┴─────────────┴────────────────────────────┘
```

---

## Part 3: Workflows

### Workflow 1: Server Lifecycle

```
                    ┌─────────┐
                    │  DRAFT  │ ← You create server record in Odoo
                    └────┬────┘
                         │ Install Node Exporter
                         │ Add to Prometheus
                         ▼
                    ┌─────────┐
                    │ ACTIVE  │ ← Prometheus scraping, metrics flowing
                    └────┬────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
       ┌─────────┐ ┌─────────┐ ┌───────────────┐
       │MAINTENAN│ │ INACTIVE│ │DECOMMISSIONED │
       │   CE    │ │(flagged │ │  (removed)    │
       │         │ │by AI as │ │               │
       │         │ │ idle)   │ │               │
       └────┬────┘ └────┬────┘ └───────────────┘
            │           │
            └─────┬─────┘
                  ▼
            ┌──────────┐
            │  ACTIVE  │ ← Back to active after maintenance/reallocation
            └──────────┘
```

### Workflow 2: Server Allocation (Request & Approval)

```
Employee                   Manager                    System/Admin
   │                          │                           │
   │ 1. Creates allocation    │                           │
   │    request in Odoo       │                           │
   │    (specs, purpose)      │                           │
   │                          │                           │
   │    ──── SUBMITTED ────►  │                           │
   │                          │                           │
   │                          │ 2. Reviews request        │
   │                          │                           │
   │                          │ AI suggests:              │
   │                          │ "Server-15 matches the    │
   │                          │  requirements and is      │
   │                          │  currently 90% idle"      │
   │                          │                           │
   │    ◄── APPROVED ──────   │                           │
   │    (or REJECTED)         │                           │
   │                          │                           │
   │                          │                           │ 3. System auto-allocates
   │                          │                           │    server, updates owner,
   │                          │                           │    sends notification
   │                          │                           │
   │    ◄── ALLOCATED ────────────────────────────────    │
   │    (Server details sent) │                           │
   │                          │                           │
   │ ... uses server ...      │                           │
   │                          │                           │
   │ 4. Returns server        │                           │
   │    ── RETURNED ──────────────────────────────►       │
   │                          │                           │ 5. Marks server available
```

### Workflow 3: Automatic Metric Collection (Cron Job)

```
Every 5 minutes (configurable):

1. Cron job triggers `_collect_all_metrics()`
2. For each active, monitored server:
   a. Build PromQL query
   b. Call Prometheus API: GET /api/v1/query
   c. Parse response
   d. Update server record with latest metrics
   e. Create metric_snapshot record
   f. Check thresholds → update health_status
   g. If health changed → trigger AI analysis
3. Clean up old snapshots (retention policy)
4. Log collection summary
```

### Workflow 4: AI Auto-Analysis (Cron Job)

```
Every 30 minutes (configurable):

1. Cron job triggers `_run_ai_analysis()`
2. Gather metrics for all servers (last 30 min)
3. Build AI prompt with structured data:
   ┌──────────────────────────────────────────────────┐
   │ SYSTEM PROMPT:                                    │
   │ You are a server infrastructure analyst.          │
   │ Analyze these server metrics and provide:         │
   │ 1. Health status for each server                  │
   │ 2. Servers that are idle/underutilized            │
   │ 3. Servers at risk of failure                     │
   │ 4. Cost optimization recommendations              │
   │ 5. Anomalies detected                            │
   │                                                   │
   │ DATA:                                             │
   │ [structured JSON of all server metrics]            │
   │                                                   │
   │ Respond in JSON format with structure:             │
   │ { servers: [...], overall_summary: ...,           │
   │   recommendations: [...], risk_score: ... }       │
   └──────────────────────────────────────────────────┘
4. Send to OpenAI API (or local LLM)
5. Parse AI response
6. Update each server's ai_summary, ai_recommendation, ai_risk_score
7. Create ai_analysis record
8. If any critical findings → create alert + send notification
```

### Workflow 5: AI Chat Interaction

```
User opens AI Chat panel in Odoo:

User: "Which servers have been idle this month?"

System:
1. Receives message via /api/monitoring/ai_chat endpoint
2. Queries Prometheus for CPU data of all servers over past 30 days
3. Builds context prompt:
   ┌─────────────────────────────────────────────────┐
   │ SYSTEM: You are an AI assistant for server       │
   │ management. You have access to the following     │
   │ real-time server data. Answer the user's         │
   │ question based on this data.                     │
   │                                                  │
   │ CONTEXT:                                         │
   │ - 47 total servers                               │
   │ - [metrics data for each server]                 │
   │                                                  │
   │ USER: Which servers have been idle this month?   │
   └─────────────────────────────────────────────────┘
4. Sends to OpenAI API
5. AI responds: "Based on the metrics data, 5 servers have
   been idle (< 5% avg CPU) this month:
   - Server-12 (web-dev-old): 2.1% avg CPU, 15% RAM
   - Server-18 (staging-v1): 1.8% avg CPU, 8% RAM
   - Server-22 (test-env): 3.2% avg CPU, 12% RAM
   - Server-31 (backup-old): 0.5% avg CPU, 4% RAM
   - Server-35 (demo-env): 1.1% avg CPU, 6% RAM
   
   Estimated monthly cost savings if decommissioned: $2,340
   Recommendation: Consolidate Server-12 and Server-18
   workloads onto Server-22."
6. Store message in ai_chat model
7. Return to user via WebSocket/AJAX
```

---

## Part 4: Menu Structure in Odoo

```
Server Monitoring (top-level menu)
├── Dashboard                    ← Client action → JS dashboard
├── Servers
│   ├── All Servers              ← List/Kanban view of all servers
│   ├── Active Servers           ← Filtered: state = active
│   ├── Idle Servers             ← Filtered: is_idle = True
│   ├── Critical Servers         ← Filtered: health = critical
│   └── Unreachable              ← Filtered: health = unreachable
├── Allocations
│   ├── Allocation Requests      ← All requests
│   ├── My Requests              ← Filtered by current user
│   └── Pending Approvals        ← Filtered: state = submitted
├── Alerts
│   ├── Active Alerts            ← Filtered: state = firing
│   ├── Alert History            ← All alerts
│   └── Alert Rules              ← Manage Prometheus alert rules
├── AI
│   ├── AI Chat                  ← AI chat interface
│   ├── AI Analysis Log          ← History of AI analyses
│   └── AI Recommendations       ← Current recommendations
├── Reports
│   ├── Server Utilization       ← Charts and reports
│   ├── Cost Analysis            ← Cloud cost tracking
│   ├── Capacity Planning        ← Trend predictions
│   └── Idle Server Report       ← Decommission candidates
└── Configuration
    ├── Monitoring Settings       ← Prometheus/AI config
    ├── Server Tags               ← Tag management
    ├── Alert Thresholds          ← Warning/critical levels
    └── AI Settings               ← AI model/provider settings
```

---

## Part 5: Security Groups & Access Control

```xml
<!-- Three access levels -->

1. Server Monitoring / User
   - Can view servers, dashboard, alerts
   - Can create allocation requests
   - Can use AI chat
   - Cannot modify server records or configuration

2. Server Monitoring / Manager
   - Everything User can do
   - Can approve/reject allocation requests
   - Can modify server records
   - Can acknowledge alerts
   - Can trigger AI analysis manually

3. Server Monitoring / Administrator
   - Everything Manager can do
   - Can modify configuration (Prometheus, AI settings)
   - Can create/delete servers
   - Can manage alert rules
   - Can view AI costs and usage
```

---

## Part 6: Cron Jobs (Scheduled Actions)

| Cron Job | Interval | Purpose |
|---|---|---|
| `Collect Server Metrics` | Every 5 min | Pull metrics from Prometheus, update server records |
| `AI Health Analysis` | Every 30 min | AI analyzes all server metrics, updates recommendations |
| `Clean Old Snapshots` | Daily | Remove old metric snapshots per retention policy |
| `Detect Idle Servers` | Daily | Flag servers idle for more than X days |
| `Sync Prometheus Targets` | Every 15 min | Update Prometheus target file when servers added/removed in Odoo |
| `Cost Calculation` | Daily | Calculate cloud costs for each server |
| `AI Fleet Summary` | Daily (morning) | Generate daily AI summary email of entire fleet |

---

## Part 7: Odoo 14 vs Odoo 19 Implementation Notes

### Backend (Python) — Mostly Identical

| Feature | Odoo 14 | Odoo 19 | Difference |
|---------|---------|---------|------------|
| Models | `models.Model` | `models.Model` | Same |
| Fields | Same API | Same API | Same |
| ORM methods | `create`, `write`, `search` | `create`, `write`, `search` | Same |
| Cron jobs | `ir.cron` XML | `ir.cron` XML | Same |
| Controllers | `http.Controller` | `http.Controller` | Same |
| `requests` lib | Works | Works | Same |
| JSON fields | Use `Text` + `json.loads` | Use `Json` field type | Odoo 17+ has `Json` field |

### Frontend (JavaScript) — Different Framework

**Odoo 14 (Legacy Web Client):**
```javascript
// Uses Widget.extend() pattern
odoo.define('server_monitoring.Dashboard', function (require) {
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var Dashboard = AbstractAction.extend({
        template: 'ServerMonitoringDashboard',
        start: function () {
            this._super.apply(this, arguments);
            this._loadDashboardData();
        },
        _loadDashboardData: function () {
            // RPC calls to backend
            this._rpc({ route: '/api/monitoring/dashboard' })
                .then(this._renderCharts.bind(this));
        },
        _renderCharts: function (data) {
            // Use ECharts or Chart.js here
        },
    });

    core.action_registry.add('server_monitoring_dashboard', Dashboard);
});
```

**Odoo 19 (OWL 2 Framework):**
```javascript
/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class ServerMonitoringDashboard extends Component {
    static template = "server_monitoring.Dashboard";

    setup() {
        this.rpc = useService("rpc");
        this.state = useState({ servers: [], loading: true });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        const data = await this.rpc("/api/monitoring/dashboard");
        this.state.servers = data.servers;
        this.state.loading = false;
        this.renderCharts(data);
    }

    renderCharts(data) {
        // Use ECharts or Chart.js here
    }
}

registry.category("actions").add("server_monitoring_dashboard", ServerMonitoringDashboard);
```

### Strategy: Shared Backend, Dual Frontend

```
server_monitoring/
├── models/          ← 100% shared between Odoo 14 and 19
├── controllers/     ← 100% shared (HTTP routes are same)
├── services/        ← 100% shared (Python logic is same)
├── views/           ← 95% shared (XML views are same)
├── static/src/js/
│   ├── v14/         ← Odoo 14 specific JS (Widget.extend)
│   └── v19/         ← Odoo 19 specific JS (OWL components)
└── __manifest__.py  ← Conditional asset loading based on version
```

**OR** maintain two separate modules with a shared Python package:

```
server_monitoring_base/    ← Shared Python models, services, controllers
server_monitoring_v14/     ← Odoo 14 frontend only
server_monitoring_v19/     ← Odoo 19 frontend only
```
