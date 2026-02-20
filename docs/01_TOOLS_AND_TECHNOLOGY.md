# 01 — Tools & Technology Stack

## Complete Reference of Every Tool, Library, and Service

This document lists **every component** you will need, what it does, why you need it, whether it costs money, and alternatives.

---

## 1. Core Platform

### Odoo Community Edition (v14 or v19)

- **What**: Open-source ERP/business application framework
- **Why**: Your main platform — all server records, dashboards, workflows, and AI chat live here
- **Cost**: Free (Community Edition)
- **Install**: `apt` / `pip` / Docker / source install
- **Website**: https://www.odoo.com/
- **Key Components Used**:
  - ORM (Object-Relational Mapping) for data models
  - QWeb templates for views
  - Scheduled Actions (ir.cron) for automated data collection
  - Web Controllers for REST APIs
  - JS framework (OWL in v19, legacy widgets in v14) for dashboards

### PostgreSQL

- **What**: Database engine used by Odoo
- **Why**: Stores all server records, metrics, AI analysis results
- **Cost**: Free
- **Version**: 12+ for Odoo 14, 15+ for Odoo 19
- **Note**: Odoo handles this automatically; you rarely interact with it directly

---

## 2. Server Monitoring — Data Collection Agents

These run on **each server you want to monitor**. You need at least ONE of these.

### Option A: Telegraf (Recommended)

- **What**: Lightweight agent that collects system metrics and sends them anywhere
- **Why**: Supports 300+ input plugins (CPU, RAM, Disk, Docker, processes, etc.) and can push data directly to your Odoo API via HTTP output
- **Cost**: Free (open-source, MIT license)
- **Install**: `apt-get install telegraf` or download from InfluxData
- **Website**: https://www.influxdata.com/time-series-platform/telegraf/
- **Key Plugins**:
  - `inputs.cpu` — CPU usage per core
  - `inputs.mem` — RAM usage
  - `inputs.disk` — Disk space and I/O
  - `inputs.net` — Network bandwidth
  - `inputs.processes` — Running process count
  - `inputs.system` — Uptime, load averages
  - `inputs.docker` — Container metrics (if using Docker)
  - `outputs.http` — Push JSON data to your Odoo REST endpoint

### Option B: Prometheus Node Exporter + Custom Scraper

- **What**: Exposes server metrics at an HTTP endpoint; you scrape it from Odoo
- **Why**: Industry standard, very reliable
- **Cost**: Free
- **Install**: Download binary from GitHub
- **Website**: https://github.com/prometheus/node_exporter
- **How it works with Odoo**: Your Odoo cron job calls `http://<server-ip>:9100/metrics`, parses the Prometheus text format, and stores values in Odoo

### Option C: Custom Python Agent (Simplest)

- **What**: A small Python script using `psutil` that collects metrics and POSTs them to Odoo
- **Why**: Easiest to understand, no external dependencies, fully customizable
- **Cost**: Free
- **Libraries**: `psutil`, `requests`
- **Trade-off**: Less mature than Telegraf, but gives you full control

### Recommendation

| Scenario | Use |
|---|---|
| Many servers, need reliability | Telegraf |
| Already using Prometheus | Node Exporter |
| Small setup, want simplicity | Custom Python agent |
| Want maximum flexibility | Telegraf + Custom Python for edge cases |

---

## 3. AI & Machine Learning

### OpenAI API (GPT-4 / GPT-4o)

