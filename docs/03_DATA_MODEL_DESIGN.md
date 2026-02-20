# 03 — Odoo Data Model Design

## Complete Model Definitions, Fields, and Relationships

This document defines every Odoo model you will create, their fields, relationships, and how they interact.

---

## Entity Relationship Overview

```
                        ┌──────────────────┐
                        │  res.users        │
                        │  (Odoo built-in)  │
                        └────────┬─────────┘
                                 │ owner_id / requested_by
                                 │
┌──────────────┐    ┌────────────┴──────────┐    ┌──────────────────┐
│ server.       │    │  server.server        │    │ server.metric    │
│ category      │───>│  (Main Model)         │<───│ (Time-Series)    │
│               │    │                       │    │                  │
│ Web, DB,      │    │ name, ip, os,         │    │ cpu, ram, disk,  │
│ App, Test     │    │ status, specs         │    │ network, ts      │
└──────────────┘    └────────┬──────────────┘    └──────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              v              v              v
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│ server.       │  │ server.alert │  │ server.ai.       │
│ request       │  │              │  │ analysis          │
│               │  │ threshold    │  │                  │
│ approval      │  │ violations,  │  │ classification,  │
│ workflow      │  │ anomalies    │  │ insights,        │
└──────────────┘  └──────────────┘  │ recommendations  │
                                    └──────────────────┘

┌──────────────────┐    ┌──────────────────┐
│ saas.service     │───>│ saas.usage       │
│                  │    │                  │
│ Cursor, ChatGPT, │    │ tokens, calls,   │
│ any API service  │    │ costs, dates     │
└──────────────────┘    └──────────────────┘

┌──────────────────┐    ┌──────────────────┐
│ ai.chat.session  │───>│ ai.chat.message  │
│                  │    │                  │
│ user sessions    │    │ user & AI msgs   │
└──────────────────┘    └──────────────────┘
```

---

## Model 1: `server.category`

Categorizes servers by their purpose.

| Field | Type | Description |
|---|---|---|
| `name` | Char (required) | Category name (e.g., "Web Server", "Database Server") |
| `code` | Char | Short code (e.g., "WEB", "DB", "APP") |
| `description` | Text | Description of this category |
| `color` | Integer | Color index for kanban view |
| `server_ids` | One2many → server.server | Servers in this category |
| `server_count` | Integer (computed) | Number of servers |

### Default Categories
- Web Server (WEB)
- Database Server (DB)
- Application Server (APP)
- Test/QA Server (TEST)
- Development Server (DEV)
- File/Storage Server (STOR)
- Mail Server (MAIL)
- CI/CD Server (CICD)

---

## Model 2: `server.server` (Main Model)

The core model representing a physical or virtual server.

