# AI Integration — Complete Guide

## Overview

This document explains how AI is integrated into the system to make everything **automatic**. The goal: you only create/manage server records — AI does all the analysis, monitoring, anomaly detection, and reporting.

---

## Part 1: AI Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI INTEGRATION LAYERS                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 1: DATA COLLECTION (Automatic)                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │Prometheus │  │Odoo Data │  │External  │                      │
│  │ Metrics   │  │(records) │  │ APIs     │                      │
│  └─────┬─────┘  └─────┬────┘  └─────┬────┘                     │
│        └───────────────┼─────────────┘                           │
│                        ▼                                         │
│  Layer 2: DATA PROCESSING (Automatic)                           │
│  ┌──────────────────────────────────┐                           │
│  │ Python Services in Odoo          │                           │
│  │ - Aggregate metrics              │                           │
│  │ - Detect threshold breaches      │                           │
│  │ - Calculate trends               │                           │
│  │ - Prepare structured context     │                           │
│  └──────────────┬───────────────────┘                           │
│                 ▼                                                │
│  Layer 3: AI ANALYSIS (Automatic + On-Demand)                   │
│  ┌──────────────────────────────────┐                           │
│  │ OpenAI API / Local LLM           │                           │
│  │ - Health assessment              │                           │
│  │ - Anomaly detection              │                           │
│  │ - Capacity prediction            │                           │
│  │ - Cost optimization              │                           │
│  │ - Natural language Q&A           │                           │
│  └──────────────┬───────────────────┘                           │
│                 ▼                                                │
│  Layer 4: ACTION & PRESENTATION (Automatic)                     │
│  ┌──────────────────────────────────┐                           │
│  │ - Update Odoo records            │                           │
│  │ - Send alerts/notifications      │                           │
│  │ - Update dashboard               │                           │
│  │ - Generate reports               │                           │
│  │ - Respond to chat queries        │                           │
│  └──────────────────────────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 2: OpenAI API Integration

### Setup

1. Get an API key from https://platform.openai.com/api-keys
2. Store it in Odoo's monitoring configuration (encrypted)
3. The Odoo module calls OpenAI's API from the backend (Python)

### Recommended Models

| Model | Use Case | Cost (per 1M tokens) | Speed |
|---|---|---|---|
| **gpt-4o** | Complex analysis, fleet summary | ~$5 input / $15 output | Medium |
| **gpt-4o-mini** | Routine checks, chat responses | ~$0.15 input / $0.60 output | Fast |
| **gpt-4.1** | Best quality analysis | ~$2 input / $8 output | Medium |
| **gpt-4.1-mini** | Good balance of quality and cost | ~$0.40 input / $1.60 output | Fast |

**Recommendation:** Use `gpt-4o-mini` or `gpt-4.1-mini` for routine scheduled analysis (cheap and fast), and `gpt-4o` or `gpt-4.1` for detailed on-demand analysis and chat.

### Python Code Pattern for API Calls

```python
import openai
import json

class AIService:
    """Service class for AI operations - used by Odoo models."""

    def __init__(self, api_key, model='gpt-4o-mini', base_url=None):
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url  # For Ollama: http://localhost:11434/v1
        )
        self.model = model

    def analyze_server_health(self, server_data):
        """
        Analyze server metrics and return structured health assessment.
        
        server_data: dict with server info and recent metrics
        Returns: dict with analysis results
        """
        system_prompt = """You are an expert server infrastructure analyst.
Analyze the provided server metrics and return a JSON response with:
{
    "health_status": "healthy|warning|critical",
    "risk_score": 0-100,
    "summary": "one-line summary",
    "issues": ["list of detected issues"],
    "recommendations": ["list of actionable recommendations"],
    "prediction": "what will happen if no action is taken",
    "idle_assessment": {
        "is_idle": true/false,
        "idle_since": "date or null",
        "confidence": 0-100
    }
}
Be precise, data-driven, and actionable."""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(server_data, indent=2)}
            ],
            response_format={"type": "json_object"},
            temperature=0.1  # Low temp for consistent analysis
        )

        return json.loads(response.choices[0].message.content)

    def analyze_fleet(self, all_servers_data):
        """Analyze entire server fleet for optimization opportunities."""
        system_prompt = """You are an expert infrastructure optimization analyst.
Analyze the entire server fleet and provide:
{
    "overall_health": "healthy|degraded|critical",
    "total_servers": N,
    "healthy_count": N,
    "warning_count": N,
    "critical_count": N,
    "idle_servers": [{"id": ..., "name": ..., "days_idle": ...}],
    "overloaded_servers": [{"id": ..., "name": ..., "issue": ...}],
    "cost_optimization": {
        "potential_monthly_savings": "$X",
        "recommendations": ["..."]
    },
    "anomalies": [{"server": ..., "anomaly": ..., "severity": ...}],
    "capacity_predictions": ["Server X disk will be full in Y days"],
    "top_recommendations": ["ranked list of most important actions"],
    "daily_summary": "A brief paragraph summarizing fleet health"
}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(all_servers_data, indent=2)}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )

        return json.loads(response.choices[0].message.content)

    def chat(self, user_message, context_data, chat_history=None):
        """AI chat that can answer questions about server infrastructure."""
        system_prompt = f"""You are an AI assistant for server infrastructure management.
You have access to real-time server monitoring data.

CURRENT SERVER DATA:
{json.dumps(context_data, indent=2)}

Answer the user's questions based on this data. Be specific with server names,
IP addresses, and metric values. If you recommend actions, be precise about
which servers and what to do. Format your responses clearly with bullet points
and sections when appropriate."""

        messages = [{"role": "system", "content": system_prompt}]

        if chat_history:
            messages.extend(chat_history)

        messages.append({"role": "user", "content": user_message})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3
        )

        return response.choices[0].message.content
```

