# 05 — Monitoring Agent Setup Guide

## How to Set Up Data Collection on Your Servers

This document covers three approaches to collecting metrics from your servers and sending them to Odoo.

---

## Approach Comparison

| Approach | Setup Effort | Reliability | Flexibility | Dependencies |
|---|---|---|---|---|
| **A: Telegraf** | Medium | High | High (300+ plugins) | Telegraf binary |
| **B: Custom Python Agent** | Low | Medium | Full control | Python, psutil |
| **C: SSH Pull from Odoo** | Low | Medium | Limited | paramiko on Odoo server |

---

## Approach A: Telegraf (Recommended for Production)

### What is Telegraf?

Telegraf is a lightweight agent by InfluxData that collects system metrics and sends them anywhere. Think of it as a data pipeline running on each server.

### How It Works with Odoo

```
[Your Server]                          [Odoo Server]
┌──────────────────┐                  ┌──────────────────┐
│                  │   HTTP POST      │                  │
│  Telegraf        │ ───────────────> │  /api/v1/metrics │
│                  │   (JSON data     │                  │
│  Collects:       │    every 60s)    │  Receives data,  │
│  - CPU usage     │                  │  stores in       │
│  - RAM usage     │                  │  server.metric   │
│  - Disk space    │                  │  model           │
│  - Network I/O   │                  │                  │
│  - Processes     │                  │                  │
│  - etc.          │                  │                  │
└──────────────────┘                  └──────────────────┘
```

### Installation

**Ubuntu/Debian:**
```bash
# Add InfluxData repository
wget -q https://repos.influxdata.com/influxdata-archive_compat.key
echo '393e8779c89ac8d958f81f942f9ad7fb82a25e133faddaf92e15b16e6ac9ce4c influxdata-archive_compat.key' | sha256sum -c && cat influxdata-archive_compat.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg > /dev/null
echo 'deb [signed-by=/etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg] https://repos.influxdata.com/debian stable main' | sudo tee /etc/apt/sources.list.d/influxdata.list

sudo apt-get update && sudo apt-get install telegraf
```

**CentOS/RHEL:**
```bash
cat <<EOF | sudo tee /etc/yum.repos.d/influxdata.repo
[influxdata]
name = InfluxData Repository
baseurl = https://repos.influxdata.com/rhel/\$releasever/\$basearch/stable
enabled = 1
gpgcheck = 1
gpgkey = https://repos.influxdata.com/influxdata-archive_compat.key
EOF

sudo yum install telegraf
```

### Configuration

Edit `/etc/telegraf/telegraf.conf`:

```toml
# Global settings
[agent]
  interval = "60s"          # Collect metrics every 60 seconds
  round_interval = true
  flush_interval = "60s"    # Send to Odoo every 60 seconds
  hostname = ""             # Auto-detect hostname

# INPUT PLUGINS — What to collect

[[inputs.cpu]]
  percpu = true             # Per-core CPU stats
  totalcpu = true           # Total CPU stats
  collect_cpu_time = false

[[inputs.mem]]
  # RAM usage — no extra config needed

[[inputs.disk]]
  ignore_fs = ["tmpfs", "devtmpfs", "devfs", "iso9660", "overlay", "aufs", "squashfs"]

[[inputs.diskio]]
  # Disk I/O stats

[[inputs.net]]
  # Network I/O stats
  interfaces = ["eth*", "ens*", "enp*"]

[[inputs.system]]
  # System uptime, load average

[[inputs.processes]]
  # Process count by state

[[inputs.swap]]
  # Swap usage

# OUTPUT PLUGIN — Where to send data

[[outputs.http]]
  url = "https://your-odoo-server.com/api/v1/metrics"
  timeout = "10s"
  method = "POST"
  data_format = "json"
  
  [outputs.http.headers]
    Content-Type = "application/json"
    X-API-Key = "YOUR_SERVER_API_KEY_HERE"
    X-Server-ID = "YOUR_SERVER_RECORD_ID"
```

### Start Telegraf

```bash
sudo systemctl enable telegraf
sudo systemctl start telegraf
sudo systemctl status telegraf

# Check logs
sudo journalctl -u telegraf -f
```

### What Data You Get

Every 60 seconds, Telegraf sends JSON like:

