# Server Monitoring Stack — Setup & Configuration Guide

## Overview

This document explains how to set up the monitoring infrastructure that collects data from all your servers. This is the **foundation** — without this, there is no data for Odoo or AI to work with.

---

## Part 1: Node Exporter — Install on EVERY Server

### What Node Exporter Collects

Node Exporter automatically collects **hundreds of metrics** from each server:

| Category | Metrics | Examples |
|----------|---------|----------|
| **CPU** | Usage per core, idle time, iowait, steal | `node_cpu_seconds_total` |
| **Memory** | Total, used, free, cached, buffers, swap | `node_memory_MemTotal_bytes` |
| **Disk** | Read/write bytes, IOPS, free space per mount | `node_filesystem_avail_bytes` |
| **Network** | Bytes sent/received, packets, errors per interface | `node_network_receive_bytes_total` |
| **System** | Uptime, load average, running processes | `node_load1`, `node_load5`, `node_load15` |
| **File Descriptors** | Open file handles | `node_filefd_allocated` |
| **OS Info** | Hostname, OS version, kernel | `node_uname_info` |

### Installation on Each Server (Ubuntu/Debian)

```bash
# Download Node Exporter (check https://prometheus.io/download/ for latest version)
wget https://github.com/prometheus/node_exporter/releases/download/v1.8.2/node_exporter-1.8.2.linux-amd64.tar.gz

# Extract
tar xvfz node_exporter-1.8.2.linux-amd64.tar.gz

# Move binary to system path
sudo mv node_exporter-1.8.2.linux-amd64/node_exporter /usr/local/bin/

# Create a dedicated system user
sudo useradd --no-create-home --shell /bin/false node_exporter
```

### Create Systemd Service

Create file `/etc/systemd/system/node_exporter.service`:

```ini
[Unit]
Description=Node Exporter
Wants=network-online.target
After=network-online.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
Restart=always
RestartSec=5
ExecStart=/usr/local/bin/node_exporter \
    --collector.systemd \
    --collector.processes \
    --collector.tcpstat \
    --web.listen-address=:9100

[Install]
WantedBy=multi-user.target
```

### Start Node Exporter

```bash
sudo systemctl daemon-reload
sudo systemctl enable node_exporter
sudo systemctl start node_exporter

# Verify it is running
curl http://localhost:9100/metrics | head -20
```

### For RHEL/CentOS Servers

```bash
# Same binary works — just use yum/dnf for dependencies if needed
# The steps are identical to Ubuntu above
```

### For Windows Servers

Use **windows_exporter** instead:
- Download from: https://github.com/prometheus-community/windows_exporter/releases
- Install as a Windows service
- Exposes metrics on port `9182`

---

## Part 2: Prometheus — Central Metrics Server

### What Prometheus Does

1. **Scrapes** metrics from all Node Exporters every 15 seconds
2. **Stores** them in an efficient time-series database
3. **Provides** an HTTP API for querying data
4. **Evaluates** alerting rules and sends notifications

### Hardware Requirements for Prometheus Server

| Number of Servers | CPU | RAM | Disk (30-day retention) |
|---|---|---|---|
| 10-20 servers | 2 cores | 4 GB | 50 GB SSD |
| 20-50 servers | 4 cores | 8 GB | 100 GB SSD |
| 50-200 servers | 8 cores | 16 GB | 250 GB SSD |
| 200+ servers | 16 cores | 32 GB | 500 GB+ SSD |

### Installation

```bash
# Download Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.54.1/prometheus-2.54.1.linux-amd64.tar.gz

# Extract
tar xvfz prometheus-2.54.1.linux-amd64.tar.gz

# Move binaries
sudo mv prometheus-2.54.1.linux-amd64/prometheus /usr/local/bin/
sudo mv prometheus-2.54.1.linux-amd64/promtool /usr/local/bin/

# Create directories
sudo mkdir -p /etc/prometheus /var/lib/prometheus

# Create user
sudo useradd --no-create-home --shell /bin/false prometheus
sudo chown prometheus:prometheus /var/lib/prometheus
```

