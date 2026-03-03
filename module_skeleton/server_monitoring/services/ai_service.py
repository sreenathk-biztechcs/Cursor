# -*- coding: utf-8 -*-
"""
AI Service for server analysis, chat, and recommendations.
Supports OpenAI API and Ollama (OpenAI-compatible local LLMs).
"""
import json
import logging

_logger = logging.getLogger(__name__)

try:
    import openai
except ImportError:
    openai = None
    _logger.warning("openai package not installed. Install with: pip install openai")


class AIService:

    def __init__(self, api_key, model='gpt-4o-mini', base_url=None):
        if openai is None:
            raise ImportError("openai package is required. Install with: pip install openai")
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = model

    def _call(self, system_prompt, user_content, json_mode=True, temperature=0.1):
        """Make an AI API call with error handling."""
        kwargs = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_content},
            ],
            'temperature': temperature,
        }
        if json_mode:
            kwargs['response_format'] = {'type': 'json_object'}

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content

        if json_mode:
            return json.loads(content)
        return content

    def analyze_server_health(self, server_data):
        """Analyze a single server's health and return structured assessment."""
        system_prompt = """You are an expert server infrastructure analyst.
Analyze the provided server metrics and return a JSON response with:
{
    "health_status": "healthy" | "warning" | "critical",
    "risk_score": <number 0-100>,
    "summary": "<one-line summary>",
    "issues": ["<list of detected issues>"],
    "recommendations": ["<list of actionable recommendations>"],
    "prediction": "<what will happen if no action is taken>",
    "idle_assessment": {
        "is_idle": true | false,
        "confidence": <number 0-100>
    }
}
Be precise, data-driven, and actionable. Use actual numbers from the data."""

        return self._call(system_prompt, json.dumps(server_data, indent=2))

    def analyze_fleet(self, all_servers_data):
        """Analyze entire server fleet for optimization opportunities."""
        system_prompt = """You are an expert infrastructure optimization analyst.
Analyze the entire server fleet and return JSON:
{
    "overall_health": "healthy" | "degraded" | "critical",
    "servers": [
        {
            "id": <server_id>,
            "summary": "<one-line status>",
            "risk_score": <0-100>,
            "recommendations": ["<actions>"]
        }
    ],
    "idle_servers": [{"id": <id>, "name": "<name>", "days_idle_estimate": <N>}],
    "overloaded_servers": [{"id": <id>, "name": "<name>", "issue": "<description>"}],
    "anomalies": [{"server": "<name>", "anomaly": "<description>", "severity": "low|medium|high"}],
    "top_recommendations": ["<ranked list of most important actions>"],
    "daily_summary": "<a brief paragraph summarizing fleet health for email>"
}"""

        return self._call(system_prompt, json.dumps(all_servers_data, indent=2))

    def explain_alert(self, alert_data, server_metrics):
        """Explain an alert with root cause analysis and recommended actions."""
        system_prompt = """You are a server incident analyst.
Analyze this alert and the associated server metrics.
Return JSON:
{
    "root_cause": "<probable root cause>",
    "severity_assessment": "<your assessment of actual severity>",
    "immediate_actions": ["<steps to take right now>"],
    "long_term_fix": "<recommended permanent fix>",
    "explanation": "<detailed human-readable explanation>"
}"""

        context = {'alert': alert_data, 'server_metrics': server_metrics}
        return self._call(system_prompt, json.dumps(context, indent=2))

    def recommend_server(self, allocation_context):
        """Recommend a server for an allocation request."""
        system_prompt = """You are a server allocation advisor.
Based on the allocation request requirements and available idle servers,
recommend the best match. Return a human-readable recommendation explaining
your choice, why it's a good fit, and any alternatives."""

        return self._call(
            system_prompt,
            json.dumps(allocation_context, indent=2),
            json_mode=False,
            temperature=0.3,
        )

    def chat(self, user_message, context_data, chat_history=None):
        """Conversational AI for natural language queries about infrastructure."""
        system_prompt = f"""You are an AI assistant for server infrastructure management.
You have access to real-time server monitoring data.

CURRENT SERVER DATA:
{json.dumps(context_data, indent=2)}

Answer the user's questions based on this data. Be specific with server names,
IP addresses, and metric values. If you recommend actions, be precise about
which servers and what to do. Format responses clearly."""

        messages = [{'role': 'system', 'content': system_prompt}]
        if chat_history:
            messages.extend(chat_history)
        messages.append({'role': 'user', 'content': user_message})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
        )
        return response.choices[0].message.content

    def generate_daily_summary(self, fleet_data):
        """Generate a human-readable daily summary email."""
        system_prompt = """You are an infrastructure reporting assistant.
Generate a clear, concise daily server fleet health report suitable for email.
Include sections for: Overall Status, Critical Issues, Warnings, Idle Servers,
and Top Recommendations. Use bullet points and be actionable."""

        return self._call(
            system_prompt,
            json.dumps(fleet_data, indent=2),
            json_mode=False,
            temperature=0.3,
        )
