# 09 — Odoo 14 vs Odoo 19 — Implementation Differences

## What Changes Between Versions and How to Handle Both

---

## Summary of Differences

| Aspect | Odoo 14 Community | Odoo 19 Community |
|---|---|---|
| **Python version** | 3.8+ | 3.10+ |
| **JS Framework** | Legacy Widget system | OWL 2 (Component-based) |
| **JS Templates** | QWeb (XML in JS) | OWL XML templates |
| **Asset bundling** | `__manifest__.py` assets dict or `assets.xml` | `__manifest__.py` assets dict |
| **Backend Models** | Nearly identical | Same with minor enhancements |
| **ORM** | Same core API | Minor improvements |
| **Web Controllers** | `http.Controller` | Same |
| **Cron Jobs** | `ir.cron` | Same |
| **Views (Form/Tree/Kanban)** | XML | Same XML (minor attribute changes) |
| **Security** | Same | Same |
| **Testing** | `TransactionCase`, `HttpCase` | Same with additions |
| **API/JSON-RPC** | Same | Same |

**The backend (Python) code is 95% identical.** The main work for dual-version support is in the **JavaScript frontend** (dashboard, AI chat).

---

## Backend Differences (Minor)

### Module Manifest

**Odoo 14:**
```python
{
    'name': 'Server Monitoring',
    'version': '14.0.1.0.0',
    'category': 'Tools',
    'depends': ['base', 'mail', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/server_views.xml',
        'views/menu.xml',
        'data/cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'server_monitoring/static/src/js/dashboard.js',
            'server_monitoring/static/src/css/dashboard.css',
        ],
        'web.assets_qweb': [
            'server_monitoring/static/src/xml/dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
}
```

**Odoo 19:**
```python
{
    'name': 'Server Monitoring',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'depends': ['base', 'mail', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/server_views.xml',
        'views/menu.xml',
        'data/cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'server_monitoring/static/src/js/**/*.js',
            'server_monitoring/static/src/js/**/*.xml',
            'server_monitoring/static/src/css/**/*.css',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
```

Key difference: Odoo 19 uses glob patterns for assets and includes XML templates in `web.assets_backend` (OWL templates are part of the JS bundle).

### Model Definitions

**Identical in both versions.** Example:

```python
from odoo import models, fields, api

class ServerServer(models.Model):
    _name = 'server.server'
    _description = 'Server'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, tracking=True)
    ip_address = fields.Char(required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ], default='draft', tracking=True)
    cpu_usage_current = fields.Float(compute='_compute_current_metrics')

    # Works exactly the same in v14 and v19
```

### Web Controllers

**Identical in both versions:**

```python
from odoo import http
from odoo.http import request

class MetricsController(http.Controller):
    
    @http.route('/api/v1/metrics', type='json', auth='none', methods=['POST'], csrf=False)
    def receive_metrics(self, **kwargs):
        # Same code works in v14 and v19
        data = request.jsonrequest
        api_key = request.httprequest.headers.get('X-API-Key')
        # ... process metrics ...
        return {'status': 'ok'}
```

### Cron Jobs

**Identical in both versions:**

```xml
<record id="cron_collect_metrics" model="ir.cron">
    <field name="name">Server Monitoring: Collect Metrics</field>
    <field name="model_id" ref="model_server_server"/>
    <field name="state">code</field>
    <field name="code">model.cron_collect_metrics()</field>
    <field name="interval_number">1</field>
    <field name="interval_type">minutes</field>
    <field name="active">True</field>
</record>
```

---

## Frontend Differences (Major)

This is where the versions diverge significantly. You need to write the dashboard and AI chat differently for each version.

### Odoo 19 — OWL Components

OWL is a modern, reactive component framework (similar to Vue.js/React). Components are defined as JavaScript classes with XML templates.

**Dashboard Component (Conceptual Structure):**

```javascript
/** @odoo-module **/
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class ServerDashboard extends Component {
    static template = "server_monitoring.Dashboard";
    
    setup() {
        this.rpc = useService("rpc");
        this.state = useState({
            servers: [],
            alerts: [],
            loading: true,
        });
        
        onMounted(() => {
            this.loadData();
            this.refreshInterval = setInterval(() => this.loadData(), 30000);
        });
        
        onWillUnmount(() => {
            clearInterval(this.refreshInterval);
        });
    }
    
    async loadData() {
        const data = await this.rpc("/api/v1/dashboard/overview");
        Object.assign(this.state, data, { loading: false });
    }
}

registry.category("actions").add("server_dashboard", ServerDashboard);
```

**OWL Template:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="server_monitoring.Dashboard">
        <div class="server-dashboard">
            <div class="dashboard-header">
                <h1>Server Monitoring</h1>
            </div>
            <div class="server-grid">
                <t t-foreach="state.servers" t-as="server" t-key="server.id">
                    <div class="server-card" t-att-class="server.monitoring_state">
                        <span t-esc="server.name"/>
                        <span t-esc="server.cpu_current + '%'"/>
                    </div>
                </t>
            </div>
            <div class="charts-container">
                <!-- Chart.js canvas elements -->
            </div>
        </div>
    </t>
