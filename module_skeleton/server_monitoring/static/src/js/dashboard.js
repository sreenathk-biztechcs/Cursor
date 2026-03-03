/** @odoo-module **/
/**
 * Server Monitoring Dashboard — Odoo 19 (OWL 2)
 *
 * For Odoo 14, replace this with a Widget.extend() implementation.
 * See docs/03_ODOO_MODULE_DESIGN.md for the Odoo 14 version pattern.
 */
import { Component, useState, onWillStart, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class ServerMonitoringDashboard extends Component {
    static template = "server_monitoring.Dashboard";

    setup() {
        this.rpc = useService("rpc");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            summary: {},
            servers: [],
            alerts: [],
            error: null,
        });
        this.chartRefs = {
            cpu: useRef("cpuChart"),
            ram: useRef("ramChart"),
            topCpu: useRef("topCpuChart"),
        };
        this.refreshInterval = null;

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            this.renderCharts();
            this.refreshInterval = setInterval(() => this.loadData(), 30000);
        });
    }

    async loadData() {
        try {
            const data = await this.rpc("/api/monitoring/dashboard", {});
            Object.assign(this.state, {
                summary: data.summary,
                servers: data.servers,
                alerts: data.alerts,
                loading: false,
                error: null,
            });
            this.renderCharts();
        } catch (err) {
            this.state.error = "Failed to load dashboard data.";
            this.state.loading = false;
        }
    }

    renderCharts() {
        // ECharts rendering logic goes here
        // See docs/05_DASHBOARD_AND_API.md for chart implementation details
    }

    onServerClick(serverId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "server.monitoring.server",
            res_id: serverId,
            views: [[false, "form"]],
        });
    }

    async onRefresh() {
        this.state.loading = true;
        await this.loadData();
    }

    willUnmount() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
}

registry.category("actions").add("server_monitoring_dashboard", ServerMonitoringDashboard);