| Field | Type | Description |
|---|---|---|
| **Identity** | | |
| `name` | Char (required) | Server display name (e.g., "PROD-WEB-01") |
| `hostname` | Char | System hostname |
| `ip_address` | Char (required) | Primary IP address |
| `ip_address_public` | Char | Public IP (if different) |
| `mac_address` | Char | MAC address |
| `fqdn` | Char | Fully Qualified Domain Name |
| **Classification** | | |
| `category_id` | Many2one → server.category | Server category |
| `tag_ids` | Many2many → server.tag | Tags for flexible grouping |
| `environment` | Selection | production / staging / development / testing |
| `server_type` | Selection | physical / virtual / cloud / container |
| `cloud_provider` | Selection | none / aws / azure / gcp / digitalocean / other |
| **Specifications** | | |
| `os_name` | Char | Operating system (e.g., "Ubuntu 22.04 LTS") |
| `os_family` | Selection | linux / windows / macos / other |
| `cpu_cores` | Integer | Number of CPU cores |
| `cpu_model` | Char | CPU model name |
| `ram_total_gb` | Float | Total RAM in GB |
| `disk_total_gb` | Float | Total disk space in GB |
| `disk_type` | Selection | ssd / hdd / nvme |
| **Network** | | |
| `ssh_port` | Integer (default=22) | SSH port |
| `ssh_user` | Char | SSH username for monitoring |
| `ssh_key_id` | Many2one → server.ssh.key | SSH private key reference |
| `api_key` | Char | API key for this server's monitoring agent |
| **Ownership** | | |
| `owner_id` | Many2one → res.users | Server owner/responsible person |
| `department_id` | Many2one → hr.department | Owning department |
| `project` | Char | Associated project name |
| **Location** | | |
| `datacenter` | Char | Data center name |
| `rack` | Char | Rack number/location |
| `location_notes` | Text | Additional location info |
| **Status & Lifecycle** | | |
| `state` | Selection (required) | draft / requested / approved / allocated / active / inactive / maintenance / decommissioned |
| `monitoring_state` | Selection (computed) | healthy / warning / critical / down / unknown |
| `is_monitored` | Boolean | Whether monitoring is enabled |
| `date_requested` | Date | When server was requested |
| `date_approved` | Date | When request was approved |
| `date_allocated` | Date | When server was allocated |
| `date_activated` | Date | When monitoring started |
| `date_decommissioned` | Date | When server was removed |
| **Live Metrics (Computed)** | | |
| `cpu_usage_current` | Float (computed) | Latest CPU usage % |
| `ram_usage_current` | Float (computed) | Latest RAM usage % |
| `disk_usage_current` | Float (computed) | Latest Disk usage % |
| `uptime_days` | Float (computed) | Days since last boot |
| `last_metric_time` | Datetime (computed) | When the last metric was received |
| `last_seen_ago` | Char (computed) | Human-readable "5 minutes ago" |
| **AI Analysis** | | |
| `ai_classification` | Selection | active / idle / underutilized / overloaded / down |
| `ai_health_score` | Float | 0-100 health score from AI |
| `ai_summary` | Text | AI-generated summary of server status |
| `ai_last_analysis` | Datetime | When AI last analyzed this server |
| **Relations** | | |
| `metric_ids` | One2many → server.metric | All metric records |
| `alert_ids` | One2many → server.alert | All alerts |
| `analysis_ids` | One2many → server.ai.analysis | All AI analysis records |
| `request_ids` | One2many → server.request | Related requests |
| **Counts (Computed)** | | |
| `metric_count` | Integer (computed) | Total metric records |
| `alert_count` | Integer (computed) | Active alert count |
| `open_alert_count` | Integer (computed) | Unresolved alert count |

### State Flow
```
draft → requested → approved → allocated → active ⇄ inactive
                                              │          │
                                              ├→ maintenance →┘
                                              │
                                              └→ decommissioned
```

---

## Model 3: `server.tag`

Flexible tagging system for servers.

| Field | Type | Description |
|---|---|---|
| `name` | Char (required) | Tag name |
| `color` | Integer | Color index |
| `server_ids` | Many2many → server.server | Tagged servers |

---

## Model 4: `server.ssh.key`

Stores SSH key references for server access.

| Field | Type | Description |
|---|---|---|
| `name` | Char (required) | Key name/label |
| `private_key_path` | Char | Path to private key file on Odoo server |
| `fingerprint` | Char | Key fingerprint |
| `notes` | Text | Additional notes |

---

## Model 5: `server.request`

Approval workflow for server allocation.

| Field | Type | Description |
|---|---|---|
| `name` | Char (computed) | Auto-generated sequence (REQ-001) |
| `server_id` | Many2one → server.server | Related server (created after approval) |
| `requested_by` | Many2one → res.users | Who requested |
| `approved_by` | Many2one → res.users | Who approved |
| `state` | Selection | draft / submitted / under_review / approved / rejected / cancelled |
| `purpose` | Text (required) | Why the server is needed |
| `specifications` | Text | Requested specs (CPU, RAM, etc.) |
| `category_id` | Many2one → server.category | Requested server type |
| `environment` | Selection | production / staging / development / testing |
| `priority` | Selection | low / medium / high / critical |
| `date_requested` | Datetime | Submission time |
| `date_reviewed` | Datetime | Review time |
| `date_approved` | Datetime | Approval time |
| `rejection_reason` | Text | If rejected, why |
| `notes` | Text | Additional notes |

---

## Model 6: `server.metric`

Time-series metric data from monitoring agents.

| Field | Type | Description |
|---|---|---|
| `server_id` | Many2one → server.server (required, indexed) | Which server |
| `metric_type` | Selection (required, indexed) | cpu / ram / disk / network_in / network_out / disk_io_read / disk_io_write / load_1m / load_5m / load_15m / process_count / swap / uptime |
| `value` | Float (required) | Metric value |
| `unit` | Char | Unit of measurement (%, GB, MB/s, etc.) |
| `timestamp` | Datetime (required, indexed) | When the metric was recorded |
| `source` | Selection | telegraf / node_exporter / custom_agent / ssh |
| `details` | Text | Additional JSON details (per-core CPU, per-disk usage, etc.) |

