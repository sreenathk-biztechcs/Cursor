# 04 — AI Integration Guide

## How AI Agents, Chat, and Automation Work

This document explains the complete AI architecture — what runs, when, how, and why. The goal is a system where AI does everything automatically; you only manage server records.

---

## AI Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AI LAYER                                    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 1. SCHEDULED AI AGENT (Runs Automatically)                   │   │
│  │                                                               │   │
│  │ Cron: Every 60 minutes                                        │   │
│  │ • Reads all server metrics from last hour                     │   │
│  │ • Classifies each server (active/idle/overloaded/down)        │   │
│  │ • Detects anomalies                                           │   │
│  │ • Generates insights                                          │   │
│  │ • Fires alerts if needed                                      │   │
│  │ • Updates ai_classification on server.server                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 2. INTERACTIVE AI CHAT (User-Triggered)                      │   │
│  │                                                               │   │
│  │ User asks a question in natural language                      │   │
│  │ • AI has access to all Odoo data via function calling         │   │
│  │ • Can query servers, metrics, alerts, SaaS usage              │   │
│  │ • Can generate charts and reports on demand                   │   │
│  │ • Maintains conversation context                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 3. REAL-TIME AI CLASSIFIER (Event-Driven)                    │   │
│  │                                                               │   │
│  │ Triggered when new metrics arrive                             │   │
│  │ • Quick rule-based checks (fast, no LLM needed)              │   │
│  │ • If anomaly detected → triggers deeper AI analysis           │   │
│  │ • Updates server status immediately                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 4. REPORT GENERATOR (Scheduled)                              │   │
│  │                                                               │   │
│  │ Cron: Daily / Weekly / Monthly                                │   │
│  │ • Generates natural language infrastructure reports           │   │
│  │ • Summarizes server health, costs, trends                     │   │
│  │ • Sends via email or posts to Odoo Discuss                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Scheduled AI Agent — Automatic Server Analysis

### How It Works

```
Every 60 minutes:
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  1. COLLECT: Fetch last 60 min of metrics per server    │
│     └─> Odoo ORM: server.metric.search_read()           │
│                                                         │
│  2. SUMMARIZE: Calculate averages, peaks, trends        │
│     └─> Python: pandas for stats, or raw SQL            │
│                                                         │
│  3. CLASSIFY (Rule-Based — fast, no API cost):          │
│     ├─> No metrics received → DOWN                      │
│     ├─> CPU avg < 5%, RAM < 20% for 7 days → IDLE      │
│     ├─> CPU avg > 80% for 2+ hours → OVERLOADED        │
│     ├─> CPU 20-80%, regular activity → ACTIVE           │
│     └─> CPU 5-20%, sporadic activity → UNDERUTILIZED    │
│                                                         │
│  4. DEEP ANALYSIS (LLM — rich insights):                │
│     └─> Send metric summary to GPT-4o/Llama:            │
│         "Analyze this server's metrics and provide:      │
│          - Health assessment                             │
│          - Anomalies detected                            │
│          - Trend prediction                              │
│          - Recommendations"                              │
│                                                         │
│  5. STORE: Write results to server.ai.analysis          │
│     └─> Update server.server ai_classification          │
│                                                         │
│  6. ALERT: If critical issues found                     │
│     └─> Create server.alert records                     │
│     └─> Send notifications                              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### AI Prompt Design for Server Analysis

The key to good AI analysis is a well-structured prompt. Here is the approach:

```
System Prompt:
"You are a server infrastructure analyst. You receive server metrics 
and must classify server health, detect anomalies, and provide 
actionable recommendations.

Respond in JSON format with these fields:
- classification: active | idle | underutilized | overloaded | down
- health_score: 0-100
- summary: One-sentence health summary
- anomalies: List of detected anomalies
- trends: List of observed trends
- recommendations: List of actionable recommendations
- confidence: 0.0-1.0"

User Message (constructed from data):
"Server: PROD-WEB-01 (Ubuntu 22.04, 8 CPU cores, 16GB RAM)
Last 24 hours metrics:
- CPU: avg=67%, min=12%, max=94%, p95=89%
- RAM: avg=72%, min=65%, max=81%
- Disk: avg=45%, trend=+0.2%/day
- Network In: avg=120 MB/s, peak=450 MB/s
- Network Out: avg=85 MB/s, peak=320 MB/s
- Load Average: avg=5.2, max=7.8
- Process Count: avg=312, max=398
- Uptime: 45 days

