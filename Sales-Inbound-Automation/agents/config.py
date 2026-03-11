"""
Shared configuration for all Inbound Sales AI Agents.
Adjust model assignments and thresholds here — no need to touch individual agents.
"""

# ── Model assignments ─────────────────────────────────────────────────────────
# Haiku 4.5  → fast, cheap: classification, scoring, simple extraction
# Sonnet 4.6 → balanced: email drafting, MOMs, summaries
# Opus 4.6   → highest quality: proposals only

HAIKU   = "claude-haiku-4-5"
SONNET  = "claude-sonnet-4-6"
OPUS    = "claude-opus-4-6"

MODEL_MAP = {
    "JunkFilterAgent":           HAIKU,
    "EnrichmentStructurerAgent": HAIKU,
    "LeadScoringAgent":          HAIKU,
    "ReplyClassifierAgent":      HAIKU,
    "DailyAgendaAgent":          HAIKU,
    "AutoAckDrafterAgent":       SONNET,
    "FollowUpDrafterAgent":      SONNET,
    "ClientMOMAgent":            SONNET,
    "TicketGistAgent":           SONNET,
    "PresaleMOMAgent":           SONNET,
    "PresaleEmailDrafterAgent":  SONNET,
    "WBSGeneratorAgent":         SONNET,
    "RetrospectiveAgent":        SONNET,
    "NoShowFollowUpAgent":       SONNET,
    "MeetingPrepBriefAgent":     SONNET,
    "ProposalGeneratorAgent":    OPUS,
}

# ── Token limits ──────────────────────────────────────────────────────────────
MAX_TOKENS = {
    HAIKU:  2048,
    SONNET: 8192,
    OPUS:   16384,
}

# ── Lead score bands ──────────────────────────────────────────────────────────
SCORE_BANDS = {
    "hot":     (90, 100),
    "warm":    (70, 89),
    "neutral": (50, 69),
    "cold":    (0,  49),
}

# ── Follow-up schedule (days after auto-ack sent) ────────────────────────────
FOLLOWUP_SCHEDULE = {
    "hot":     [1, 3, 7],
    "warm":    [2, 5, 10],
    "neutral": [2, 5, 10],
    "cold":    [3, 7, 14],
}

# ── Audit log path ────────────────────────────────────────────────────────────
AUDIT_LOG_PATH = "logs/agent_audit.jsonl"

# ── Company identity (injected into email drafts) ────────────────────────────
COMPANY_NAME      = "Your Company Name"
COMPANY_TAGLINE   = "We help B2B companies streamline operations with custom Odoo implementations."
COMPANY_PORTFOLIO = "We've worked with 100+ companies across manufacturing, distribution, and services."
