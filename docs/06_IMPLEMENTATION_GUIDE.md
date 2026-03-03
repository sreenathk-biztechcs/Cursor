# Step-by-Step Implementation Guide

## Implementation Phases

This is a large project. Break it into **6 phases**, each delivering working functionality.

---

## Phase 0: Prerequisites & Environment Setup (Week 1)

### What You Need Before Starting

| Requirement | Details |
|---|---|
| **Odoo 14 or 19 CE** | Running instance with admin access |
| **Python environment** | Access to install pip packages in Odoo's virtualenv |
| **At least 1 server** to monitor | Any Linux server you have access to |
| **A server for Prometheus** | Can be the same as Odoo for testing, separate for production |
| **OpenAI API key** | From https://platform.openai.com (add $10-20 credits) |
| **Cursor IDE** | For writing the module code |
| **Basic Odoo module knowledge** | How to create a module, define models, create views |

### Step 0.1: Set Up Development Environment

```bash
# Clone your Odoo instance or set up a new one
# For Odoo 14 CE:
git clone https://github.com/odoo/odoo.git -b 14.0 --depth 1

# For Odoo 19 CE:
git clone https://github.com/odoo/odoo.git -b 19.0 --depth 1

# Create a custom addons directory
mkdir -p /opt/odoo/custom-addons/server_monitoring

# Install required Python packages in Odoo's virtualenv
pip install openai requests prometheus-api-client
```

### Step 0.2: Install Node Exporter on Your First Test Server

Follow the instructions in `02_MONITORING_STACK_SETUP.md`, Part 1.

Verify it works:
```bash
curl http://your-server-ip:9100/metrics | head -5
# Should show metric lines
```

### Step 0.3: Install Prometheus

Follow the instructions in `02_MONITORING_STACK_SETUP.md`, Part 2.

Verify it works:
```bash
# Open http://prometheus-server:9090 in browser
# Go to Status → Targets
# Your server should show as "UP"
```

### Step 0.4: Verify OpenAI API Key

```python
import openai
client = openai.OpenAI(api_key='your-key-here')
response = client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[{"role": "user", "content": "Say hello"}]
)
print(response.choices[0].message.content)
```

---

## Phase 1: Core Odoo Module — Server Management (Week 2-3)

### Goal: Create and manage server records in Odoo

**What you build:**
- Server model with all fields
- Form view, tree view, kanban view
- Menu structure
- Security groups and access rules
- Server allocation workflow

### Step 1.1: Create Module Skeleton

Use Cursor to generate the `__manifest__.py` and basic model files:

```
Tell Cursor: "Create an Odoo [14/19] module called server_monitoring 
with __manifest__.py. The module should have models for server records 
with fields for hostname, IP, OS, CPU cores, RAM, disk, owner, department, 
status (draft/active/maintenance/decommissioned/inactive), health status 
(healthy/warning/critical/unknown/unreachable), and metric fields for 
CPU/RAM/disk/network usage."
```

### Step 1.2: Create Views

```
Tell Cursor: "Create form view, tree view, and kanban view for the 
server.monitoring.server model. The kanban view should show server name, 
IP, health status with color coding, and key metrics (CPU, RAM, disk)."
```

### Step 1.3: Create Allocation Model and Workflow

```
Tell Cursor: "Create the server.monitoring.allocation model with a 
request/approval workflow. States: draft, submitted, approved, allocated, 
rejected, returned. Include buttons for state transitions and 
appropriate security checks."
```

### Step 1.4: Test Phase 1

- Create 5-10 test server records manually
- Test the allocation workflow
- Verify menu structure and navigation
- Check security groups work correctly

### Deliverable: You can create/edit/manage server records and process allocation requests in Odoo.

---

## Phase 2: Prometheus Integration — Live Metrics (Week 3-4)

### Goal: Automatically collect metrics from Prometheus and update Odoo

**What you build:**
- Prometheus service class
- Metric collection cron job
- Metric snapshot model
- Health status auto-calculation
- Prometheus target file sync

### Step 2.1: Create Prometheus Service