---

## Part 3: AI Features — What AI Does Automatically

### Feature 1: Automatic Health Assessment (Every 30 Minutes)

**What happens:**
1. Cron job collects last 30 minutes of metrics for all servers
2. Sends structured data to AI
3. AI returns health status, risk scores, and recommendations
4. Odoo updates every server record with AI analysis
5. Dashboard shows AI-generated health badges and recommendations

**What you see:** Each server card on your dashboard shows:
- Green/Yellow/Red health badge (set by AI)
- Risk score (0-100)
- One-line AI summary ("CPU trending up 15% over past week, monitor closely")
- Recommendations ("Consider scaling up before month-end traffic spike")

### Feature 2: Idle Server Detection (Daily)

**What happens:**
1. AI receives 7-day (or configurable) metric history for all servers
2. AI identifies servers with consistently low utilization
3. AI assesses *why* they might be idle (test env, old project, forgotten)
4. AI recommends: decommission, consolidate, reallocate, or keep

**What you see:** An "Idle Servers" section on dashboard with AI explanation:
```
Server-22 (test-env-old):
  Status: IDLE for 23 days
  Avg CPU: 1.2% | RAM: 8% | Disk: 15%
  AI Says: "This appears to be an abandoned test environment.
           No active network connections detected in 23 days.
           Recommendation: Decommission and reclaim resources.
           Estimated savings: $180/month"
```

### Feature 3: Anomaly Detection (Continuous)

**What happens:**
1. When metrics are collected, Python code checks for threshold breaches
2. When unusual patterns are detected (CPU spike, memory leak, disk growth rate), AI is called
3. AI analyzes the pattern and explains what is happening
4. Alert is created with AI explanation

**Example AI Alert Analysis:**
```
Alert: HighMemory on Server-15 (db-production)
AI Analysis: "Memory has been steadily increasing by ~200MB/hour
             for the past 6 hours, indicating a potential memory leak.
             Current: 91% (14.5GB / 16GB).
             Top memory consumers: PostgreSQL (8.2GB), Java (3.1GB).
             
             Root Cause Hypothesis: The Java application appears to
             have a memory leak — its memory grew from 1.2GB to 3.1GB
             in 6 hours without corresponding increase in requests.
             
             Immediate Action: Restart the Java application.
             Long-term: Investigate Java heap configuration and
             potential memory leak in the application code."
```

### Feature 4: AI Chat (On-Demand)

Users can ask natural language questions and get data-driven answers:

| User Question | AI Can Answer Because... |
|---|---|
| "Which servers are idle?" | AI has access to all server metrics |
| "What will run out of disk first?" | AI can calculate disk growth rates |
| "Compare Server-5 and Server-12 performance" | AI can pull and compare metrics |
| "Should I approve this allocation request for 16GB RAM?" | AI can check which idle servers have 16GB+ |
| "Generate a report of last month's incidents" | AI has access to alert history |
| "What's our total cloud cost this month?" | AI has access to cost data |
| "Predict capacity needs for next quarter" | AI can analyze trends and growth rates |

### Feature 5: Smart Allocation Recommendations

When someone requests a server allocation:
1. AI reads the request requirements (CPU, RAM, purpose)
2. AI scans all idle/underutilized servers
3. AI recommends the best match
4. If no match, AI recommends new server specs

### Feature 6: Daily Summary Email (Morning Briefing)

Every morning, AI generates a report and emails it:

