/** @odoo-module **/
/**
 * AI Chat Widget for Server Monitoring Dashboard — Odoo 19 (OWL 2)
 *
 * Provides an in-dashboard chat interface for asking AI questions
 * about server infrastructure.
 */
import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class AIChatWidget extends Component {
    static template = "server_monitoring.AIChatWidget";

    setup() {
        this.rpc = useService("rpc");
        this.state = useState({
            messages: [],
            inputText: "",
            loading: false,
            sessionId: this._generateSessionId(),
        });
        this.messagesEnd = useRef("messagesEnd");

        onMounted(() => {
            this._addWelcomeMessage();
        });
    }

    _generateSessionId() {
        return "chat-" + Date.now() + "-" + Math.random().toString(36).substr(2, 9);
    }

    _addWelcomeMessage() {
        this.state.messages.push({
            role: "assistant",
            content:
                "Hello! I'm your AI infrastructure assistant. Ask me anything about your servers. For example:\n" +
                '- "Which servers are idle?"\n' +
                '- "What needs immediate attention?"\n' +
                '- "Compare production vs staging server usage"',
        });
    }

    async onSend() {
        const message = this.state.inputText.trim();
        if (!message || this.state.loading) return;

        this.state.messages.push({ role: "user", content: message });
        this.state.inputText = "";
        this.state.loading = true;
        this._scrollToBottom();

        try {
            const result = await this.rpc("/api/monitoring/ai_chat", {
                message: message,
                session_id: this.state.sessionId,
            });
            this.state.messages.push({
                role: "assistant",
                content: result.response || result.error || "No response received.",
            });
        } catch (err) {
            this.state.messages.push({
                role: "assistant",
                content: "Sorry, I encountered an error. Please try again.",
            });
        }

        this.state.loading = false;
        this._scrollToBottom();
    }

    onKeyPress(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.onSend();
        }
    }

    _scrollToBottom() {
        const el = this.messagesEnd.el;
        if (el) {
            setTimeout(() => el.scrollIntoView({ behavior: "smooth" }), 100);
        }
    }
}