```
Tell Cursor: "Create a Python service class for Prometheus API integration. 
It should have methods for instant_query, range_query, get_targets, 
get_server_metrics (CPU, RAM, disk, network, load, uptime), and 
is_server_up. Use the requests library. Handle errors gracefully."
```

### Step 2.2: Create Configuration Model

```
Tell Cursor: "Create a server.monitoring.config model (res.config.settings 
mixin) with fields for Prometheus URL, credentials, scrape interval, 
snapshot retention days. Add a Settings menu item."
```

### Step 2.3: Create Metric Collection Cron Job

```
Tell Cursor: "Create an ir.cron scheduled action that runs every 5 minutes. 
It should iterate over all active monitored servers, call Prometheus API 
for each server's metrics, update the server record, create a metric 
snapshot record, and calculate health status based on configurable thresholds."
```

### Step 2.4: Create Prometheus Target Sync

```
Tell Cursor: "When a server record is created, modified, or deleted in Odoo, 
automatically update the Prometheus file_sd targets JSON file so Prometheus 
starts/stops scraping the server."
```

### Step 2.5: Test Phase 2

- Add your real server IPs to Odoo
- Run the cron job manually
- Verify metrics appear in server records
- Check metric snapshot records are created
- Verify health status changes when metrics cross thresholds

### Deliverable: Server records show live metrics pulled from Prometheus every 5 minutes.

---

## Phase 3: Dashboard — Visualize Everything (Week 4-6)

### Goal: Build the Grafana-like dashboard inside Odoo

**What you build:**
- Client action dashboard
- ECharts integration
- KPI cards
- Line charts (CPU/RAM/Disk over time)
- Server health heatmap
- Server status cards
- Real-time refresh

### Step 3.1: Set Up Dashboard Client Action

```
Tell Cursor: "Create an Odoo [14/19] client action for the server monitoring 
dashboard. For Odoo 14, use AbstractAction.extend(). For Odoo 19, use an 
OWL component registered in the action registry. Include a backend controller 
at /api/monitoring/dashboard that returns all dashboard data as JSON."
```

### Step 3.2: Add ECharts Library

```bash
# Download ECharts
cd /opt/odoo/custom-addons/server_monitoring/static/lib/
mkdir echarts
wget https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js -O echarts/echarts.min.js
```

### Step 3.3: Build KPI Cards

```
Tell Cursor: "Add KPI summary cards to the dashboard showing total servers, 
healthy count, warning count, critical count, idle servers, active alerts, 
monthly cost, and AI fleet health score. Style them with appropriate colors."
```

### Step 3.4: Build Charts

```
Tell Cursor: "Add ECharts line charts for CPU and RAM usage over the last 6 hours 
for the top 5 busiest servers. Add a horizontal bar chart showing top 10 servers 
by CPU usage. Add a gauge chart for the overall fleet health score."
```

### Step 3.5: Build Server Cards

```
Tell Cursor: "Add a scrollable row of server status cards. Each card shows server 
name, IP, health indicator (colored dot), CPU/RAM/Disk progress bars, and the 
AI summary text. Clicking a card opens the server's form view."
```

### Step 3.6: Add Auto-Refresh

```
Tell Cursor: "Add a refresh button and auto-refresh mechanism (every 30 seconds) 
to the dashboard. When data is refreshed, update all charts and cards smoothly 
without full page reload."
```

### Step 3.7: Test Phase 3

- Open the dashboard
- Verify all KPI cards show correct data
- Verify charts render with real data
- Verify server cards are interactive
- Test auto-refresh
- Test on different screen sizes

### Deliverable: A beautiful, functional dashboard showing all server metrics with live charts.

---

## Phase 4: AI Integration — Automatic Intelligence (Week 6-8)

### Goal: AI analyzes everything automatically and provides insights

**What you build:**
- AI service class
- Automatic health analysis cron job
- Idle server detection
- Alert analysis
- AI chat widget
- Daily summary email

### Step 4.1: Create AI Service

```
Tell Cursor: "Create an AI service class that wraps OpenAI API calls. 
It should support analyze_server_health (single server), analyze_fleet 
(all servers), chat (conversational with context), and 
explain_alert (alert analysis). Use structured JSON output format. 
Support both OpenAI and Ollama (via base_url parameter)."
```