```
Subject: Daily Server Fleet Health Report — Feb 20, 2026

Good morning,

FLEET OVERVIEW:
• 47 servers monitored | 41 healthy | 4 warning | 2 critical
• 5 servers flagged as idle (potential savings: $1,200/month)

CRITICAL ISSUES (Action Required):
1. Server-08 (db-replica-02): Disk at 94%, growing 2GB/day
   → Will be full in ~3 days. Immediate cleanup needed.
   
2. Server-31 (app-server-prod): CPU averaged 92% yesterday
   → Performance degradation likely. Scale up recommended.

WARNINGS:
3. Server-15: Memory slowly increasing (potential leak)
4. Server-22: Network errors increasing (check NIC/cables)
5. Server-18: SSL certificate expires in 7 days
6. Server-09: 3 failed login attempts detected

IDLE SERVERS (Decommission Candidates):
7. Server-12, Server-35, Server-41, Server-44, Server-47
   (All < 5% CPU for 14+ days)

TOP RECOMMENDATION:
Consolidate Server-12 and Server-35 workloads onto Server-47,
then decommission 12 and 35. Estimated savings: $360/month.

— Your AI Infrastructure Assistant
```

---

## Part 4: Using Cursor AI for Development

### How to Use Cursor Effectively for This Project

You have Cursor AI — use it as your development partner:

#### Step 1: Set Up Context

In Cursor, add these files to your context:
- The Odoo source code (for reference)
- Your module files
- The Prometheus API documentation
- The OpenAI API documentation

#### Step 2: Development Workflow with Cursor

```
1. Tell Cursor: "Create the server.monitoring.server model with these fields: [paste from design doc]"
   → Cursor generates the Python model code

2. Tell Cursor: "Create the XML form view and tree view for this model"
   → Cursor generates the Odoo XML views

3. Tell Cursor: "Create the Prometheus service class that queries /api/v1/query"
   → Cursor generates the API client

4. Tell Cursor: "Create the cron job that collects metrics every 5 minutes"
   → Cursor generates the cron job and Python method

5. Tell Cursor: "Create the ECharts dashboard component for Odoo 14/19"
   → Cursor generates the JavaScript dashboard

6. Tell Cursor: "Create the AI chat widget with WebSocket support"
   → Cursor generates the chat component
```

#### Step 3: Use Cursor for Debugging

When something doesn't work:
- Share the error traceback with Cursor
- Share the relevant code files
- Cursor will identify the issue and suggest fixes

#### Step 4: Use Cursor for Testing

Tell Cursor:
- "Write unit tests for the prometheus_service.py"
- "Write integration tests for the metric collection cron job"
- "Write a test for the AI analysis workflow"

---

## Part 5: Using ChatGPT Premium for Research & Planning

### How to Use ChatGPT Effectively

Since you have ChatGPT Premium, use it for:

1. **Research Questions:**
   - "What are the best PromQL queries for detecting idle servers?"
   - "How to implement WebSocket in Odoo 14?"
   - "Best practices for storing time-series data in PostgreSQL"

2. **Architecture Review:**
   - Paste your architecture docs and ask "Review this architecture for scalability issues"
   - "What are the security concerns with this design?"

3. **Prompt Engineering:**
   - "Help me write the optimal system prompt for server health analysis"
   - "How should I structure the metrics data for best AI analysis results?"

4. **Code Review:**
   - Paste your code and ask "Review this Odoo model for best practices"
   - "Is this PromQL query efficient for 200 servers?"

---

## Part 6: Local LLM Alternative (Ollama)

If you want to reduce API costs or keep data private, you can run AI locally:

### Install Ollama

```bash
curl -fsSL https://ollama.ai/install.sh | sh

# Download a model (Llama 3 is excellent for this use case)
ollama pull llama3.1:8b          # 8B params, fast, needs 8GB VRAM
ollama pull llama3.1:70b         # 70B params, better quality, needs 40GB VRAM
ollama pull mistral:7b           # Alternative, very capable

# Ollama provides an OpenAI-compatible API at http://localhost:11434
```

### Using Ollama with the Same Code

The beautiful thing: **Ollama provides an OpenAI-compatible API**. So the same code works:

```python
# Just change the base_url and model
ai_service = AIService(
    api_key='ollama',  # Ollama doesn't need a real key
    model='llama3.1:8b',
    base_url='http://localhost:11434/v1'
)
```

### When to Use Local vs Cloud AI

| Scenario | Recommendation | Why |
|---|---|---|
| Development & testing | Local (Ollama) | Free, fast iteration |
| Routine health checks | Local (Ollama) | Free, data stays private |
| Complex fleet analysis | Cloud (GPT-4o) | Better reasoning for complex tasks |
| AI chat (user-facing) | Cloud (GPT-4o-mini) | Better conversational quality |
| Sensitive data | Local (Ollama) | Data never leaves your network |

---

