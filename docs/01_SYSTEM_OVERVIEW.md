# Odoo AI-Powered Server Monitoring System — Complete Guide

## Table of Contents

1. [What This System Does](#what-this-system-does)
2. [Big Picture Architecture](#big-picture-architecture)
3. [Core Concepts Explained (For Beginners)](#core-concepts-explained)
4. [Tools & Technologies Stack](#tools--technologies-stack)
5. [How Everything Connects](#how-everything-connects)

---

## What This System Does

You have **many servers** across your company. Today, you manually track which ones are active, which are idle, and which are wasting resources. This system will:

| Problem Today | What This System Solves |
|---|---|
| You don't know which servers are active or idle | **Automatic real-time monitoring** — every server reports its CPU, RAM, disk, network usage automatically |
| You manually request and track server allocations | **Odoo custom module** — request, approve, allocate, and track servers inside Odoo |
| No centralized dashboard | **Grafana-style dashboard inside Odoo** — live charts, gauges, and tables showing all server health |
| No AI assistance | **AI auto-analysis** — AI reads the metrics, detects anomalies, suggests actions, and answers your questions via chat |
| Works across Odoo versions | **Compatible with Odoo 14 CE and Odoo 19 CE** |

---

## Big Picture Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        YOUR SERVERS (10, 50, 200+)                      │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │ Server 1 │  │ Server 2 │  │ Server 3 │  │ Server N │               │
│  │          │  │          │  │          │  │          │               │
│  │ [Node    │  │ [Node    │  │ [Node    │  │ [Node    │               │
│  │ Exporter]│  │ Exporter]│  │ Exporter]│  │ Exporter]│               │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘               │
│       │              │              │              │                     │
│       └──────────────┴──────┬───────┴──────────────┘                    │
│                             │ metrics (pull every 15s)                   │
│                             ▼                                           │
│                    ┌─────────────────┐                                   │
│                    │   PROMETHEUS     │  ◄── Time-series database        │
│                    │  (Metrics Store) │      Collects & stores all       │
│                    └────────┬────────┘      server metrics               │
│                             │                                           │
│              ┌──────────────┼──────────────┐                            │
│              │              │              │                             │
│              ▼              ▼              ▼                             │
│   ┌──────────────┐  ┌─────────────┐  ┌──────────────┐                  │
│   │   GRAFANA     │  │ ODOO MODULE │  │  AI ENGINE   │                  │
│   │  (Optional    │  │ (Custom     │  │ (OpenAI /    │                  │
│   │   Reference)  │  │  Dashboard) │  │  Local LLM)  │                  │
│   └──────────────┘  └──────┬──────┘  └──────┬───────┘                  │
│                            │                │                           │
│                            └────────┬───────┘                           │
│                                     ▼                                   │
│                          ┌──────────────────┐                           │
│                          │  ODOO 14 / 19    │                           │
│                          │  ┌─────────────┐ │                           │
│                          │  │ Server Mgmt │ │                           │
│                          │  │ Dashboard   │ │                           │
│                          │  │ AI Chat     │ │                           │
│                          │  │ Alerts      │ │                           │
│                          │  │ Reports     │ │                           │
│                          │  └─────────────┘ │                           │
│                          └──────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Concepts Explained

### What is Grafana?

Grafana is an **open-source visualization tool**. It connects to data sources (like Prometheus) and displays beautiful dashboards with charts, graphs, and alerts. Think of it as a "TV screen" that shows your server health in real-time.

**Why we are NOT just using Grafana directly:**
- Grafana is great for visualization, but it **cannot manage server records** (allocations, approvals, ownership).
- You want everything **inside Odoo** — one system, one login, one place.
- We will **replicate Grafana's dashboard capabilities inside Odoo** using JavaScript chart libraries (Chart.js / ECharts / Plotly).
- You can optionally keep Grafana running as a reference or embed its panels via iframe.

### What is Prometheus?

Prometheus is a **metrics collection and storage engine**. It:
- **Pulls** (scrapes) metrics from your servers every 15 seconds
- **Stores** them in a time-series database (efficient for "what was the CPU at 3 PM yesterday?")
- **Provides a query language** called PromQL to ask questions about your data
- Is the **industry standard** — used by Google, Amazon, every major tech company

### What is Node Exporter?

Node Exporter is a **small program you install on each server**. It exposes server metrics (CPU, RAM, disk, network, processes) as an HTTP endpoint that Prometheus can scrape.

- Runs on port `9100` by default
- Extremely lightweight (~10 MB RAM)
- Works on any Linux server

### What is an API?

An API (Application Programming Interface) is how two systems talk to each other. In our case:
- **Prometheus API** → Odoo asks Prometheus "give me CPU usage of Server 3" → Prometheus responds with data
- **OpenAI API** → Odoo sends metrics to ChatGPT → ChatGPT responds with analysis
- **Odoo API** → External tools can push data into Odoo

### What is a Time-Series Database?

A database optimized for data that changes over time. Instead of storing "Server A has 50% CPU", it stores:
```
Server A CPU: 50% at 10:00:00, 55% at 10:00:15, 48% at 10:00:30, ...
```
This lets you see trends, patterns, and history.

---

## Tools & Technologies Stack

### Required Tools

| Tool | Purpose | Where It Runs | Cost |
|------|---------|---------------|------|
| **Prometheus** | Collects and stores metrics from all servers | Central monitoring server | Free (open source) |
| **Node Exporter** | Exposes server metrics (CPU, RAM, disk, etc.) | On EACH monitored server | Free (open source) |
| **Alertmanager** | Sends alerts when thresholds are breached | With Prometheus | Free (open source) |
| **Odoo 14/19 CE** | Server management, dashboard, AI chat | Your Odoo server | Free (Community Edition) |

### Optional but Recommended Tools

| Tool | Purpose | Where It Runs | Cost |
|------|---------|---------------|------|
| **Grafana** | Reference dashboard (can embed in Odoo) | Central monitoring server | Free (open source) |
| **cAdvisor** | Monitor Docker containers if you use Docker | On Docker hosts | Free |
| **Blackbox Exporter** | Monitor HTTP endpoints, ping, SSL certs | Central server | Free |
| **Process Exporter** | Monitor specific processes on servers | On each server | Free |

### AI Tools

| Tool | Purpose | Cost |
|------|---------|------|
| **OpenAI API (GPT-4)** | AI analysis of metrics, anomaly detection, chat | Pay-per-use (~$0.01-0.03 per query) |
| **ChatGPT Premium** | You already have this — use for development help | Your existing subscription |
| **Cursor AI** | You already have this — use for coding the module | Your existing subscription |
| **Ollama (optional)** | Run AI locally for free (Llama 3, Mistral) | Free (needs GPU server) |

### JavaScript Libraries for Odoo Dashboard

| Library | Purpose |
|---------|---------|
| **ECharts** (recommended) | Rich interactive charts — gauges, heatmaps, line charts |
| **Chart.js** | Lightweight charts — simpler but fast |
| **Plotly.js** | Scientific/complex charts |
| **D3.js** | Maximum customization (steep learning curve) |

---

## How Everything Connects — Data Flow

### Step-by-Step Data Flow

```
1. Node Exporter (on each server)
   │
   │  Exposes metrics at http://server-ip:9100/metrics
   │  Example data: cpu_usage=45%, ram_used=8GB, disk_free=120GB
   │
   ▼
2. Prometheus (central server)
   │
   │  Scrapes all Node Exporters every 15 seconds
   │  Stores data in time-series database
   │  Retains data for 15-90 days (configurable)
   │
   ▼
3. Odoo Cron Job (runs every 1-5 minutes)
   │
   │  Calls Prometheus HTTP API:
   │  GET http://prometheus:9090/api/v1/query?query=node_cpu_seconds_total
   │
   │  Receives JSON response with metrics
   │
   ▼
4. Odoo Custom Module
   │
   │  Stores latest snapshot in Odoo database
   │  Updates server records (active/inactive/warning/critical)
   │  Triggers AI analysis if anomaly detected
   │
   ▼
5. AI Engine (OpenAI API or Local LLM)
   │
   │  Receives: "Server X has 95% CPU for last 2 hours, 
   │            disk at 92%, 3 zombie processes"
   │  Returns: "CRITICAL: Server X is overloaded. 
   │           Recommend: Kill zombie PIDs, move DB to Server Y,
   │           add 16GB RAM or migrate workload"
   │
   ▼
6. Odoo Dashboard
   │
   │  Displays: Live charts, server cards, AI recommendations
   │  User sees: Everything in one place inside Odoo
   │
   ▼
7. AI Chat (inside Odoo)

   User asks: "Which servers have been idle for more than 7 days?"
   AI responds: "Servers 12, 15, 22 have had <5% CPU usage for 
                 the past 10 days. Recommend decommissioning."
```

### API Endpoints Used

| Source | API Endpoint | What It Returns |
|--------|-------------|-----------------|
| Prometheus | `GET /api/v1/query` | Instant metric value |
| Prometheus | `GET /api/v1/query_range` | Metric values over time range |
| Prometheus | `GET /api/v1/targets` | List of all monitored servers and their status |
| OpenAI | `POST /v1/chat/completions` | AI analysis text |
| Odoo | `POST /jsonrpc` | Odoo's own RPC for external integrations |

---

## Odoo Version Differences

### Odoo 14 CE vs Odoo 19 CE

| Feature | Odoo 14 CE | Odoo 19 CE |
|---------|-----------|-----------|
| **Frontend Framework** | Legacy web client (jQuery-based) | OWL 2 framework (modern, component-based) |
| **Dashboard** | Use `ir.actions.client` + Chart.js/ECharts | Use OWL components + Chart.js/ECharts |
| **Cron Jobs** | `ir.cron` — same in both | `ir.cron` — same in both |
| **API Calls** | `requests` library in Python | `requests` library in Python |
| **AI Chat Widget** | Custom widget using `Widget.extend()` | Custom OWL component |
| **Module Structure** | Same `__manifest__.py` structure | Same `__manifest__.py` structure |
| **Python Version** | Python 3.8+ | Python 3.10+ |

**Key Takeaway:** The backend logic (models, cron jobs, API calls, AI integration) is **95% identical** between Odoo 14 and 19. The main difference is the **frontend/dashboard code** — Odoo 14 uses the legacy widget system while Odoo 19 uses OWL components.

**Strategy:** Build the module with a shared backend and two separate frontend implementations.