### Configuration File

Create `/etc/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s          # How often to collect metrics
  evaluation_interval: 15s      # How often to evaluate alerting rules
  scrape_timeout: 10s

# Alertmanager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - localhost:9093

# Load alerting rules
rule_files:
  - "alerts/*.yml"

# Define what to scrape
scrape_configs:

  # Monitor Prometheus itself
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # Monitor all your servers
  # OPTION A: Static list (simple, for small number of servers)
  - job_name: 'servers'
    static_configs:
      - targets:
          - '192.168.1.10:9100'    # Server 1 - Web App
          - '192.168.1.11:9100'    # Server 2 - Database
          - '192.168.1.12:9100'    # Server 3 - File Storage
          - '192.168.1.13:9100'    # Server 4 - Dev Environment
          - '192.168.1.14:9100'    # Server 5 - Staging
        labels:
          environment: 'production'

      - targets:
          - '192.168.2.10:9100'
          - '192.168.2.11:9100'
        labels:
          environment: 'development'

  # OPTION B: File-based discovery (better for dynamic environments)
  # Prometheus auto-reloads this file when it changes
  - job_name: 'servers-dynamic'
    file_sd_configs:
      - files:
          - '/etc/prometheus/targets/*.json'
        refresh_interval: 30s

  # OPTION C: If you use cloud providers
  # AWS EC2 auto-discovery
  # - job_name: 'aws-ec2'
  #   ec2_sd_configs:
  #     - region: us-east-1
  #       access_key: YOUR_ACCESS_KEY
  #       secret_key: YOUR_SECRET_KEY
  #       port: 9100
```

### File-Based Service Discovery (Recommended for Your Use Case)

This is powerful because **Odoo can update this file** when you add/remove servers!

Create `/etc/prometheus/targets/servers.json`:

```json
[
  {
    "targets": ["192.168.1.10:9100"],
    "labels": {
      "hostname": "web-server-01",
      "department": "engineering",
      "owner": "john",
      "purpose": "web-application",
      "odoo_server_id": "42"
    }
  },
  {
    "targets": ["192.168.1.11:9100"],
    "labels": {
      "hostname": "db-server-01",
      "department": "data-team",
      "owner": "jane",
      "purpose": "database",
      "odoo_server_id": "43"
    }
  }
]
```

### Create Systemd Service for Prometheus

Create `/etc/systemd/system/prometheus.service`:

```ini
[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
Restart=always
RestartSec=5
ExecStart=/usr/local/bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.path=/var/lib/prometheus/ \
    --storage.tsdb.retention.time=90d \
    --web.console.templates=/etc/prometheus/consoles \
    --web.console.libraries=/etc/prometheus/console_libraries \
    --web.enable-lifecycle \
    --web.enable-admin-api

[Install]
WantedBy=multi-user.target
```

### Start Prometheus

```bash
sudo systemctl daemon-reload
sudo systemctl enable prometheus
sudo systemctl start prometheus

# Access Prometheus UI at http://your-server:9090
# Try a query: up  (shows which servers are reachable)
```

---

## Part 3: Alertmanager — Automated Notifications

### Installation

```bash
wget https://github.com/prometheus/alertmanager/releases/download/v0.27.0/alertmanager-0.27.0.linux-amd64.tar.gz
tar xvfz alertmanager-0.27.0.linux-amd64.tar.gz
sudo mv alertmanager-0.27.0.linux-amd64/alertmanager /usr/local/bin/
sudo mkdir -p /etc/alertmanager
```

### Configuration (`/etc/alertmanager/alertmanager.yml`)

```yaml
global:
  resolve_timeout: 5m
  smtp_from: 'alerts@yourcompany.com'
  smtp_smarthost: 'smtp.yourcompany.com:587'
  smtp_auth_username: 'alerts@yourcompany.com'
  smtp_auth_password: 'your-smtp-password'

route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'

  routes:
    - match:
        severity: critical
      receiver: 'critical-alerts'
      repeat_interval: 1h

receivers:
  - name: 'default'
    email_configs:
      - to: 'your-email@company.com'

  - name: 'critical-alerts'
    email_configs:
      - to: 'your-email@company.com'
    # Optional: Webhook to notify Odoo directly
    webhook_configs:
      - url: 'http://your-odoo-server:8069/api/monitoring/alert'
        send_resolved: true
```