- **What**: Cloud AI service for natural language understanding and analysis
- **Why**: Powers the AI Chat ("Which servers are idle?"), generates summaries, classifies server status
- **Cost**: Pay-per-use (~$0.01-0.03 per 1K tokens for GPT-4o)
- **API Key**: Required (get from https://platform.openai.com/)
- **Python Library**: `openai`
- **Used For**:
  - AI Chat interface in Odoo
  - Automatic server classification (active/inactive/underutilized)
  - Natural language report generation
  - Anomaly explanation ("Server X CPU spiked because...")

### LangChain (Recommended Framework)

- **What**: Python framework for building AI applications with LLMs
- **Why**: Provides structured tools, chains, and agents that can query your Odoo database and monitoring data
- **Cost**: Free (open-source)
- **Install**: `pip install langchain langchain-openai`
- **Website**: https://www.langchain.com/
- **Used For**:
  - Building the AI agent that automatically analyzes metrics
  - Function calling (AI can query Odoo models, run SQL, check APIs)
  - Chat memory (conversation history in AI Chat)
  - RAG (Retrieval-Augmented Generation) for searching server documentation

### Ollama (Optional — Local AI, No API Costs)

- **What**: Run open-source LLMs locally (Llama 3, Mistral, etc.)
- **Why**: No API costs, data stays on-premise, works offline
- **Cost**: Free (but needs a machine with 8GB+ RAM, GPU preferred)
- **Install**: `curl -fsSL https://ollama.com/install.sh | sh`
- **Website**: https://ollama.com/
- **Models**: `llama3.1:8b`, `mistral:7b`, `codellama:13b`
- **Trade-off**: Less capable than GPT-4 but free and private

### Scikit-learn (Optional — Classical ML)

- **What**: Python machine learning library
- **Why**: For anomaly detection, clustering, and time-series forecasting without needing an LLM
- **Cost**: Free
- **Install**: `pip install scikit-learn`
- **Used For**:
  - Anomaly detection (Isolation Forest algorithm for detecting unusual server behavior)
  - Clustering servers by usage patterns
  - Predicting future resource needs

---

## 4. Dashboard & Visualization (Inside Odoo)

### Chart.js

- **What**: JavaScript charting library
- **Why**: Renders beautiful, interactive charts (line, bar, pie, gauge) directly in Odoo views
- **Cost**: Free
- **CDN**: `https://cdn.jsdelivr.net/npm/chart.js`
- **Used For**: CPU/RAM/Disk graphs, network bandwidth charts, utilization gauges
- **Odoo Integration**: Loaded as a JS asset in your module, rendered in OWL components (v19) or widgets (v14)

### Apache ECharts (Alternative)

- **What**: More powerful charting library with more chart types
- **Why**: Supports heatmaps, tree maps, and complex dashboards
- **Cost**: Free
- **Website**: https://echarts.apache.org/
- **When to use**: If you need Grafana-level visualization complexity

### Odoo Built-in Graph/Pivot Views

- **What**: Odoo's native graph and pivot table views
- **Why**: Zero additional setup, works out of the box
- **Limitation**: Less customizable than Chart.js/ECharts, but good for quick data views

### Recommendation

Use **Chart.js** for the main dashboard (it covers 90% of needs) and fall back to **ECharts** only for specialized visualizations like heatmaps.

---

## 5. Data Pipeline & Storage

### InfluxDB (Optional — Time-Series Database)

- **What**: Purpose-built database for time-series metrics
- **Why**: If you have 50+ servers generating metrics every 10 seconds, PostgreSQL may struggle; InfluxDB handles this efficiently
- **Cost**: Free (open-source edition)
- **Install**: `apt-get install influxdb2`
- **When to use**: Only if you have a large number of servers (50+) or need sub-minute metric resolution
- **How it works with Odoo**: Telegraf → InfluxDB → Odoo cron reads from InfluxDB API → stores summaries in Odoo PostgreSQL

### Redis (Optional — Caching & Real-time)

- **What**: In-memory data store
- **Why**: Cache latest metrics for instant dashboard loading; pub/sub for real-time updates
- **Cost**: Free
- **Install**: `apt-get install redis`
- **When to use**: If you want the dashboard to update without page refresh (WebSocket + Redis pub/sub)

### For Most Setups (Under 50 Servers)

Just use **PostgreSQL** (Odoo's default database). Store metrics directly in Odoo models. Keep 30-90 days of detailed data and aggregate older data into daily summaries.

---

## 6. SaaS API Integrations

### Cursor IDE

- **What**: AI-powered code editor (fork of VS Code)
- **Tracking**: Usage statistics, API call counts, team member activity
- **API**: Cursor provides usage data through their dashboard/API
- **How**: Periodic API calls from Odoo cron to fetch usage data
- **Data Captured**: Requests made, tokens used, active users, billing info

### ChatGPT / OpenAI Platform

- **What**: AI chat and API service
- **Tracking**: API usage, costs, token consumption
- **API**: `https://api.openai.com/v1/organization/usage` (Organization Usage API)
- **How**: Odoo cron calls OpenAI usage API daily
- **Data Captured**: Tokens used per model, costs, request counts

### Extensible for Any Future Service

The system is designed so you can add any API-based service by:
1. Creating a new Odoo model for the service
2. Writing an API connector class
3. Adding a cron job to poll the API
4. Adding a dashboard widget

---

## 7. Communication & Alerting

### Odoo Built-in

- **Mail**: Odoo's mail system for email alerts
- **Discuss**: Internal chat/messaging for team notifications
- **Activities**: Task assignments when server issues are detected

### External (Optional)

| Service | Use Case | Cost |
|---|---|---|
| Slack Webhooks | Alert channels | Free |
| Telegram Bot API | Mobile alerts | Free |
| PagerDuty | Critical incident management | Paid |
| Twilio (SMS) | SMS alerts for critical issues | Pay-per-use |

---

## 8. Development Tools

### Required

| Tool | Purpose |
|---|---|
| Python 3.8+ (v14) / 3.10+ (v19) | Odoo server-side development |
| Node.js 16+ | Building Odoo frontend assets |
| Git | Version control |
| Cursor IDE | Your development environment (with AI assistance) |

### Recommended Python Libraries

```
# Core (installed with Odoo)
lxml
psycopg2
werkzeug

# Monitoring
psutil          # System metrics collection (for custom agents)
paramiko        # SSH connections to remote servers
requests        # HTTP API calls

# AI
openai          # OpenAI API client
langchain       # AI agent framework
langchain-openai # LangChain + OpenAI integration

# Data Processing
pandas          # Data analysis and manipulation
numpy           # Numerical computing

# Optional
scikit-learn    # Machine learning (anomaly detection)
celery          # Background task queue (for heavy AI processing)
redis           # Caching and real-time updates
influxdb-client # InfluxDB connection (if using time-series DB)
```

---

## 9. Infrastructure Requirements

### Minimum Setup (Small — Under 10 Servers)

| Component | Specification |
|---|---|
| Odoo Server | 2 CPU, 4GB RAM, 50GB Disk |
| Database | Same machine (PostgreSQL) |
| AI | OpenAI API (cloud, no local hardware needed) |
| Monitoring Agent | Telegraf or Python script on each server |

### Recommended Setup (Medium — 10-50 Servers)

| Component | Specification |
|---|---|
| Odoo Server | 4 CPU, 8GB RAM, 100GB SSD |
| Database | Separate PostgreSQL server (4 CPU, 8GB RAM) |
| AI | OpenAI API + optional Ollama on a GPU machine |
| Redis | Same machine as Odoo or separate (2GB RAM) |
| Monitoring Agent | Telegraf on each server |

### Large Setup (50+ Servers)

| Component | Specification |
|---|---|
| Odoo Server | 8 CPU, 16GB RAM, 200GB SSD |
| Database | Dedicated PostgreSQL cluster |
| Time-Series DB | InfluxDB on separate server |
| AI Server | Dedicated GPU server for Ollama (RTX 3090 or better) |
| Redis | Dedicated instance |
| Monitoring | Telegraf + Prometheus for redundancy |

---

## 10. Summary: What to Install Where

### On Your Odoo Server
```
Odoo 14 or 19 CE
PostgreSQL
Python libraries (openai, langchain, psutil, paramiko, requests, pandas)
Redis (optional)
Node.js (for building assets)
```

### On Each Monitored Server
```
Telegraf (recommended)
  OR
Node Exporter (Prometheus)
  OR
Custom Python monitoring script
```

### Cloud Services (API Keys Needed)
```
OpenAI API key (for AI features)
Cursor account (for usage tracking)
ChatGPT/OpenAI Organization (for usage tracking)
```

### Optional Separate Services
```
InfluxDB (if 50+ servers)
Ollama (if you want free local AI)
```