### Indexing Strategy
- Compound index on `(server_id, metric_type, timestamp)` for fast time-range queries
- This is critical for dashboard performance

### Data Volume Estimate
- 1 server, 10 metric types, every 60 seconds = 600 records/hour = 14,400/day
- 20 servers = 288,000 records/day
- **Data retention**: Keep detailed metrics for 30 days, aggregate to hourly for 90 days, daily for 1 year

---

## Model 7: `server.metric.summary`

Aggregated metric data for efficient long-term storage and dashboard queries.

| Field | Type | Description |
|---|---|---|
| `server_id` | Many2one → server.server (indexed) | Which server |
| `metric_type` | Selection (indexed) | Same as server.metric |
| `period` | Selection | hourly / daily / weekly / monthly |
| `date_start` | Datetime (indexed) | Start of the period |
| `value_avg` | Float | Average value in the period |
| `value_min` | Float | Minimum value |
| `value_max` | Float | Maximum value |
| `value_p95` | Float | 95th percentile |
| `sample_count` | Integer | Number of data points aggregated |

---

## Model 8: `server.alert`

Alert records generated by monitoring rules and AI analysis.

| Field | Type | Description |
|---|---|---|
| `name` | Char (computed) | Alert title |
| `server_id` | Many2one → server.server | Affected server |
| `alert_type` | Selection | cpu_high / ram_high / disk_full / server_down / network_issue / anomaly / ai_insight |
| `severity` | Selection | info / warning / critical / emergency |
| `state` | Selection | active / acknowledged / resolved / silenced |
| `message` | Text | Alert description |
| `metric_value` | Float | The value that triggered the alert |
| `threshold_value` | Float | The threshold that was exceeded |
| `triggered_at` | Datetime | When the alert fired |
| `acknowledged_at` | Datetime | When someone acknowledged it |
| `resolved_at` | Datetime | When it was resolved |
| `acknowledged_by` | Many2one → res.users | Who acknowledged |
| `auto_resolved` | Boolean | Whether the system auto-resolved it |
| `ai_recommendation` | Text | AI suggestion for fixing the issue |

---

## Model 9: `server.alert.rule`

Configurable alert rules (thresholds).

| Field | Type | Description |
|---|---|---|
| `name` | Char (required) | Rule name |
| `metric_type` | Selection | Which metric to watch |
| `operator` | Selection | greater_than / less_than / equals / not_equals |
| `threshold` | Float | Threshold value |
| `duration_minutes` | Integer | How long condition must persist |
| `severity` | Selection | warning / critical / emergency |
| `is_active` | Boolean (default=True) | Whether rule is enabled |
| `server_ids` | Many2many → server.server | Apply to specific servers (empty = all) |
| `category_ids` | Many2many → server.category | Apply to server categories |
| `notification_channel` | Selection | email / discuss / slack / telegram |
| `notification_user_ids` | Many2many → res.users | Who to notify |

### Default Rules
| Rule | Metric | Threshold | Duration | Severity |
|---|---|---|---|---|
| High CPU | cpu | > 90% | 15 min | warning |
| Critical CPU | cpu | > 95% | 5 min | critical |
| High Memory | ram | > 90% | 10 min | warning |
| Disk Full | disk | > 90% | instant | critical |
| Server Down | last_metric | > 5 min ago | instant | emergency |
| Server Idle | cpu | < 5% | 7 days | info |

---

## Model 10: `server.ai.analysis`

Stores AI analysis results for each server.

| Field | Type | Description |
|---|---|---|
| `server_id` | Many2one → server.server | Analyzed server |
| `analysis_date` | Datetime | When analysis was performed |
| `classification` | Selection | active / idle / underutilized / overloaded / down |
| `health_score` | Float | 0-100 |
| `summary` | Text | Natural language summary |
| `insights` | Text | Detailed insights (JSON or formatted text) |
| `recommendations` | Text | AI recommendations |
| `metrics_snapshot` | Text | JSON snapshot of metrics used for analysis |
| `model_used` | Char | AI model used (e.g., "gpt-4o", "llama3.1") |
| `confidence` | Float | Confidence score 0-1 |

---

## Model 11: `saas.service`

External SaaS services to track.