### Alert Rules

Create `/etc/prometheus/alerts/server_alerts.yml`:

```yaml
groups:
  - name: server_health
    rules:

      # Server is down
      - alert: ServerDown
        expr: up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Server {{ $labels.instance }} is DOWN"
          description: "Server has been unreachable for more than 2 minutes."

      # High CPU usage
      - alert: HighCPU
        expr: 100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High CPU on {{ $labels.instance }}"
          description: "CPU usage is {{ $value }}% for more than 10 minutes."

      # High memory usage
      - alert: HighMemory
        expr: (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100 > 90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High Memory on {{ $labels.instance }}"
          description: "Memory usage is {{ $value }}%."

      # Disk almost full
      - alert: DiskSpaceLow
        expr: (1 - node_filesystem_avail_bytes{fstype!="tmpfs"} / node_filesystem_size_bytes{fstype!="tmpfs"}) * 100 > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Disk space low on {{ $labels.instance }}"
          description: "Disk usage is {{ $value }}% on {{ $labels.mountpoint }}."

      # Server idle (for detecting unused servers)
      - alert: ServerIdle
        expr: avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[1h])) * 100 > 95
        for: 24h
        labels:
          severity: info
        annotations:
          summary: "Server {{ $labels.instance }} appears idle"
          description: "CPU has been >95% idle for 24 hours. Consider decommissioning."
```

---

## Part 4: Grafana (Optional Reference Dashboard)

### Why Optional?

We are building the dashboard **inside Odoo**, so Grafana is optional. However, it is useful:
- As a **reference** to compare with your Odoo dashboard
- For **quick ad-hoc queries** during debugging
- To **embed panels** in Odoo via iframe (quick win)

### Installation

```bash
# Ubuntu/Debian
sudo apt-get install -y apt-transport-https software-properties-common
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
echo "deb https://packages.grafana.com/oss/deb stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt-get update
sudo apt-get install grafana

sudo systemctl enable grafana-server
sudo systemctl start grafana-server

# Access at http://your-server:3000
# Default login: admin / admin
```

### Connect Grafana to Prometheus

1. Open Grafana → Configuration → Data Sources
2. Add Prometheus
3. URL: `http://localhost:9090`
4. Save & Test

### Useful Grafana Dashboards (Pre-built)

Import these community dashboards (Grafana → Dashboards → Import):

| Dashboard ID | Name | Purpose |
|---|---|---|
| **1860** | Node Exporter Full | Complete server metrics |
| **11074** | Node Exporter for Prometheus | Alternative layout |
| **13978** | Node Exporter Quickstart | Simplified view |

### Embedding Grafana in Odoo (Quick Integration)

You can embed Grafana panels directly in Odoo using iframes:

1. In Grafana, open any panel → Share → Embed
2. Copy the iframe URL
3. In your Odoo module, use an `ir.actions.client` action or a website page to embed it

This gives you an **instant dashboard inside Odoo** while you build the native one.

Grafana embed URL format:
```
http://grafana-server:3000/d-solo/DASHBOARD_ID/dashboard-name?orgId=1&panelId=2&from=now-6h&to=now
```

To allow anonymous embedding, set in `/etc/grafana/grafana.ini`:
```ini
[auth.anonymous]
enabled = true
org_name = Main Org.
org_role = Viewer

[security]
allow_embedding = true
```

---

## Part 5: Additional Exporters (For Specific Needs)

### Process Exporter — Monitor Specific Applications

If you need to know which **specific processes** are running on each server:

```bash
# Install process-exporter
wget https://github.com/ncabatoff/process-exporter/releases/download/v0.8.3/process-exporter-0.8.3.linux-amd64.tar.gz
```