Historical context:
- Last week avg CPU: 58% (current is higher)
- Disk was 40% last month (growing)
- 2 CPU spike alerts in past 7 days"
```

### Cost Optimization

| Strategy | How |
|---|---|
| Rule-based first | Only call LLM when rules are insufficient or for rich insights |
| Batch analysis | Analyze all servers in one LLM call instead of one-per-server |
| Cache results | Don't re-analyze if metrics haven't changed significantly |
| Use GPT-4o-mini | For simple classification, cheaper model is sufficient |
| Local LLM | Use Ollama for routine analysis, GPT-4 only for complex cases |

**Estimated cost**: ~$0.50-2.00/day for 20 servers analyzed hourly with GPT-4o-mini.

---

## 2. Interactive AI Chat

### Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│  Odoo Chat   │────>│  Chat Controller │────>│  LangChain Agent     │
│  UI (JS)     │     │  (Python)        │     │                      │
│              │<────│                  │<────│  Tools:              │
│  - Input box │     │  /api/v1/chat    │     │  - query_servers()   │
│  - Messages  │     │                  │     │  - query_metrics()   │
│  - History   │     │                  │     │  - query_alerts()    │
└──────────────┘     └──────────────────┘     │  - query_saas()     │
                                               │  - run_analysis()   │
                                               │  - generate_chart() │
                                               │  - search_logs()    │
                                               └──────────────────────┘
```

### LangChain Agent Setup

The AI Chat uses a **LangChain Agent** with custom **Tools**. Each tool is a Python function that the AI can call to fetch data from Odoo.

**Tools the AI Agent Has Access To:**

| Tool Name | What It Does | Example Use |
|---|---|---|
| `query_servers` | Search/filter servers in Odoo | "Find all idle production servers" |
| `query_metrics` | Get metric data for a server + time range | "Get CPU data for SRV-01 last 24h" |
| `query_alerts` | Get active alerts | "Show all critical alerts" |
| `query_saas_usage` | Get SaaS usage data | "ChatGPT costs this month" |
| `run_sql` | Execute read-only SQL | Complex aggregations |
| `server_status` | Get current status of a server | "Is PROD-DB-01 up?" |
| `generate_report` | Create a summary report | "Weekly server health report" |
| `count_servers` | Count servers by various criteria | "How many servers do we have?" |
| `compare_servers` | Compare metrics between servers | "Compare SRV-01 and SRV-02 CPU" |

### How a Chat Query Works (Step by Step)

```
User types: "Which servers have been idle for more than 7 days?"

1. Odoo JS sends POST to /api/v1/chat
   Body: { session_id: 123, message: "Which servers have been idle..." }

2. Chat Controller receives the message
   - Saves user message to ai.chat.message
   - Passes to LangChain Agent

3. LangChain Agent thinks:
   "I need to find idle servers. Let me use the query_servers tool."
   
4. Agent calls tool: query_servers(filters={"ai_classification": "idle"})
   
5. Tool executes:
   self.env['server.server'].search_read(
       [('ai_classification', '=', 'idle')],
       ['name', 'ip_address', 'ai_last_analysis', 'cpu_usage_current']
   )
   Returns: [
       {"name": "SRV-DB-04", "cpu_usage_current": 2.1, ...},
       {"name": "SRV-WEB-07", "cpu_usage_current": 0.8, ...},
   ]

6. Agent processes results and generates natural language response

7. Response saved to ai.chat.message and returned to frontend

8. Frontend displays the response with any charts/data
```

### Conversation Memory

The AI maintains context within a session:
- Previous messages are included in the LLM context
- Server context: if you asked about SRV-01, follow-up questions assume SRV-01
- LangChain's `ConversationBufferWindowMemory` keeps last N messages

---

## 3. Real-Time Classifier (Event-Driven)

This is a lightweight, fast classifier that runs whenever new metrics arrive.

```
Metric arrives via API
        │
        v
┌─────────────────────────────┐
│  Quick Rule Checks (No LLM) │
│                              │
│  if no_metrics_5min:         │
│     server.monitoring_state  │
│     = 'down'                 │
│     create_alert('down')     │
│                              │
│  if cpu > alert_threshold:   │
│     create_alert('cpu_high') │
│                              │
│  if disk > 90%:              │
│     create_alert('disk_full')│
│                              │
│  Update server computed      │
│  fields (cpu_current, etc.)  │
└─────────────────────────────┘
```

This is pure Python with no AI API calls — it runs in milliseconds. The deeper LLM analysis is reserved for the scheduled hourly job.

---

## 4. AI Report Generator

### Daily Report (Example Output)

```
═══════════════════════════════════════════════════════
 DAILY SERVER INFRASTRUCTURE REPORT — February 20, 2026
═══════════════════════════════════════════════════════

FLEET OVERVIEW
─────────────────────────────────────────────────────
 Total Servers:    48
 Active:           39 (81%)
 Idle:             5  (10%)
 Under-utilized:   3  (6%)
 Down:             1  (2%)

CRITICAL ISSUES
─────────────────────────────────────────────────────
 ⚠ PROD-DB-03: Disk usage at 94% — will be full in ~3 days
 ⚠ PROD-WEB-05: CPU averaged 91% — consider scaling up

COST SUMMARY
─────────────────────────────────────────────────────
 ChatGPT API:     $12.40 today ($186 this month)
 Cursor:          5 active users, 342 completions
 
RECOMMENDATIONS
─────────────────────────────────────────────────────
 1. Reclaim SRV-TEST-02 — idle for 22 days
 2. Add disk space to PROD-DB-03 urgently
 3. Consider load balancing for PROD-WEB-05
═══════════════════════════════════════════════════════
```

---

## 5. Choosing the Right AI Backend