| Field | Type | Description |
|---|---|---|
| `name` | Char (required) | Service name (e.g., "Cursor", "ChatGPT") |
| `service_type` | Selection | cursor / chatgpt / github / custom |
| `api_endpoint` | Char | API base URL |
| `api_key` | Char | API key / token |
| `api_secret` | Char | API secret (if needed) |
| `is_active` | Boolean | Whether tracking is enabled |
| `sync_frequency` | Selection | hourly / daily / weekly |
| `last_sync` | Datetime | Last successful sync |
| `config_json` | Text | Additional JSON configuration |
| `usage_ids` | One2many → saas.usage | Usage records |
| `monthly_budget` | Float | Monthly budget limit |
| `currency_id` | Many2one → res.currency | Currency |

---

## Model 12: `saas.usage`

Usage tracking for SaaS services.

| Field | Type | Description |
|---|---|---|
| `service_id` | Many2one → saas.service (indexed) | Which service |
| `date` | Date (indexed) | Usage date |
| `user_id` | Many2one → res.users | Which user (if per-user tracking) |
| `metric_name` | Char | What's being measured (e.g., "api_calls", "tokens", "cost") |
| `value` | Float | Metric value |
| `unit` | Char | Unit (calls, tokens, USD, etc.) |
| `details` | Text | Additional JSON details |

---

## Model 13: `ai.chat.session`

AI chat conversation sessions.

| Field | Type | Description |
|---|---|---|
| `name` | Char (computed) | Session title (auto-generated from first message) |
| `user_id` | Many2one → res.users | Who is chatting |
| `message_ids` | One2many → ai.chat.message | Messages in session |
| `created_at` | Datetime | Session start |
| `last_activity` | Datetime | Last message time |
| `is_active` | Boolean | Whether session is active |
| `context_server_id` | Many2one → server.server | If chat is about a specific server |
| `message_count` | Integer (computed) | Number of messages |

---

## Model 14: `ai.chat.message`

Individual messages in an AI chat session.

| Field | Type | Description |
|---|---|---|
| `session_id` | Many2one → ai.chat.session | Parent session |
| `role` | Selection | user / assistant / system |
| `content` | Text | Message content |
| `timestamp` | Datetime | When the message was sent |
| `tokens_used` | Integer | Tokens consumed by this message |
| `model_used` | Char | AI model used |
| `function_calls` | Text | JSON of any function calls made by AI |
| `attachments` | Text | JSON references to charts/data generated |

---

## Model 15: `server.monitoring.config`

Global configuration for the monitoring system.

| Field | Type | Description |
|---|---|---|
| `name` | Char | Config key |
| `value` | Text | Config value |
| `description` | Text | What this setting does |

### Configuration Keys
| Key | Default | Description |
|---|---|---|
| `metric_retention_days` | 30 | Days to keep detailed metrics |
| `summary_retention_days` | 365 | Days to keep summary metrics |
| `ai_analysis_frequency` | 60 | Minutes between AI analysis runs |
| `default_alert_email` | (empty) | Default email for alerts |
| `openai_api_key` | (empty) | OpenAI API key |
| `openai_model` | gpt-4o | Default AI model |
| `dashboard_refresh_seconds` | 30 | Dashboard auto-refresh interval |

---

## Database Indexes (Critical for Performance)

```sql
-- server.metric: Most queried table
CREATE INDEX idx_metric_server_type_ts ON server_metric (server_id, metric_type, timestamp DESC);
CREATE INDEX idx_metric_timestamp ON server_metric (timestamp DESC);

-- server.metric.summary
CREATE INDEX idx_summary_server_type_period ON server_metric_summary (server_id, metric_type, period, date_start DESC);

-- server.alert
CREATE INDEX idx_alert_server_state ON server_alert (server_id, state);
CREATE INDEX idx_alert_severity ON server_alert (severity, state);

-- saas.usage
CREATE INDEX idx_usage_service_date ON saas_usage (service_id, date DESC);
```

---

## Odoo 14 vs 19 Model Differences

The model definitions are **identical** between Odoo 14 and 19. The only differences are:

| Aspect | Odoo 14 | Odoo 19 |
|---|---|---|
| `_inherit` syntax | Same | Same |
| Field types | Same | May have newer field options |
| Computed fields | `@api.depends` | Same (possibly new decorators) |
| Access rights | `ir.model.access.csv` | Same |
| Record rules | `ir.rule` XML | Same |
| Module manifest | `__manifest__.py` | Same structure, new keys possible |