Configuration (`/etc/process-exporter/config.yml`):
```yaml
process_names:
  - name: "{{.Matches}}"
    cmdline:
      - 'postgres'
      - 'nginx'
      - 'python.*odoo'
      - 'java'
      - 'node'
```

### Blackbox Exporter — Monitor HTTP/HTTPS/Ping

Test if services are actually **responding**:

```bash
wget https://github.com/prometheus/blackbox_exporter/releases/download/v0.25.0/blackbox_exporter-0.25.0.linux-amd64.tar.gz
```

### cAdvisor — Monitor Docker Containers

If your servers run Docker:

```bash
docker run -d \
  --name=cadvisor \
  --publish=8080:8080 \
  --volume=/:/rootfs:ro \
  --volume=/var/run:/var/run:ro \
  --volume=/sys:/sys:ro \
  --volume=/var/lib/docker/:/var/lib/docker:ro \
  gcr.io/cadvisor/cadvisor:latest
```

---

## Part 6: Key Prometheus Queries (PromQL) You Will Use

These are the queries your Odoo module will send to Prometheus:

### Server Status
```promql
# Is server up? (1 = up, 0 = down)
up{job="servers"}

# How long has server been running?
time() - node_boot_time_seconds
```

### CPU
```promql
# CPU usage percentage (per server)
100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Load average (1 min, 5 min, 15 min)
node_load1
node_load5
node_load15
```

### Memory
```promql
# Memory usage percentage
(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100

# Total RAM in GB
node_memory_MemTotal_bytes / 1024 / 1024 / 1024

# Available RAM in GB
node_memory_MemAvailable_bytes / 1024 / 1024 / 1024
```

### Disk
```promql
# Disk usage percentage per mount point
(1 - node_filesystem_avail_bytes{fstype!="tmpfs"} / node_filesystem_size_bytes{fstype!="tmpfs"}) * 100

# Disk read/write rate (bytes/sec)
rate(node_disk_read_bytes_total[5m])
rate(node_disk_written_bytes_total[5m])
```

### Network
```promql
# Network traffic in/out (bytes/sec)
rate(node_network_receive_bytes_total{device!="lo"}[5m])
rate(node_network_transmit_bytes_total{device!="lo"}[5m])
```

### Identifying Idle Servers
```promql
# Servers with less than 5% CPU usage over past 7 days
avg_over_time((100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100))[7d:1h]) < 5
```

---

## Part 7: Security Considerations

### Network Security

```
┌─────────────────────────────────┐
│       Monitoring Network         │
│  (Separate VLAN recommended)     │
│                                  │
│  Prometheus ◄──── Node Exporters │
│      │                           │
│      ▼                           │
│  Odoo Server ◄── reads via API   │
│                                  │
│  Firewall Rules:                 │
│  - Port 9100: Only from          │
│    Prometheus IP                  │
│  - Port 9090: Only from          │
│    Odoo + Grafana IPs            │
│  - Port 3000: Only from          │
│    internal network               │
└─────────────────────────────────┘
```

### TLS Encryption (Recommended for Production)

Enable HTTPS on Node Exporter:
```yaml
# /etc/node_exporter/web-config.yml
tls_server_config:
  cert_file: /etc/node_exporter/cert.pem
  key_file: /etc/node_exporter/key.pem
```

### Basic Authentication

```yaml
# /etc/node_exporter/web-config.yml
basic_auth_users:
  prometheus: $2y$12$HASHED_PASSWORD_HERE
```

---

## Summary Checklist

- [ ] Install Node Exporter on all servers you want to monitor
- [ ] Install Prometheus on a central monitoring server
- [ ] Configure `prometheus.yml` with all your server targets
- [ ] Set up file-based service discovery for dynamic server management
- [ ] Install Alertmanager and configure alert rules
- [ ] (Optional) Install Grafana for reference dashboards
- [ ] Verify all servers appear as "UP" in Prometheus targets page
- [ ] Test PromQL queries to ensure data flows correctly
- [ ] Configure firewall rules to secure the monitoring network
- [ ] (Optional) Enable TLS and authentication for production
