# 10 — FAQ & Troubleshooting

## Common Questions and Solutions

---

## General Questions

### Q: Do I need to know Grafana to build this?

**No.** This system is built entirely within Odoo. Grafana is only referenced as a visual inspiration for the dashboard. You use Chart.js or ECharts (JavaScript charting libraries) to create similar visualizations directly inside Odoo. No Grafana installation or knowledge is needed.

### Q: Can I still use Grafana alongside this system?

**Yes.** If you already have Grafana or want to use it for certain use cases, you can:
- Have Telegraf send data to both Odoo and Grafana's data source (InfluxDB/Prometheus)
- Embed Grafana panels in Odoo using iframes (quick but less integrated)
- Use the Odoo dashboard as your primary view and Grafana for deep-dive technical analysis

### Q: How much will the AI features cost per month?

Estimated costs for a 20-server setup:

| Component | Monthly Cost |
|---|---|
| Hourly AI analysis (GPT-4o-mini) | $15-30 |
| Daily reports (GPT-4o-mini) | $1-3 |
| AI Chat (depends on usage, GPT-4o) | $10-50 |
| **Total with cloud AI** | **$26-83** |
| **Total with Ollama (local)** | **$0** (just electricity) |

### Q: Can I build this without AI features?

**Yes.** The AI features are additive. You can build:
- Phase 1 (Server Registry) — No AI needed
- Phase 2 (Monitoring) — No AI needed
- Phase 3 (Dashboard) — No AI needed
- Phase 4 onwards — AI features

Even without AI, you get a fully functional server monitoring system with dashboards and alerts (using rule-based logic instead of AI).

### Q: How many servers can this handle?

| Servers | Performance | Special Requirements |
|---|---|---|
| 1-20 | Excellent | None, default Odoo setup |
| 20-50 | Good | Add database indexes, tune PostgreSQL |
| 50-100 | Good | Consider InfluxDB for metrics, dedicated DB server |
| 100-500 | Moderate | InfluxDB required, Odoo stores summaries only, multiple workers |
| 500+ | Possible | Full architecture review needed, consider microservices |

### Q: What if I only have 5-10 servers?

This system works great even for small setups. The custom Python agent approach is perfect — lightweight, simple, and you can skip the complex parts (InfluxDB, Redis, etc.). Use OpenAI for AI features and PostgreSQL for everything.

---

## Technical Questions

### Q: What if a monitored server goes offline? How do I know?

The system detects offline servers in two ways:

1. **Agent-push model (Telegraf/custom)**: If no metrics are received for 5 minutes, the Odoo cron marks the server as "down" and fires an alert.

2. **SSH-pull model**: If Odoo can't SSH into the server, it immediately logs the failure and marks it as "down."

Both approaches create a `server.alert` record with severity "emergency" and send notifications.

### Q: How do I handle servers behind a firewall or NAT?

Options:
1. **VPN**: Connect all servers to a VPN. Monitoring traffic flows through the VPN.
2. **Reverse SSH tunnel**: Server creates an outbound SSH tunnel to Odoo server, Odoo connects back through the tunnel.
3. **Agent push only**: The agent on the server makes outbound HTTPS POST requests to Odoo (outbound traffic is usually allowed even with firewalls).
4. **Jump/bastion host**: For SSH-pull approach, use a jump host.

**Recommended**: Agent push (option 3) since it only requires outbound HTTPS from the monitored server.

### Q: Can I monitor Windows servers?

**Yes.** 
- Telegraf has full Windows support
- Custom Python agent with psutil works on Windows
- SSH-pull approach uses PowerShell commands instead of Linux commands

Telegraf on Windows collects: CPU, RAM, Disk, Network, Windows Performance Counters, Windows Services, IIS metrics, and more.

### Q: How do I handle SSH key management securely?

1. **Dedicated monitoring user**: Create a `monitor` user on each server with read-only access
2. **Separate SSH key**: Generate a key pair specifically for monitoring
3. **No sudo**: The monitoring user should not have sudo access
4. **Store key path in Odoo**: Store only the file path in `server.ssh.key`, not the key content
5. **Key rotation**: Rotate keys every 90 days using automation

### Q: What happens if Odoo itself goes down?

- Monitoring agents (Telegraf) will buffer data locally and send it when Odoo comes back
- Custom Python agents should implement local buffering (save to a file if HTTP POST fails)
- Historical data gap will exist but no data is permanently lost with Telegraf

### Q: How do I add a new metric type?

1. Add the new metric type to the `metric_type` selection field on `server.metric`
2. Update the monitoring agent configuration to collect the new metric
3. Add a dashboard widget/chart for the new metric
4. Optionally add alert rules for the new metric
5. Update AI prompts to include the new metric in analysis

---

## Implementation Questions

### Q: Should I start with Odoo 14 or 19?