```json
{
  "metrics": [
    {
      "name": "cpu",
      "tags": {"cpu": "cpu-total", "host": "prod-web-01"},
      "fields": {"usage_idle": 33.5, "usage_system": 12.3, "usage_user": 54.2},
      "timestamp": 1740052800
    },
    {
      "name": "mem",
      "tags": {"host": "prod-web-01"},
      "fields": {"total": 17179869184, "available": 5368709120, "used_percent": 68.75},
      "timestamp": 1740052800
    },
    {
      "name": "disk",
      "tags": {"host": "prod-web-01", "path": "/"},
      "fields": {"total": 107374182400, "used": 48318382080, "used_percent": 45.0},
      "timestamp": 1740052800
    }
  ]
}
```

---

## Approach B: Custom Python Agent

### What It Is

A simple Python script that uses the `psutil` library to collect system metrics and sends them to your Odoo API.

### How It Works

```
[Your Server]
┌────────────────────────────────────────────────┐
│                                                │
│  python3 monitor_agent.py                      │
│                                                │
│  while True:                                   │
│    metrics = collect_all_metrics()  # psutil   │
│    send_to_odoo(metrics)            # requests │
│    sleep(60)                                   │
│                                                │
└────────────────────────────────────────────────┘
```

### Prerequisites

```bash
pip3 install psutil requests
```

### What psutil Collects

| Function | Data |
|---|---|
| `psutil.cpu_percent()` | CPU usage percentage |
| `psutil.virtual_memory()` | RAM total, available, used, percent |
| `psutil.disk_usage('/')` | Disk total, used, free, percent |
| `psutil.net_io_counters()` | Bytes sent/received, packets |
| `psutil.boot_time()` | System boot timestamp → uptime |
| `psutil.getloadavg()` | Load average (1, 5, 15 min) |
| `psutil.pids()` | Process count |
| `psutil.swap_memory()` | Swap usage |
| `psutil.disk_io_counters()` | Disk read/write bytes |
| `psutil.sensors_temperatures()` | CPU temperature (Linux) |

### Running as a Service

Create a systemd service so it runs automatically:

```ini
# /etc/systemd/system/odoo-monitor.service
[Unit]
Description=Odoo Server Monitor Agent
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /opt/odoo-monitor/monitor_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable odoo-monitor
sudo systemctl start odoo-monitor
```

---

## Approach C: SSH Pull from Odoo

### What It Is

Instead of installing agents on each server, Odoo connects to servers via SSH and runs commands to collect metrics.

### How It Works

```
[Odoo Server]                    [Target Servers]
┌──────────────────┐            ┌──────────────┐
│                  │   SSH      │              │
│  Cron job        │──────────> │  SRV-01      │
│  (every 60s)     │  commands  │              │
│                  │            └──────────────┘
│  For each server:│            ┌──────────────┐
│  1. SSH connect  │──────────> │  SRV-02      │
│  2. Run commands │  commands  │              │
│  3. Parse output │            └──────────────┘
│  4. Store metrics│            ┌──────────────┐
│                  │──────────> │  SRV-03      │
└──────────────────┘  commands  │              │
                                └──────────────┘
```

### Commands Used

| Metric | Command | Parsing |
|---|---|---|
| CPU | `top -bn1 \| head -3` | Parse "Cpu(s)" line |
| RAM | `free -m` | Parse "Mem:" line |
| Disk | `df -h /` | Parse usage percentage |
| Load | `cat /proc/loadavg` | Split by space |
| Uptime | `cat /proc/uptime` | First value in seconds |
| Processes | `ps aux \| wc -l` | Integer count |
| Network | `cat /proc/net/dev` | Parse interface stats |

### Pros and Cons

| Pros | Cons |
|---|---|
| No agent installation needed | Slower (SSH connection overhead) |
| Centralized management | SSH keys must be managed |
| Works with any Linux server | Doesn't scale well past 20-30 servers |
| No dependencies on monitored servers | Connection failures = missed data |

### When to Use

- Small number of servers (< 20)
- Servers where you can't install software
- Quick proof-of-concept before deploying Telegraf

---

## Odoo API Endpoint Design

Regardless of which agent approach you use, Odoo needs an API endpoint to receive metrics.

