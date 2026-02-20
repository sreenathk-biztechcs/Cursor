# 02 — Implementation Roadmap

## Phase-by-Phase Plan to Build the Complete System

This roadmap breaks the entire project into 7 phases. Each phase is self-contained and delivers working functionality. You can stop after any phase and have a useful system.

---

## Timeline Overview

```
Phase 1 ──── Phase 2 ──── Phase 3 ──── Phase 4 ──── Phase 5 ──── Phase 6 ──── Phase 7
Server       Monitoring    Dashboard    AI           SaaS         AI Chat      Polish &
Registry     Agents        (Grafana-    Classification Tracking   & Full       Production
& Workflow   & Data        style)       & Alerts                  Automation
             Collection

Week 1-2     Week 3-4      Week 5-6     Week 7-8     Week 9-10    Week 11-12   Week 13-14
```

---

## Phase 1: Server Registry & Approval Workflow (Week 1-2)

### Goal
Build the Odoo custom module with server management models and approval workflow.

### What You Build
- Custom Odoo module: `server_monitoring`
- Server model with full lifecycle states
- Request → Approval → Allocation workflow
- Basic list/form/kanban views

### Tasks

| # | Task | Effort |
|---|---|---|
| 1.1 | Create Odoo module scaffold (`__manifest__.py`, `__init__.py`) | 1 hour |
| 1.2 | Define `server.server` model (name, IP, OS, specs, status, owner, etc.) | 3 hours |
| 1.3 | Define `server.category` model (Web Server, DB Server, App Server, etc.) | 1 hour |
| 1.4 | Define `server.request` model (request/approval workflow) | 3 hours |
| 1.5 | Create form, tree, kanban views for all models | 4 hours |
| 1.6 | Implement state machine: Draft → Requested → Approved → Allocated → Active → Inactive → Decommissioned | 3 hours |
| 1.7 | Add approval workflow with email notifications | 2 hours |
| 1.8 | Security: access rights and record rules | 2 hours |
| 1.9 | Menu items and navigation | 1 hour |
| 1.10 | Testing and refinement | 3 hours |

### Deliverable
A working Odoo module where you can create server records, request allocations, and track server lifecycle.

### Skills Needed
- Odoo module development (Python, XML views)
- Basic ORM knowledge

---

## Phase 2: Monitoring Agents & Data Collection (Week 3-4)

### Goal
Install monitoring agents on servers and build the data pipeline into Odoo.

### What You Build
- Monitoring agent deployment (Telegraf or custom Python)
- Odoo REST API endpoint to receive metrics
- `server.metric` model to store time-series data
- Cron job for periodic data collection
- SSH-based remote metric collection (alternative approach)

### Tasks

| # | Task | Effort |
|---|---|---|
| 2.1 | Define `server.metric` model (server_id, metric_type, value, timestamp) | 2 hours |
| 2.2 | Define `server.metric.type` model (CPU, RAM, Disk, Network, etc.) | 1 hour |
| 2.3 | Build REST API controller (`/api/v1/metrics`) to accept metric data via POST | 4 hours |
| 2.4 | API authentication (API key per server) | 2 hours |
| 2.5 | Install and configure Telegraf on 1-2 test servers | 3 hours |
| 2.6 | Configure Telegraf HTTP output to push to Odoo API | 2 hours |
| 2.7 | Alternative: Build custom Python agent with `psutil` | 4 hours |
| 2.8 | Alternative: SSH-based collection from Odoo server using `paramiko` | 4 hours |
| 2.9 | Build cron job to aggregate metrics (hourly/daily summaries) | 3 hours |
| 2.10 | Data retention policy (auto-delete metrics older than X days) | 2 hours |
| 2.11 | Auto-detect server status (active/inactive) based on metric flow | 2 hours |
| 2.12 | Testing with real servers | 4 hours |

### Deliverable
Metrics flowing from your servers into Odoo automatically every 30-60 seconds. You can see raw metric data in Odoo.

### Three Approaches (Pick One or Combine)

**Approach A: Agent Push (Recommended)**
```
[Server] → Telegraf → HTTP POST → [Odoo API] → [server.metric table]
```

**Approach B: Odoo Pull via SSH**
```
[Odoo Cron] → SSH to server → run commands → parse output → [server.metric table]
```