| Start with Odoo 19 if... | Start with Odoo 14 if... |
|---|---|
| New installation, no legacy code | Existing Odoo 14 installation with data |
| Want modern frontend (OWL) | Team is familiar with Odoo 14 |
| Prefer latest features | Need long-term stability |
| Building for the future | Need to support older infrastructure |

If you need both, start with the backend (models, controllers, AI logic) which is identical, then build two frontend packages.

### Q: Can I use Cursor AI to help write the code?

**Absolutely.** Cursor is ideal for this project. Here's how to use it effectively:

1. **Module scaffolding**: Ask Cursor to generate the Odoo module structure
2. **Model definitions**: Describe the fields and let Cursor generate the Python classes
3. **Views**: Describe the UI and let Cursor generate XML views
4. **Controllers**: Describe the API endpoints and let Cursor generate the Python controllers
5. **JavaScript**: Describe the dashboard components and let Cursor generate OWL/Widget code
6. **AI integration**: Describe the LangChain agent and let Cursor help with the implementation

Tip: Feed these documentation files to Cursor as context when generating code.

### Q: How long does the initial setup take?

| Task | Time (with Cursor AI help) | Time (manual) |
|---|---|---|
| Module scaffold + basic models | 1-2 hours | 4-6 hours |
| Monitoring agent setup (1 server) | 30 minutes | 1-2 hours |
| Basic dashboard | 2-4 hours | 8-12 hours |
| AI integration | 2-4 hours | 6-10 hours |
| Full Phase 1-3 | 1-2 weeks | 4-6 weeks |

### Q: What if I don't have a GPU for local AI (Ollama)?

No problem. Use OpenAI's cloud API:
- GPT-4o-mini is very cheap (~$0.15 per million input tokens)
- No hardware requirements
- Just need an API key and internet connection
- Can always add Ollama later

### Q: How do I test the system?

1. **Local testing**: Install Odoo locally, create fake server records, use a script to simulate metric data
2. **Single server**: Set up monitoring on the Odoo server itself (monitor the monitor)
3. **Small pilot**: Pick 2-3 non-critical servers, deploy agents, run for a week
4. **Gradual rollout**: Add more servers one at a time, monitor for issues

---

## Troubleshooting

### Problem: Telegraf is not sending data to Odoo

**Check list:**
1. Is Telegraf running? `systemctl status telegraf`
2. Can Telegraf reach Odoo? `curl -X POST https://your-odoo.com/api/v1/metrics`
3. Is the API key correct? Check `X-API-Key` header matches `server.server.api_key`
4. Check Telegraf logs: `journalctl -u telegraf -f`
5. Is the Odoo endpoint returning 200? Check Odoo server logs

### Problem: Dashboard is slow to load

**Solutions:**
1. Add database indexes (see Data Model document)
2. Reduce the time range (show 1h instead of 24h by default)
3. Aggregate old metrics (run the aggregation cron)
4. Limit data points per chart (downsample to max 500 points)
5. Use `read_group()` instead of `search_read()` for aggregations
6. Check PostgreSQL slow query log

### Problem: AI analysis is expensive

**Solutions:**
1. Switch to GPT-4o-mini for routine analysis
2. Use Ollama for bulk classification (free)
3. Reduce analysis frequency (every 2-4 hours instead of hourly)
4. Batch analysis (analyze all servers in one API call)
5. Cache results — don't re-analyze if metrics haven't changed significantly
6. Use rule-based classification for obvious cases (server down, disk full)

### Problem: Too many alerts (alert fatigue)

**Solutions:**
1. Increase threshold durations (require condition to persist longer)
2. Use alert grouping (multiple related alerts become one)
3. Add hysteresis: alert fires at 90%, clears at 80% (not 89.9%)
4. Implement alert suppression during maintenance windows
5. Use AI to prioritize: AI marks alerts as "important" or "noise"
6. Set up escalation: only critical alerts send email, others are just logged

### Problem: Monitoring agent uses too much CPU on the monitored server

**Solutions:**
1. Increase collection interval (every 120s instead of 60s)
2. Reduce number of metrics collected (disable unused plugins)
3. Telegraf is very lightweight (<10MB RAM, <0.5% CPU) — if it's using more, check configuration
4. For custom Python agent, use `psutil.cpu_percent(interval=None)` (non-blocking)

---

## Quick Start Checklist

Here's the absolute minimum to get a working prototype:

- [ ] Install Odoo 14 or 19 Community Edition
- [ ] Create the `server_monitoring` module with `server.server` model
- [ ] Add basic views (form, tree, kanban)
- [ ] Create the `server.metric` model
- [ ] Build the `/api/v1/metrics` REST endpoint
- [ ] Install psutil on one test server and write a simple POST script
- [ ] Verify metrics are arriving in Odoo
- [ ] Add a basic Chart.js graph in a dashboard action
- [ ] You now have a working monitoring system

From here, incrementally add AI, more charts, alerts, and SaaS tracking.