### Endpoint: `POST /api/v1/metrics`

```
URL:     POST https://your-odoo.com/api/v1/metrics
Headers: Content-Type: application/json
         X-API-Key: <server_api_key>
Auth:    API key validated against server.server.api_key

Request Body:
{
  "server_identifier": "prod-web-01",  // hostname or IP
  "timestamp": "2026-02-20T10:30:00Z",
  "metrics": {
    "cpu_percent": 67.5,
    "ram_percent": 72.3,
    "ram_used_mb": 11876,
    "ram_total_mb": 16384,
    "disk_percent": 45.0,
    "disk_used_gb": 45.2,
    "disk_total_gb": 100.0,
    "network_in_mbps": 120.5,
    "network_out_mbps": 85.3,
    "load_1m": 5.2,
    "load_5m": 4.8,
    "load_15m": 4.1,
    "process_count": 312,
    "swap_percent": 5.2,
    "uptime_seconds": 3888000
  }
}

Response (200 OK):
{
  "status": "ok",
  "server_id": 42,
  "metrics_stored": 15,
  "alerts_triggered": 0
}

Response (401 Unauthorized):
{
  "status": "error",
  "message": "Invalid API key"
}
```

### Endpoint: `GET /api/v1/metrics/<server_id>`

For the dashboard to fetch metrics:

```
URL:     GET https://your-odoo.com/api/v1/metrics/42?type=cpu&period=24h
Headers: Cookie: session_id=<odoo_session>
Auth:    Odoo session (logged-in user)

Response:
{
  "server": {"id": 42, "name": "PROD-WEB-01"},
  "metric_type": "cpu",
  "period": "24h",
  "data": [
    {"timestamp": "2026-02-19T10:30:00Z", "value": 65.2},
    {"timestamp": "2026-02-19T10:31:00Z", "value": 67.8},
    ...
  ],
  "summary": {
    "avg": 67.5,
    "min": 12.3,
    "max": 94.1,
    "p95": 89.2
  }
}
```

---

## Network Architecture

### Firewall Rules Needed

| From | To | Port | Protocol | Purpose |
|---|---|---|---|---|
| Monitored servers | Odoo server | 8069 (or 443) | HTTPS | Telegraf/agent pushing metrics |
| Odoo server | Monitored servers | 22 | SSH | SSH-based monitoring (Approach C) |
| Odoo server | Monitored servers | 9100 | HTTP | Node Exporter scraping (optional) |
| Users | Odoo server | 8069 (or 443) | HTTPS | Accessing Odoo dashboard |
| Odoo server | api.openai.com | 443 | HTTPS | AI API calls |
| Odoo server | External SaaS APIs | 443 | HTTPS | Cursor/ChatGPT usage APIs |

### Security Considerations

1. **HTTPS everywhere**: Use TLS for metric transmission (especially over public networks)
2. **API key rotation**: Rotate server API keys periodically
3. **SSH key management**: Use dedicated monitoring SSH keys with read-only access
4. **Network segmentation**: Consider a monitoring VLAN
5. **Rate limiting**: Limit API calls to prevent abuse
6. **IP whitelisting**: Only accept metrics from known server IPs

---

## Scaling Guide

| Servers | Agent | Collection Interval | Storage | Estimated Data/Day |
|---|---|---|---|---|
| 1-10 | Any approach | 60s | PostgreSQL | ~150K records |
| 10-30 | Telegraf or Python | 60s | PostgreSQL | ~450K records |
| 30-50 | Telegraf | 60s | PostgreSQL + archival | ~750K records |
| 50-100 | Telegraf | 60s | PostgreSQL + InfluxDB | ~1.5M records |
| 100+ | Telegraf | 60-120s | InfluxDB primary | ~3M+ records |

### Data Retention Strategy

| Age | Resolution | Storage | Action |
|---|---|---|---|
| 0-7 days | Raw (every 60s) | server.metric | Keep as-is |
| 7-30 days | Raw (every 60s) | server.metric | Keep, prepare for aggregation |
| 30-90 days | Hourly summary | server.metric.summary | Aggregate, delete raw |
| 90-365 days | Daily summary | server.metric.summary | Keep summaries only |
| 365+ days | Monthly summary | server.metric.summary | Archive or delete |