**Approach C: Prometheus Scraping**
```
[Server] → Node Exporter (port 9100) ← [Odoo Cron] scrapes → [server.metric table]
```

---

## Phase 3: Grafana-Style Dashboard in Odoo (Week 5-6)

### Goal
Build a dynamic, real-time dashboard inside Odoo that looks and feels like Grafana.

### What You Build
- Custom Odoo dashboard view using Chart.js
- Real-time metric visualization (CPU, RAM, Disk, Network graphs)
- Server health overview (grid of servers with status indicators)
- Drill-down from dashboard to individual server details
- Auto-refresh (polls Odoo API every 10-30 seconds)

### Tasks

| # | Task | Effort |
|---|---|---|
| 3.1 | Design dashboard layout (wireframe) | 2 hours |
| 3.2 | Create Odoo controller endpoints for dashboard data (JSON API) | 4 hours |
| 3.3 | Build main dashboard OWL component (v19) / Widget (v14) | 8 hours |
| 3.4 | Integrate Chart.js for line charts (CPU/RAM over time) | 4 hours |
| 3.5 | Build gauge widgets (current CPU %, RAM %, Disk %) | 3 hours |
| 3.6 | Build server grid (colored cards: green=healthy, red=down, yellow=warning) | 4 hours |
| 3.7 | Add time range selector (Last 1h, 6h, 24h, 7d, 30d) | 2 hours |
| 3.8 | Add auto-refresh mechanism (polling or WebSocket) | 3 hours |
| 3.9 | Individual server detail page with all metrics | 4 hours |
| 3.10 | Network topology visualization (optional) | 6 hours |
| 3.11 | Mobile-responsive layout | 3 hours |
| 3.12 | Testing and UI polish | 4 hours |

### Deliverable
A beautiful dashboard in Odoo that shows all server metrics in real-time with charts, gauges, and status cards — similar to Grafana but native to Odoo.

### Dashboard Layout Concept