## Part 7: AI Integration with Odoo — Technical Details

### How AI Service Connects to Odoo Models

```python
# In your Odoo model (server.py):

class ServerMonitoringServer(models.Model):
    _name = 'server.monitoring.server'

    def action_run_ai_analysis(self):
        """Triggered manually or by cron job."""
        config = self.env['server.monitoring.config'].get_config()
        ai_service = AIService(
            api_key=config.ai_api_key,
            model=config.ai_model,
            base_url=config.ai_base_url or None
        )

        for server in self:
            # Gather recent metrics
            metrics = server._get_recent_metrics(hours=1)
            
            # Build structured data for AI
            server_data = {
                'name': server.name,
                'ip': server.ip_address,
                'os': server.os_type,
                'cpu_cores': server.cpu_cores,
                'ram_total_gb': server.ram_total_gb,
                'current_metrics': {
                    'cpu_usage': server.cpu_usage_percent,
                    'ram_usage': server.ram_usage_percent,
                    'disk_usage': server.disk_usage_percent,
                    'load_avg': [server.load_average_1m, server.load_average_5m, server.load_average_15m],
                },
                'metrics_history': metrics,
                'active_alerts': [a.alert_name for a in server.alert_ids.filtered(lambda a: a.state == 'firing')],
                'uptime_days': server.uptime_seconds / 86400 if server.uptime_seconds else 0,
            }

            # Call AI
            analysis = ai_service.analyze_server_health(server_data)

            # Update server record
            server.write({
                'ai_summary': analysis.get('summary', ''),
                'ai_recommendation': '\n'.join(analysis.get('recommendations', [])),
                'ai_risk_score': analysis.get('risk_score', 0),
                'ai_last_analysis': fields.Datetime.now(),
                'health_status': analysis.get('health_status', 'unknown'),
            })

            # Create analysis log
            self.env['server.monitoring.ai.analysis'].create({
                'server_id': server.id,
                'analysis_type': 'health_check',
                'trigger': 'scheduled',
                'input_data': json.dumps(server_data),
                'ai_response': json.dumps(analysis),
                'summary': analysis.get('summary', ''),
                'risk_score': analysis.get('risk_score', 0),
                'recommendations': '\n'.join(analysis.get('recommendations', [])),
                'model_used': config.ai_model,
            })
```

### AI Prompt Templates

Store prompt templates in Odoo so they can be customized without code changes:

| Template Name | Purpose | When Used |
|---|---|---|
| `health_check_prompt` | Individual server health analysis | Every 30 min per server |
| `fleet_analysis_prompt` | Entire fleet overview | Daily |
| `anomaly_explanation_prompt` | Explain detected anomaly | When alert fires |
| `chat_system_prompt` | Context for AI chat | Every chat message |
| `allocation_recommendation_prompt` | Suggest server for allocation | On new allocation request |
| `daily_summary_prompt` | Morning briefing email | Daily at 7 AM |
| `idle_detection_prompt` | Identify truly idle servers | Daily |
| `capacity_prediction_prompt` | Predict future capacity needs | Weekly |

---

## Part 8: Cost Estimation for AI

### OpenAI API Costs (Approximate)

| Operation | Frequency | Tokens per Call | Monthly Cost (50 servers) |
|---|---|---|---|
| Health check per server | 48/day (every 30 min) | ~2,000 | ~$7/month (gpt-4o-mini) |
| Fleet analysis | 1/day | ~10,000 | ~$0.20/month |
| AI chat messages | ~50/day | ~3,000 | ~$5/month |
| Alert analysis | ~5/day | ~2,000 | ~$0.10/month |
| Daily summary | 1/day | ~5,000 | ~$0.10/month |
| **Total estimate** | | | **~$12-15/month** |

### Cost Optimization Tips

1. **Use `gpt-4o-mini` for routine checks** — 30x cheaper than `gpt-4o`
2. **Batch servers in fleet analysis** instead of analyzing one by one
3. **Cache AI responses** — don't re-analyze if metrics haven't changed significantly
4. **Use local Ollama** for development and testing — $0 cost
5. **Rate limit AI calls** — if 10 alerts fire simultaneously, batch them into one AI call

---

## Summary: What You Need to Do

| Step | Action | Tool |
|---|---|---|
| 1 | Get OpenAI API key | https://platform.openai.com |
| 2 | Configure API key in Odoo monitoring settings | Odoo UI |
| 3 | (Optional) Install Ollama for local AI | Terminal |
| 4 | AI features work automatically via cron jobs | Nothing — automatic |
| 5 | Use AI chat from the dashboard | Odoo UI |
| 6 | Use Cursor AI to help build the module | Cursor IDE |
| 7 | Use ChatGPT to research and refine | Browser |
