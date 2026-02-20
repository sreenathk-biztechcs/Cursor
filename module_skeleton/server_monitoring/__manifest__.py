# -*- coding: utf-8 -*-
{
    'name': 'Server Monitoring & AI Management',
    'version': '19.0.1.0.0',  # Change to 14.0.1.0.0 for Odoo 14
    'category': 'Tools',
    'summary': 'AI-powered server monitoring, management, and dashboard with Prometheus integration',
    'description': """
        Server Monitoring & AI Management
        ==================================
        - Monitor server health (CPU, RAM, Disk, Network) via Prometheus
        - Grafana-style dashboard inside Odoo with ECharts
        - AI-powered automatic analysis (OpenAI / Ollama)
        - Server allocation request and approval workflow
        - Alert management from Prometheus Alertmanager
        - AI chat for natural language queries about your infrastructure
        - Daily AI-generated fleet health reports
        - Idle server detection and cost optimization
    """,
    'author': 'Your Company',
    'website': 'https://yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'hr',        # For department linkage
        'web',       # For client actions / dashboard
    ],
    'data': [
        # Security
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        # Data
        'data/cron_jobs.xml',
        'data/mail_templates.xml',
        # Views
        'views/menu.xml',
        'views/server_views.xml',
        'views/server_allocation_views.xml',
        'views/alert_views.xml',
        'views/ai_analysis_views.xml',
        'views/monitoring_config_views.xml',
        'views/dashboard_action.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'server_monitoring/static/lib/echarts/echarts.min.js',
            'server_monitoring/static/src/css/dashboard.css',
            'server_monitoring/static/src/js/dashboard.js',
            'server_monitoring/static/src/js/charts.js',
            'server_monitoring/static/src/js/ai_chat_widget.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