### Decision Matrix

| Factor | OpenAI (GPT-4o) | OpenAI (GPT-4o-mini) | Ollama (Llama 3.1 8B) | Ollama (Mistral 7B) |
|---|---|---|---|---|
| **Quality** | Excellent | Good | Good | Good |
| **Speed** | Fast (cloud) | Very Fast (cloud) | Depends on hardware | Depends on hardware |
| **Cost** | ~$0.01/1K tokens | ~$0.0003/1K tokens | Free | Free |
| **Privacy** | Data sent to OpenAI | Data sent to OpenAI | Fully local | Fully local |
| **Setup** | API key only | API key only | Need server with 8GB+ RAM | Need server with 8GB+ RAM |
| **Best For** | Complex analysis, chat | Routine classification | Privacy-sensitive, budget | Privacy-sensitive, budget |

### Recommended Hybrid Approach

```
Routine classification (every hour):
  → Ollama (Llama 3.1 8B) — Free, local, private

AI Chat (user questions):
  → OpenAI GPT-4o — Best quality for interactive use

Daily reports:
  → OpenAI GPT-4o-mini — Good quality, very cheap

Anomaly explanation:
  → OpenAI GPT-4o — Needs deep reasoning
```

---

## 6. Setting Up LangChain for Odoo

### Conceptual Flow

```python
# This is a conceptual representation, not production code

# 1. Define tools that can access Odoo data
class OdooTools:
    """Each method becomes a tool the AI can call"""
    
    def query_servers(self, filters: dict) -> list:
        """Search servers with given filters"""
        # Uses Odoo ORM: self.env['server.server'].search_read(...)
        
    def get_server_metrics(self, server_name: str, metric_type: str, hours: int) -> dict:
        """Get metrics for a server over a time period"""
        # Uses Odoo ORM: self.env['server.metric'].search_read(...)
        
    def get_active_alerts(self, severity: str = None) -> list:
        """Get all active alerts, optionally filtered by severity"""
        # Uses Odoo ORM: self.env['server.alert'].search_read(...)
    
    def get_saas_usage(self, service: str, period: str) -> dict:
        """Get SaaS usage stats for a service"""
        # Uses Odoo ORM: self.env['saas.usage'].search_read(...)

# 2. Create the LangChain agent
# The agent combines:
#   - An LLM (GPT-4o or Ollama)
#   - The tools above
#   - A system prompt explaining the agent's role
#   - Conversation memory

# 3. Process user messages
# User message → Agent → Agent decides which tools to call → 
# Tools fetch Odoo data → Agent generates response
```

### System Prompt for the Chat Agent

```
You are an AI infrastructure assistant integrated into Odoo. You help 
manage and monitor servers. You have access to real-time server metrics, 
alerts, and SaaS usage data.

When answering questions:
1. Always use your tools to fetch real data — never make up numbers
2. Be specific: include server names, exact values, and timestamps
3. Provide actionable recommendations when relevant
4. If asked to compare, show data side by side
5. If you detect critical issues in the data, proactively mention them

You have access to these tools:
- query_servers: Search and filter servers
- get_server_metrics: Get time-series metrics for a server
- get_active_alerts: Get current alerts
- get_saas_usage: Get SaaS tool usage data
- server_status: Quick status check for a server
```

---

## 7. Anomaly Detection Without LLM

For cost-effective anomaly detection, you can use statistical methods that run locally:

### Z-Score Method
```
For each metric value:
  z_score = (value - mean) / std_deviation
  if abs(z_score) > 3:
      → ANOMALY DETECTED
```

### Isolation Forest (scikit-learn)
- Unsupervised ML algorithm specifically designed for anomaly detection
- Train on historical metrics, flag outliers
- No labels needed, works automatically

### Moving Average Deviation
```
For each new metric:
  moving_avg = average of last 60 data points
  deviation = abs(value - moving_avg) / moving_avg
  if deviation > 0.5:  # 50% deviation from normal
      → ANOMALY DETECTED
```

These run locally in Python with zero API costs and can trigger the LLM only when an anomaly is found (for explanation and recommendations).

---

## 8. Making It "Fully Automatic"

Here is exactly how the system runs with zero manual effort after initial setup:

| What Happens | How | Frequency |
|---|---|---|
| Metrics collected | Telegraf agents push to Odoo API | Every 30-60 seconds |
| Quick health check | Rule-based classifier on metric arrival | Real-time |
| Deep AI analysis | Cron job runs LLM analysis | Every 60 minutes |
| Alerts generated | Rule engine + AI anomaly detection | Real-time + hourly |
| Notifications sent | Odoo mail/discuss on alert creation | On alert |
| Dashboard updated | Frontend polls API | Every 30 seconds |
| SaaS data synced | Cron job calls external APIs | Hourly or daily |
| Daily report | Cron job at 8 AM | Daily |
| Weekly report | Cron job on Monday 9 AM | Weekly |
| Data cleanup | Cron job deletes old metrics | Daily at 2 AM |
| Server status | Auto-set based on metric flow | Continuous |

**Your only tasks**: Add/edit server records. Everything else runs itself.
