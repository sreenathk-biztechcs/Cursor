# 08 — SaaS Tool Tracking

## How to Track Cursor, ChatGPT, and Any Other SaaS Service

---

## Overview

Your company uses SaaS tools like Cursor IDE and ChatGPT Premium. This module tracks their usage, costs, and integrates the data into your Odoo dashboard alongside server metrics.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Cursor API  │    │ OpenAI API   │    │ Future APIs  │
│              │    │ (ChatGPT)    │    │ (GitHub,     │
│ Usage stats  │    │ Usage stats  │    │  Slack, etc) │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                    │
       └───────────────────┼────────────────────┘
                           │
                    ┌──────┴───────┐
                    │  Odoo Cron   │
                    │  Job         │
                    │  (Periodic   │
                    │   sync)      │
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │  saas.usage  │
                    │  model       │
                    │              │
                    │  Stored in   │
                    │  Odoo DB     │
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │  Dashboard   │
                    │  Widgets     │
                    └──────────────┘
```

---

## 1. ChatGPT / OpenAI Usage Tracking

### What Data You Can Track

| Metric | Source | API Endpoint |
|---|---|---|
| API calls per day | OpenAI Usage API | `/v1/organization/usage` |
| Tokens consumed | OpenAI Usage API | `/v1/organization/usage` |
| Cost per day | OpenAI Usage API | `/v1/organization/costs` |
| Per-model breakdown | OpenAI Usage API | `/v1/organization/usage` |
| Per-user breakdown | OpenAI Usage API | `/v1/organization/users` |
| Billing info | OpenAI Billing API | `/v1/dashboard/billing/usage` |

### How to Get Your API Key

1. Go to https://platform.openai.com/
2. Navigate to Settings → API Keys
3. Create a new key with "Usage Read" permissions
4. Store this key in Odoo's `saas.service` model

### What the Sync Process Looks Like

```
Odoo Cron (runs daily at midnight):
  1. Read saas.service where service_type = 'chatgpt'
  2. Call OpenAI Usage API with the stored API key
  3. Parse response: extract tokens, costs, calls per model
  4. Create saas.usage records for each metric
  5. If cost exceeds budget threshold → create alert
  6. Log sync timestamp
```

### Data Stored in Odoo

```
saas.usage records (example for one day):

| service    | date       | metric_name     | value    | unit   |
|------------|------------|-----------------|----------|--------|
| ChatGPT    | 2026-02-20 | api_calls       | 1,245    | calls  |
| ChatGPT    | 2026-02-20 | tokens_input    | 2,450,000| tokens |
| ChatGPT    | 2026-02-20 | tokens_output   | 890,000  | tokens |
| ChatGPT    | 2026-02-20 | cost_total      | 12.40    | USD    |
| ChatGPT    | 2026-02-20 | cost_gpt4o      | 8.20     | USD    |
| ChatGPT    | 2026-02-20 | cost_gpt4o_mini | 4.20     | USD    |
```

---

## 2. Cursor IDE Usage Tracking

### What is Cursor?

Cursor is an AI-powered code editor (fork of VS Code) that uses AI for code completion, chat, and editing. It has a premium subscription with usage limits.

### What Data You Can Track

| Metric | Description |
|---|---|
| Active users | How many team members are using Cursor |
| AI completions | Number of AI code completions used |
| Chat messages | Number of AI chat interactions |
| Premium requests | Fast/premium model requests used |
| Subscription status | Active/expired/limit reached |

### How to Get Usage Data

Cursor's usage data can be accessed through:

1. **Cursor Dashboard** (https://cursor.com/settings): Manual viewing
2. **Cursor API** (if available): Programmatic access via API key
3. **Browser automation**: If no API is available, use a scheduled script to scrape the dashboard

### Sync Strategy

```
Option A (If Cursor has API):
  Odoo Cron → Cursor API → parse JSON → store in saas.usage

Option B (If no API, use dashboard scraping):
  Odoo Cron → Playwright/Selenium → login to Cursor dashboard → 
  extract usage data → store in saas.usage

Option C (Manual entry with smart form):
  User pastes usage data from Cursor dashboard → 
  Odoo parses and stores it → 
  (Least automatic, but simplest to implement)