```
┌─────────────────────────────────────────────────────────────────┐
│  Server Monitoring Dashboard          [1h] [6h] [24h] [7d]     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐       │
│  │ SRV1 │ │ SRV2 │ │ SRV3 │ │ SRV4 │ │ SRV5 │ │ SRV6 │       │
│  │  ●   │ │  ●   │ │  ●   │ │  ●   │ │  ●   │ │  ●   │       │
│  │ 45%  │ │ 82%  │ │ 12%  │ │ OFF  │ │ 67%  │ │  3%  │       │
│  │ CPU  │ │ CPU  │ │ CPU  │ │      │ │ CPU  │ │ CPU  │       │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘       │
│   Green    Yellow    Green     Red     Yellow   Green (idle?)  │
│                                                                 │
├─────────────────────────────────┬───────────────────────────────┤
│  CPU Usage (All Servers)        │  Memory Usage (All Servers)   │
│  ┌───────────────────────────┐  │  ┌───────────────────────────┐│
│  │    ╱╲    ╱╲              │  │  │  ──────────────           ││
│  │   ╱  ╲  ╱  ╲    ╱╲      │  │  │         ╱╲               ││
│  │──╱    ╲╱    ╲──╱  ╲──── │  │  │  ──────╱  ╲──────────── ││
│  │                          │  │  │                           ││
│  └───────────────────────────┘  │  └───────────────────────────┘│
├─────────────────────────────────┴───────────────────────────────┤
│  Active: 12  │  Inactive: 3  │  Warning: 2  │  Down: 1        │
├─────────────────────────────────────────────────────────────────┤
│  AI Insights:                                                   │
│  • Server SRV6 has been idle for 14 days — consider reclaiming │
│  • SRV2 CPU consistently above 80% — consider scaling up       │
│  • 3 servers have less than 10% disk space remaining           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 4: AI Classification & Alerts (Week 7-8)

### Goal
Add AI-powered automatic analysis of server health, usage classification, and alerting.

### What You Build
- AI agent that analyzes metrics and classifies server states
- Anomaly detection (sudden spikes, server down, disk filling up)
- Automatic alerting via email/Odoo Discuss
- AI-generated insights on the dashboard
- Scheduled AI analysis (runs every hour)

### Tasks

| # | Task | Effort |
|---|---|---|
| 4.1 | Define `server.ai.analysis` model (stores AI analysis results) | 2 hours |
| 4.2 | Define `server.alert` model (alert type, severity, message, status) | 2 hours |
| 4.3 | Build AI analysis service (Python class using OpenAI/LangChain) | 6 hours |
| 4.4 | Implement server classification logic (Active / Idle / Underutilized / Overloaded / Down) | 4 hours |
| 4.5 | Build anomaly detection (statistical + AI-based) | 4 hours |
| 4.6 | Create alert rules engine (configurable thresholds) | 4 hours |
| 4.7 | Email notification for critical alerts | 2 hours |
| 4.8 | Odoo Discuss notification integration | 2 hours |
| 4.9 | AI Insights widget on dashboard | 3 hours |
| 4.10 | Cron job: Run AI analysis every hour | 2 hours |
| 4.11 | Alert dashboard (list of active alerts) | 3 hours |
| 4.12 | Testing with various scenarios | 4 hours |

### Deliverable
AI automatically classifies each server's status, detects anomalies, fires alerts, and provides insights — all without human intervention.

### AI Classification Logic

```
┌─────────────────────────────────────────────────────┐
│                AI Analysis Engine                     │
│                                                      │
│  Input: Last 24h of metrics for a server             │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │ Rule-Based Checks (Fast, No AI needed)       │    │
│  │                                               │    │
│  │ • No metrics for 30+ min → Status: DOWN      │    │
│  │ • CPU < 5% for 7+ days → Status: IDLE        │    │
│  │ • CPU > 90% for 1+ hour → Alert: OVERLOADED  │    │
│  │ • Disk > 90% → Alert: DISK_CRITICAL          │    │
│  │ • RAM > 95% → Alert: MEMORY_CRITICAL         │    │
│  └─────────────────────────────────────────────┘    │
│                      │                               │
│                      v                               │
│  ┌─────────────────────────────────────────────┐    │
│  │ AI-Based Analysis (Deep, Uses LLM)           │    │
│  │                                               │    │
│  │ • Trend analysis: "CPU rising 5% daily"      │    │
│  │ • Pattern detection: "Weekend spikes"         │    │
│  │ • Recommendations: "Scale up" / "Reclaim"    │    │
│  │ • Natural language summary of server health   │    │
│  └─────────────────────────────────────────────┘    │
│                                                      │
│  Output: Classification + Alerts + Insights          │
└─────────────────────────────────────────────────────┘
```

---

## Phase 5: SaaS Tool Tracking (Week 9-10)

### Goal
Track usage of external SaaS tools (Cursor IDE, ChatGPT Premium, and any future tool).

### What You Build
- Generic `saas.service` model (extensible for any SaaS tool)
- `saas.usage` model for tracking usage metrics
- API connectors for Cursor and ChatGPT
- Usage dashboards with cost tracking
- Cron jobs for periodic usage sync

### Tasks

| # | Task | Effort |
|---|---|---|
| 5.1 | Define `saas.service` model (name, type, API config, credentials) | 2 hours |
| 5.2 | Define `saas.usage` model (service_id, metric, value, date) | 2 hours |
| 5.3 | Build OpenAI/ChatGPT usage connector (API calls, tokens, costs) | 4 hours |
| 5.4 | Build Cursor usage connector | 4 hours |
| 5.5 | Build generic API connector framework (for future services) | 4 hours |
| 5.6 | SaaS usage dashboard widgets | 4 hours |
| 5.7 | Cost tracking and budget alerts | 3 hours |
| 5.8 | Per-user/per-team usage breakdown | 3 hours |
| 5.9 | Cron jobs for daily/hourly sync | 2 hours |
| 5.10 | Testing | 3 hours |

### Deliverable
Cursor and ChatGPT usage data visible in Odoo with cost tracking. Easy to add any new SaaS service in the future.

---

## Phase 6: AI Chat Interface (Week 11-12)

### Goal
Build a conversational AI chat inside Odoo where you can ask questions about your infrastructure in plain English.

### What You Build
- Chat interface (sidebar panel or full-page view)
- AI agent with access to all server data, metrics, and SaaS usage
- Function calling (AI can query database, check server status, generate reports)
- Conversation history
- Suggested questions

### Tasks

| # | Task | Effort |
|---|---|---|
| 6.1 | Design chat UI (OWL component for v19, Widget for v14) | 4 hours |
| 6.2 | Build chat backend controller (send message → get AI response) | 4 hours |
| 6.3 | Define `ai.chat.session` and `ai.chat.message` models | 2 hours |
| 6.4 | Build LangChain agent with Odoo tools (query servers, query metrics, etc.) | 8 hours |
| 6.5 | Implement function calling: AI can run Odoo ORM queries | 4 hours |
| 6.6 | Implement function calling: AI can check live server status | 3 hours |
| 6.7 | Implement function calling: AI can generate charts/reports | 4 hours |
| 6.8 | Add conversation memory (remember context within a session) | 2 hours |
| 6.9 | Add suggested questions ("Which servers are idle?", "Show monthly costs") | 1 hour |
| 6.10 | Streaming responses (typewriter effect) | 3 hours |
| 6.11 | Testing with various question types | 4 hours |

### Deliverable
An AI chat interface in Odoo where you can ask any question about your servers, metrics, costs, and the AI responds with accurate data from your system.

### Example Conversations

```
You:  "Which servers have been idle for more than 7 days?"
AI:   "I found 3 idle servers:
       1. SRV-DB-04 (idle for 14 days, last activity: Feb 6)
       2. SRV-WEB-07 (idle for 9 days, last activity: Feb 11)
       3. SRV-TEST-02 (idle for 22 days, last activity: Jan 29)
       Recommendation: Consider decommissioning SRV-TEST-02."

