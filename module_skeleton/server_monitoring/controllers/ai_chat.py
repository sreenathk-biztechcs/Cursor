# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json
import uuid


class AIChatController(http.Controller):

    @http.route('/api/monitoring/ai_chat', type='json', auth='user')
    def ai_chat(self, message, session_id=None, **kwargs):
        """Handle AI chat messages."""
        if not session_id:
            session_id = str(uuid.uuid4())

        config = request.env['server.monitoring.config'].sudo().get_config()
        if not config or not config.ai_api_key:
            return {'error': 'AI not configured', 'response': 'AI is not configured. Please set up the API key in Settings.'}

        from ..services.ai_service import AIService
        ai = AIService(
            api_key=config.ai_api_key,
            model=config.ai_model or 'gpt-4o-mini',
            base_url=config.ai_base_url or None,
        )

        servers = request.env['server.monitoring.server'].sudo().search([
            ('state', '=', 'active'),
        ])
        context_data = [{
            'name': s.name,
            'ip': s.ip_address,
            'cpu': s.cpu_usage_percent,
            'ram': s.ram_usage_percent,
            'disk': s.disk_usage_percent,
            'health': s.health_status,
            'is_idle': s.is_idle,
            'uptime': s.uptime_display,
            'department': s.department_id.name or '',
            'owner': s.owner_id.name or '',
            'ai_summary': s.ai_summary or '',
        } for s in servers]

        ChatMsg = request.env['server.monitoring.ai.chat'].sudo()

        history_records = ChatMsg.search([
            ('session_id', '=', session_id),
            ('user_id', '=', request.env.user.id),
        ], order='timestamp asc', limit=20)

        chat_history = [{'role': r.role, 'content': r.message} for r in history_records]

        ChatMsg.create({
            'user_id': request.env.user.id,
            'session_id': session_id,
            'role': 'user',
            'message': message,
        })

        try:
            ai_response = ai.chat(message, context_data, chat_history)
        except Exception as e:
            ai_response = f"I encountered an error: {str(e)}. Please try again."

        ChatMsg.create({
            'user_id': request.env.user.id,
            'session_id': session_id,
            'role': 'assistant',
            'message': ai_response,
            'model_used': config.ai_model or 'gpt-4o-mini',
        })

        return {
            'response': ai_response,
            'session_id': session_id,
        }