```

### Recommendation

Start with **Option C** (manual entry), then upgrade to **Option A** if/when Cursor provides a proper API. The data model is the same regardless of how data is collected.

---

## 3. Generic SaaS Connector Framework

The system is designed to be extensible. Adding a new SaaS service requires:

### Step 1: Create Service Record

In Odoo UI: SaaS Tracking → Services → Create
- Name: "GitHub"
- Type: Custom
- API Endpoint: `https://api.github.com`
- API Key: `ghp_xxxxxxxxxxxx`
- Sync Frequency: Daily

### Step 2: Implement Connector

Each service type has a connector class. The connector is responsible for:
- Authenticating with the API
- Fetching usage/billing data
- Transforming data into `saas.usage` records

### Connector Pattern

```
Base class: SaaSConnector
  - authenticate()
  - fetch_usage(date_from, date_to)
  - transform_data(raw_data) → list of saas.usage values
  - sync()  ← called by cron

Subclasses:
  - OpenAIConnector(SaaSConnector)
  - CursorConnector(SaaSConnector)
  - GitHubConnector(SaaSConnector)
  - CustomConnector(SaaSConnector)  ← configurable via JSON
```

### Adding Future Services

| Service | What to Track | API Available? |
|---|---|---|
| GitHub | Repos, actions minutes, storage, seats | Yes (REST + GraphQL) |
| Slack | Messages, active users, storage | Yes (REST) |
| AWS | EC2 instances, costs, usage | Yes (Cost Explorer API) |
| Azure | VMs, costs, usage | Yes (Cost Management API) |
| Google Cloud | Compute, costs, usage | Yes (Billing API) |
| Jira | Issues, sprints, time tracking | Yes (REST) |
| Notion | Pages, users, API calls | Limited |
| Vercel | Deployments, bandwidth, builds | Yes (REST) |

---

## 4. Dashboard Widgets for SaaS

### Cost Overview Widget

```
┌──────────────────────────────────────────────────────┐
│  SaaS Costs — February 2026                          │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ ChatGPT  │  │ Cursor   │  │ GitHub   │          │
│  │ $186.40  │  │ $480.00  │  │ $44.00   │          │
│  │ ▲ 12%    │  │ ─ 0%     │  │ ▼ 5%    │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│                                                      │
│  Total: $710.40 / Budget: $1,000.00                  │
│  ████████████████████████░░░░░░░░  71%               │
│                                                      │
│  [View Details]                                      │
└──────────────────────────────────────────────────────┘
```

### Usage Trend Widget

```
┌──────────────────────────────────────────────────────┐
│  ChatGPT Usage — Last 30 Days                        │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │                    ╱╲                           │  │
│  │         ╱╲       ╱  ╲      ╱╲                 │  │
│  │  ──────╱  ╲─────╱    ╲────╱  ╲────────        │  │
│  │                                                │  │
│  │  Jan 21                              Feb 20   │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  Avg: 1,200 calls/day | Peak: 2,100 (Feb 5)        │
│  Total tokens: 45.2M | Total cost: $186.40          │
└──────────────────────────────────────────────────────┘
```

---

## 5. Budget Alerts

Configure per-service budgets and get alerts when approaching limits.

| Alert | Condition | Action |
|---|---|---|
| 75% Budget | Monthly cost reaches 75% of budget | Info notification |
| 90% Budget | Monthly cost reaches 90% of budget | Warning notification |
| 100% Budget | Monthly cost exceeds budget | Critical alert, email to finance |
| Unusual spike | Daily cost > 3x average | Warning notification |

---

## 6. AI Integration with SaaS Data

The AI agent can answer questions about SaaS usage:

```
User: "How much are we spending on AI tools this month?"
AI:   "Total AI tool spending for February 2026:
       - ChatGPT API: $186.40 (12,450 API calls, 45.2M tokens)
       - Cursor Pro: $480.00 (24 seats × $20/month)
       - Total: $666.40
       
       This is within your $1,000 monthly budget (67% used).
       ChatGPT costs increased 12% from January, primarily due
       to increased GPT-4o usage by the engineering team."

User: "Who is using the most ChatGPT tokens?"
AI:   "Top 5 ChatGPT users this month:
       1. john.doe:    8,200 calls, 12.1M tokens ($48.20)
       2. jane.smith:  6,100 calls, 9.8M tokens  ($38.40)
       3. bob.wilson:  4,300 calls, 7.2M tokens  ($28.10)
       4. alice.chen:  3,800 calls, 5.9M tokens  ($22.60)
       5. tom.brown:   2,100 calls, 3.4M tokens  ($13.20)
       
       Note: john.doe's usage spiked 40% this week, likely due
       to the new feature development sprint."
```