You:  "What's the total cost of our ChatGPT usage this month?"
AI:   "ChatGPT usage for February 2026:
       - Total API calls: 12,450
       - Total tokens: 8.2M
       - Total cost: $246.00
       - Top user: john.doe (3,200 calls, $78.40)"

You:  "Show me CPU trends for SRV-PROD-01 this week"
AI:   [Generates and displays a chart showing CPU usage over the past 7 days]
       "CPU averaged 67% this week with peak at 94% on Wednesday 2 PM.
       This correlates with your weekly batch processing job."
```

---

## Phase 7: Polish, Optimization & Production (Week 13-14)

### Goal
Harden the system for production use, optimize performance, and add finishing touches.

### Tasks

| # | Task | Effort |
|---|---|---|
| 7.1 | Performance optimization (database indexes, query optimization) | 4 hours |
| 7.2 | Data archival strategy (move old metrics to archive tables) | 3 hours |
| 7.3 | Error handling and recovery (what if agents go down?) | 4 hours |
| 7.4 | Security audit (API keys, SSH keys, access rights) | 3 hours |
| 7.5 | User documentation | 4 hours |
| 7.6 | Admin documentation (how to add new servers, configure alerts) | 3 hours |
| 7.7 | Backup and restore procedures | 2 hours |
| 7.8 | Load testing (simulate 100+ servers sending metrics) | 3 hours |
| 7.9 | CI/CD pipeline for the module | 3 hours |
| 7.10 | Module packaging for distribution | 2 hours |
| 7.11 | Final testing and bug fixes | 4 hours |

---

## Summary Table

| Phase | Duration | Key Output | Can Stop Here? |
|---|---|---|---|
| 1. Server Registry | 2 weeks | Server CRUD + workflow | Yes (basic server tracking) |
| 2. Monitoring Agents | 2 weeks | Live data flowing into Odoo | Yes (data collection working) |
| 3. Dashboard | 2 weeks | Visual monitoring in Odoo | Yes (Grafana-like dashboard) |
| 4. AI Classification | 2 weeks | Auto-classification + alerts | Yes (intelligent monitoring) |
| 5. SaaS Tracking | 2 weeks | Cursor/ChatGPT tracking | Yes (full monitoring + SaaS) |
| 6. AI Chat | 2 weeks | Conversational AI interface | Yes (complete AI system) |
| 7. Production Polish | 2 weeks | Production-ready system | Final |

**Total estimated time: 12-14 weeks** (working part-time, ~20 hours/week)

With full-time effort and Cursor AI assistance, this can be compressed to **6-8 weeks**.