### Step 4.2: Create AI Health Analysis Cron Job

```
Tell Cursor: "Create a cron job that runs every 30 minutes. It collects 
recent metrics for all servers, sends them to the AI service in batches, 
and updates each server's ai_summary, ai_recommendation, ai_risk_score, 
and health_status fields. Create ai_analysis log records."
```

### Step 4.3: Create AI Chat Widget

For Odoo 14:
```
Tell Cursor: "Create a chat widget for Odoo 14 using Widget.extend(). 
It should be a panel on the right side of the dashboard with a message 
input, send button, and scrollable message history. Messages are sent 
via AJAX to /api/monitoring/ai_chat and responses are displayed in 
a chat bubble format."
```

For Odoo 19:
```
Tell Cursor: "Create an OWL component for AI chat in Odoo 19. 
Same functionality as above but using OWL reactive state, 
OWL templates, and the Odoo 19 service architecture."
```

### Step 4.4: Create Daily Summary Email

```
Tell Cursor: "Create a cron job that runs daily at 7 AM. It collects 
fleet-wide metrics, sends them to AI for a comprehensive daily summary, 
and emails the result to configured recipients using Odoo's mail 
templates. Include sections for critical issues, warnings, idle servers, 
and top recommendations."
```

### Step 4.5: Add AI to Dashboard

```
Tell Cursor: "Add the AI summary section to the dashboard header 
(showing fleet summary text from AI). Add AI recommendations section.
Integrate the AI chat widget as a collapsible panel on the dashboard."
```

### Step 4.6: Test Phase 4

- Trigger AI analysis manually and verify results
- Check that AI summaries appear on server records
- Test the AI chat with various questions
- Verify the daily summary email
- Check AI analysis logs for correctness
- Test with Ollama as an alternative to OpenAI

### Deliverable: AI automatically analyzes server health, provides recommendations, and answers questions via chat.

---

## Phase 5: Alerts & Notifications (Week 8-9)

### Goal: Receive and manage alerts from Prometheus in Odoo

**What you build:**
- Alert webhook controller
- Alert model and views
- Alert notification system
- AI-powered alert analysis
- Odoo activity/notification integration

### Step 5.1: Create Alert Webhook

```
Tell Cursor: "Create an Odoo controller that receives Alertmanager webhook 
payloads at /api/monitoring/alert_webhook. Parse the alerts, match them 
to server records by IP address, create alert records, and trigger AI 
analysis for critical alerts. Include webhook secret verification."
```

### Step 5.2: Create Alert Views

```
Tell Cursor: "Create tree view and form view for server.monitoring.alert. 
The tree view should show alert name, server, severity (with color), 
state, start time, and duration. Include filters for active/resolved/acknowledged. 
Add an 'Acknowledge' button."
```

### Step 5.3: Add Alert Integration to Dashboard

```
Tell Cursor: "Add an 'Active Alerts' section to the dashboard showing 
currently firing alerts with severity indicators. Include a count badge 
in the navigation menu."
```

### Step 5.4: Configure Alertmanager

Update your Alertmanager configuration to send webhooks to Odoo (see `02_MONITORING_STACK_SETUP.md`, Part 3).

### Step 5.5: Test Phase 5

- Simulate a high CPU situation on a test server
- Verify alert appears in Prometheus, then in Odoo
- Check AI analysis of the alert
- Test acknowledgement workflow
- Verify alert resolves when the condition clears

### Deliverable: Alerts from Prometheus automatically appear in Odoo with AI-powered analysis.

---

## Phase 6: Reports, Optimization & Polish (Week 9-11)

### Goal: Add reports, optimize performance, and polish the UI

**What you build:**
- Server utilization reports
- Idle server report
- Cost analysis
- Data retention/cleanup jobs
- Performance optimization
- UI polish and responsive design

### Step 6.1: Reports

```
Tell Cursor: "Create QWeb report templates for:
1. Server Utilization Report — shows metrics summary for each server over a date range
2. Idle Server Report — lists servers flagged as idle with AI recommendations
3. Monthly Cost Report — summarizes cloud costs by department/owner"
```