</templates>
```

### Odoo 14 — Legacy Widgets

Odoo 14 uses the older Widget system based on Backbone.js patterns.

**Dashboard Widget (Conceptual Structure):**

```javascript
odoo.define('server_monitoring.Dashboard', function (require) {
    "use strict";

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var ajax = require('web.ajax');
    var QWeb = core.qweb;

    var ServerDashboard = AbstractAction.extend({
        template: 'ServerDashboard',
        
        init: function (parent, action) {
            this._super.apply(this, arguments);
            this.data = {};
        },
        
        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._loadData();
                self._startAutoRefresh();
            });
        },
        
        _loadData: function () {
            var self = this;
            return ajax.jsonRpc('/api/v1/dashboard/overview', 'call', {}).then(function (data) {
                self.data = data;
                self._renderDashboard();
            });
        },
        
        _renderDashboard: function () {
            this.$('.dashboard-content').html(
                QWeb.render('ServerDashboardContent', {data: this.data})
            );
            this._renderCharts();
        },
        
        _renderCharts: function () {
            // Initialize Chart.js charts
        },
        
        _startAutoRefresh: function () {
            this.refreshInterval = setInterval(this._loadData.bind(this), 30000);
        },
        
        destroy: function () {
            clearInterval(this.refreshInterval);
            this._super.apply(this, arguments);
        },
    });

    core.action_registry.add('server_dashboard', ServerDashboard);
    return ServerDashboard;
});
```

**QWeb Template (in separate XML file):**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates id="template" xml:space="preserve">
    <t t-name="ServerDashboard">
        <div class="server-dashboard">
            <div class="dashboard-header">
                <h1>Server Monitoring</h1>
            </div>
            <div class="dashboard-content">
                <!-- Dynamically rendered -->
            </div>
        </div>
    </t>
    
    <t t-name="ServerDashboardContent">
        <div class="server-grid">
            <t t-foreach="data.servers" t-as="server">
                <div class="server-card" t-attf-class="#{server.monitoring_state}">
                    <span t-esc="server.name"/>
                    <span><t t-esc="server.cpu_current"/>%</span>
                </div>
            </t>
        </div>
    </t>
</templates>
```

---

## Strategy for Supporting Both Versions

### Option 1: Two Separate Modules (Recommended)

```
server_monitoring_base/        ← Shared: models, cron, controllers, security
    models/
    controllers/
    security/
    data/

server_monitoring_ui_14/       ← Odoo 14 specific: JS widgets, QWeb
    static/src/js/
    static/src/xml/
    static/src/css/

server_monitoring_ui_19/       ← Odoo 19 specific: OWL components
    static/src/js/
    static/src/xml/
    static/src/css/
```

- `server_monitoring_base` contains all Python code (identical for both)
- Install `server_monitoring_ui_14` on Odoo 14 instances
- Install `server_monitoring_ui_19` on Odoo 19 instances

### Option 2: Single Module with Version Detection

```python
# In __manifest__.py, use version detection
import odoo
odoo_version = int(odoo.release.version.split('.')[0])

# In JavaScript, check version
if (typeof owl !== 'undefined') {
    // Odoo 19+ (OWL available)
} else {
    // Odoo 14 (Legacy widgets)
}
```

This is messier but keeps everything in one module.

### Recommendation

**Use Option 1** (separate UI modules). It's cleaner, easier to maintain, and follows Odoo community best practices.

---

## Migration Path: Odoo 14 → 19

If you start with Odoo 14 and later upgrade to 19:

### What Migrates Automatically
- All model data (servers, metrics, alerts, etc.)
- Security rules
- Cron jobs
- Menu items and actions

### What Needs Manual Work
- JavaScript frontend (rewrite widgets as OWL components)
- QWeb templates (adapt to OWL template syntax)
- Asset declarations in manifest

### Migration Effort
- Backend: ~2 hours (minor syntax updates)
- Frontend: ~2-3 days (rewrite dashboard and AI chat as OWL components)
- Testing: ~1-2 days

---

## Feature Parity Table

| Feature | Odoo 14 | Odoo 19 | Notes |
|---|---|---|---|
| Server CRUD | Full | Full | Identical |
| Approval workflow | Full | Full | Identical |
| Metric collection | Full | Full | Identical backend |
| REST API | Full | Full | Identical |
| Dashboard | Full | Full | Different JS, same functionality |
| Chart.js charts | Full | Full | Same library, different integration |
| AI analysis | Full | Full | Identical backend |
| AI Chat | Full | Full | Different JS frontend |
| SaaS tracking | Full | Full | Identical |
| Alerts | Full | Full | Identical |
| Reports | Full | Full | Identical |
| Real-time refresh | Polling | Polling + bus | v19 has better long-polling support |
