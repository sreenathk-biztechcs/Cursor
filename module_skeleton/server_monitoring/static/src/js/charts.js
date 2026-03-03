/** @odoo-module **/
/**
 * ECharts wrapper utilities for server monitoring dashboard.
 * Provides helper functions for creating common chart types.
 */

export function createCPULineChart(container, seriesData, timestamps) {
    if (!window.echarts || !container) return null;

    const chart = echarts.init(container);
    const option = {
        title: { text: "CPU Usage (All Servers)", left: "center", textStyle: { fontSize: 14 } },
        tooltip: { trigger: "axis" },
        legend: { bottom: 0, type: "scroll" },
        grid: { left: "3%", right: "4%", bottom: "15%", containLabel: true },
        xAxis: { type: "time", boundaryGap: false },
        yAxis: { type: "value", name: "%", min: 0, max: 100 },
        series: seriesData.map((s) => ({
            name: s.name,
            type: "line",
            smooth: true,
            data: s.data,
            showSymbol: false,
        })),
    };
    chart.setOption(option);
    return chart;
}

export function createGaugeChart(container, value, title) {
    if (!window.echarts || !container) return null;

    const chart = echarts.init(container);
    const option = {
        series: [
            {
                type: "gauge",
                progress: { show: true, width: 18 },
                axisLine: { lineStyle: { width: 18 } },
                axisTick: { show: false },
                splitLine: { length: 15, lineStyle: { width: 2 } },
                axisLabel: { distance: 25, fontSize: 12 },
                anchor: { show: true, size: 25, itemStyle: { borderWidth: 10 } },
                title: { show: true, fontSize: 14 },
                detail: { valueAnimation: true, fontSize: 24, formatter: "{value}%" },
                data: [{ value: value, name: title }],
            },
        ],
    };
    chart.setOption(option);
    return chart;
}

export function createBarChart(container, data, title) {
    if (!window.echarts || !container) return null;

    const chart = echarts.init(container);
    const option = {
        title: { text: title, left: "center", textStyle: { fontSize: 14 } },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
        grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
        xAxis: { type: "value", max: 100 },
        yAxis: {
            type: "category",
            data: data.map((d) => d.name),
            inverse: true,
        },
        series: [
            {
                type: "bar",
                data: data.map((d) => ({
                    value: d.value,
                    itemStyle: {
                        color: d.value > 90 ? "#e74c3c" : d.value > 70 ? "#f39c12" : "#2ecc71",
                    },
                })),
            },
        ],
    };
    chart.setOption(option);
    return chart;
}

export function createHeatmapChart(container, servers) {
    if (!window.echarts || !container) return null;

    const chart = echarts.init(container);
    const cols = Math.ceil(Math.sqrt(servers.length));
    const data = servers.map((s, i) => [i % cols, Math.floor(i / cols), s.cpu]);

    const option = {
        title: { text: "Server Health Map", left: "center", textStyle: { fontSize: 14 } },
        tooltip: {
            formatter: (params) => {
                const server = servers[params.data[1] * cols + params.data[0]];
                return server
                    ? `${server.name}<br/>CPU: ${server.cpu}%<br/>RAM: ${server.ram}%`
                    : "";
            },
        },
        visualMap: {
            min: 0,
            max: 100,
            inRange: { color: ["#2ecc71", "#f1c40f", "#e74c3c"] },
        },
        series: [{ type: "heatmap", data: data, label: { show: false } }],
    };
    chart.setOption(option);
    return chart;
}