### Step 6.2: Data Retention

```
Tell Cursor: "Create a cron job that runs daily to clean up old metric 
snapshots. Keep 5-minute resolution for 7 days, aggregate to hourly 
averages for 30 days, then daily averages for 1 year. Delete anything 
older than retention period."
```

### Step 6.3: Performance Optimization

Key optimizations:
- Add database indexes on `server_id`, `timestamp` for metric snapshots
- Use `read_group` for dashboard aggregations instead of loading all records
- Batch Prometheus API calls where possible
- Cache AI responses for unchanged metrics
- Use Odoo's `@api.model` caching where appropriate

### Step 6.4: UI Polish

- Add loading spinners while data loads
- Add error handling with user-friendly messages
- Make dashboard responsive for mobile/tablet
- Add dark mode support
- Add server detail drill-down from dashboard
- Add keyboard shortcuts (R = refresh, / = search)

---

## Phase Summary

| Phase | What You Get | Duration |
|---|---|---|
| **Phase 0** | Environment set up, monitoring stack running | 1 week |
| **Phase 1** | Server records and allocation workflow in Odoo | 1-2 weeks |
| **Phase 2** | Live metrics from Prometheus flowing into Odoo | 1-2 weeks |
| **Phase 3** | Beautiful Grafana-like dashboard in Odoo | 2-3 weeks |
| **Phase 4** | AI-powered automatic analysis and chat | 2-3 weeks |
| **Phase 5** | Alert management integrated with Prometheus | 1-2 weeks |
| **Phase 6** | Reports, optimization, production-ready polish | 2-3 weeks |
| **Total** | **Full system** | **~10-14 weeks** |

---

## Deployment Considerations

### For Testing / Development

```
┌─────────────────────────────────────┐
│ Single Machine (Your Laptop/VM)      │
│                                      │
│  - Odoo 14 or 19                    │
│  - Prometheus + Node Exporter        │
│  - Grafana (optional)               │
│  - Ollama (for free AI)             │
│                                      │
│  Perfect for development & demo      │
└─────────────────────────────────────┘
```

### For Production

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Odoo Server   │  │ Monitoring   │  │ AI Server    │
│               │  │ Server       │  │ (optional)   │
│ - Odoo 14/19  │  │              │  │              │
│ - PostgreSQL  │  │ - Prometheus │  │ - Ollama     │
│ - Nginx proxy │  │ - Grafana    │  │ - GPU        │
│               │  │ - Alertmgr   │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
        │                │                  │
        └────────────────┼──────────────────┘
                         │
              ┌──────────┴──────────┐
              │ Your Servers (N)     │
              │ - Node Exporter      │
              └─────────────────────┘
```

### Docker Deployment (Alternative)

You can run the monitoring stack in Docker:

```yaml
# docker-compose.yml for monitoring stack
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./targets:/etc/prometheus/targets
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ALLOW_EMBEDDING=true
      - GF_AUTH_ANONYMOUS_ENABLED=true

  alertmanager:
    image: prom/alertmanager:latest
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml

volumes:
  prometheus_data:
```

---

## Troubleshooting Guide

| Problem | Cause | Solution |
|---|---|---|
| Node Exporter not showing metrics | Service not running | `systemctl status node_exporter` |
| Prometheus shows target as DOWN | Firewall blocking port 9100 | Open port 9100 from Prometheus IP |
| Odoo can't reach Prometheus API | Network/firewall issue | Test with `curl http://prometheus:9090/api/v1/query?query=up` from Odoo server |
| Metrics not updating in Odoo | Cron job not running | Check Odoo cron job logs, run manually |
| AI analysis returns error | Invalid API key or rate limit | Check API key, check OpenAI status page |
| Dashboard not loading | JS errors | Check browser console (F12), check asset compilation |
| Charts not rendering | ECharts not loaded | Verify echarts.min.js is in static/lib and declared in manifest |
| Metric snapshots growing too fast | No cleanup job | Verify the retention cron job runs daily |
| Slow dashboard load | Too many records | Add database indexes, use read_group, paginate |
| Alert webhook not receiving | Wrong URL or auth | Check Alertmanager config, test with curl |
