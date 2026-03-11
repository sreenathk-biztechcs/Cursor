# Inbound Sales Automation

**Odoo 19 CE + Custom App + Claude AI**

## Final Requirements Specification

10 Inbound Reps | Odoo 19 Community Edition | Claude AI
n8n for external automation only

> **Note:** Odoo 19 Community Edition for V1. All AI capabilities are built via our own Claude API integration in a custom Odoo app. No Enterprise features are used. Everything is either built custom or via third-party Community modules. Goal: build everything custom where possible.

Prepared for: Sales Head & Odoo Team
March 2026

---

## Contents

1. Architecture - Odoo App vs n8n
2. Odoo Community Edition - What We Build (Enterprise Removed)
3. Inbound Flow (23 Steps)
4. Step-by-Step Detail
5. Follow-up Email System
6. Junk / Marketing Lead Filtering
7. Meeting Recording & Client MOM
8. Presale Ticket Lifecycle
9. WBS & Proposal Generation
10. AI-Drafted Emails for Presale Tickets
11. Daily Presale Agenda - 10:30 AM
12. Lead Closure Retrospective
13. Centralized Email Management
14. Who Does What - Odoo Native vs Odoo App vs n8n
15. Odoo Custom App - What It Does
16. n8n Workflows (External Only)
17. Apollo Data Extraction via Playwright
18. AI Model Selection & Cost Optimization
19. Odoo Configuration Required
20. Phase 2 Roadmap

---

## 1. Architecture - Odoo App vs n8n

| Layer | Tool | Role |
|-------|------|------|
| Odoo Native | Odoo 19 CE | CRM, pipeline, email gateway (Gmail OAuth 2.0 per rep via `google_gmail` module), calendar sync (Google Calendar two-way sync via `google_calendar` module + Meeting-Lead Auto-Linker), assignment, activities, projects, dashboards |
| Odoo Custom App | Odoo Module + Claude API | AI-powered features: junk filter, enrichment, scoring, follow-up email drafting, personalized emails, MOM generation, presale agenda, proposal generation, presale email drafting, lead retro |
| Odoo `mail_smart_link` Module | Custom Odoo Module | Smart email routing: prevents duplicate leads when known customers send new emails (overrides `message_new` on `crm.lead`) |
| Gmail Workspace Add-on | Google Apps Script | Gmail sidebar with Odoo CRM context, log Gmail-sent emails to leads, create leads from Gmail, manual lead linking, dedup via Message-ID |
| External Automation | n8n (self-hosted) | External integrations: Apollo data (via Playwright), Google Sheets WBS, **Google Drive (proposal templates & generated proposals)**, Teams alerts, presale MOM split |
| Apollo Data Access | Playwright (via n8n or standalone) | **All Apollo data extraction (conversations, recordings, enrichment, prospects). Apollo confirmed: NO API available for any of these.** |

### Why Odoo App instead of FastAPI?

- Emails (auto-ack, follow-ups, MOM drafts) go out directly from Odoo - no external routing
- Calendar stays synced between Google Calendar and Odoo natively via `google_calendar` module (two-way sync, per-user OAuth). Synced meetings auto-linked to CRM leads.
- Follow-up activities and daily task view are native Odoo features
- Reps work 100% inside Odoo - no need to check another system
- Fewer moving parts - one less server to maintain (no FastAPI/VPS needed just for AI)
- Odoo app can call Claude API directly via Python (Odoo is Python-based)

### What n8n still handles (Odoo cannot do these):

- **Apollo data extraction via Playwright** (Apollo confirmed: NO API for recordings or conversations. All Apollo data access is via Playwright browser automation.)
- Processing presale meeting recordings and splitting MOM by ticket #
- Generating WBS in Google Sheets (Sheets API integration)
- **Google Drive integration** (fetching proposal templates, writing generated proposals back to Drive)
- Sending Teams webhook notifications (external push)
- Apollo prospect import for outbound (via Playwright)

---

## 2. Odoo Community Edition - What We Build

**Odoo 19 Community Edition only.** No Enterprise edition. All features are built custom or sourced from third-party Community modules. The goal is to build everything custom where possible.

| Need | Community Status | Our Approach |
|------|-----------------|--------------|
| AI Email Writer (smart drafting) | Not available | **BUILD:** Custom app calls Claude API. AI Follow-up Email Drafter generates contextual drafts for each follow-up. |
| AI Reply Suggester (Chatter AI) | Not available | **BUILD:** Claude API generates suggested replies. Shown in activity notes. |
| Marketing Automation (drip sequences) | Not available | **BUILD:** Automation Rules + Scheduled Actions create follow-up activities. Custom app handles timing logic. |
| Activity Plans (auto-create sequences) | Basic activities only | **BUILD:** Automation Rule on lead assignment creates Day 2/5/10 follow-up activities automatically. |
| Predictive Lead Scoring (ML) | Not available | **BUILD:** ICP-fit scoring via Claude API. Already planned as custom skill. |
| AI Meeting Transcription | Not available | **USE:** Apollo for recordings. n8n fetches transcript. |
| AI Sentiment Analysis | Not available | **BUILD if needed:** Claude API can analyze sentiment per conversation. |
| Centralized Email (all reps via Odoo) | Basic mail gateway | **BUILD:** `mail_smart_link` Odoo module (smart email routing, prevents duplicate leads) + Gmail Workspace Add-on (Apps Script: sidebar, log emails, manual linking). Gmail OAuth 2.0 per rep via Odoo's `google_gmail` module. |
| Presale Email Drafting | Not available | **BUILD:** AI drafts emails based on presale discussions and customer replies on sub-tickets. |
| Lead Closure Retro | Not available | **BUILD:** AI generates detailed retrospective on lead won/lost. |

**Bottom line:** By building a custom Odoo app with Claude API on Community Edition, we get all the AI capabilities we need at ~$80-128/mo in API costs. Zero Enterprise dependency.

---

## 3. Inbound Flow (23 Steps)

Complete lifecycle from lead capture to deal closure and retrospective. Color coding shows system ownership. Most steps run inside Odoo via the custom app. n8n only handles external integrations.

| # | Step | System | Notes |
|---|------|--------|-------|
| 1 | Lead Received | Trigger | Email / web form / referral / phone creates lead in Odoo CRM |
| 2 | Junk / Marketing Filter | Odoo+AI | Odoo app calls Claude to classify lead |
| 3 | Auto-Enrichment | Odoo+AI | **Apollo (via Playwright) as primary data source** -> Claude structures into 30 fields |
| 4 | Lead Scoring | Odoo+AI | Odoo app calls Claude: 0-100 + qualification |
| 5 | Lead Assignment | Odoo | Odoo native rules: round-robin / territory |
| 6 | Auto-Ack Email + **Rep's Calendar Link** | Odoo+AI | Personalized email with **assigned rep's calendar booking link from their profile** |
| 7 | Follow-up Activities Created | Odoo | Day 2/5/10 follow-up tasks for rep |
| 8 | AI Drafts Follow-up Emails | Odoo+AI | Contextual draft per follow-up |
| 9 | Rep Reviews & Sends Follow-ups | Odoo | Rep opens My Activities, reviews drafts, sends |
| 10 | Meeting Scheduled | Odoo | Client books via Calendly/Google Calendar. Event syncs to Odoo via `google_calendar` module. Meeting-Lead Auto-Linker matches attendee to lead automatically. |
| 11 | Meeting Recorded | External | Apollo records (video + transcript), fallback: GMeet. **Transcript fetched via Playwright (no Apollo API).** |
| 12 | Client MOM Generated | Odoo+AI | Draft email for rep. Also logged to lead. |
| 13 | Presale Ticket Created | Odoo+AI | Gist of ALL discussions added. Ticket = primary presale source. |
| 14 | Discussion Sync to Ticket | Odoo+AI | AI generates detailed MOMs, strips financial numbers before syncing to ticket |
| 15 | **Daily Presale Agenda (10:30 AM)** | Odoo+AI | **Per ticket: customer responses, new info, queries, who answers. Individual assignments.** |
| 16 | Presale Meeting Recorded | External | Recorded with ticket # mentioned per topic |
| 17 | Presale MOM Split by Ticket | n8n | n8n fetches recording, Claude splits by ticket # |
| 18 | **AI Drafts Presale Emails** | Odoo+AI | **MOM on ticket + draft client email on LEAD (in "My Activities")** |
| 19 | WBS Generated (AI + Human Loop) | n8n + Odoo | **AI generates WBS -> Human validates/modifies -> "Ready for Proposal"** |
| 20 | Proposal from WBS + Templates | n8n+AI | **n8n pulls template from Google Drive, Claude generates scope/team/financial, writes proposal back to Drive** |
| 21 | Rep Reviews & Sends Proposal | Odoo | Reviews proposal, sends from Odoo |
| 22 | Tracking & Close | Odoo | Pipeline updates, follow-ups, win/loss |
| 23 | **Lead Closure Retrospective** | Odoo+AI | **AI retro on win/loss - logged to PRESALE TICKET (not lead) so all team members can see it** |

---

## 4. Step-by-Step Detail

| # | Step | System | What Happens |
|---|------|--------|-------------|
| 1 | Lead Received | Trigger | Email / web form / referral / phone creates lead in Odoo CRM |
| 2 | Junk / Marketing Filter | Odoo App + Claude | Odoo app calls Claude to classify lead. Junk/marketing -> assigned to Marketing User. Genuine -> continues to enrichment. |
| 3 | Auto-Enrichment | Odoo App + Claude | **Primary data source: Apollo (via Playwright).** n8n scrapes Apollo for company/contact data (employee count, revenue, tech stack, etc.) -> passes to Claude to structure and fill 30 fields on the lead. See Section 17. |
| 4 | Lead Scoring | Odoo App + Claude | Odoo app calls Claude: scores 0-100 based on ICP fit, intent signals, authority. **ICP criteria provided by sales team in a structured format (see below).** Qualification stored. |
| 5 | Lead Assignment | Odoo Native | Odoo native assignment rules: round-robin, territory. No custom development needed. |
| 6 | Auto-Ack Email + Rep's Calendar Link | Odoo App + Claude | **Fully AI-generated email**, tailored to what the client is asking about. E.g., if client inquires about a specific industry or service, AI acknowledges expertise in that area ("We're an industry leader in X, and it would be great to connect"). **Includes assigned rep's calendar booking link from their Odoo profile.** Email sent from Odoo (tracks opens, replies). |
| 7 | Follow-up Activities Created | Odoo Native | Automation Rule creates scheduled activities: Day 2, Day 5, Day 10 follow-ups. Assigned to lead owner. |
| 8 | AI Drafts Follow-up Emails | Odoo App + Claude | For each follow-up activity, Odoo app calls Claude to generate a contextual email draft. Draft stored in activity notes for rep to review. |
| 9 | Rep Reviews & Sends Follow-ups | Odoo Native | Rep opens 'My Activities Today' view. Sees AI-drafted email, reviews/edits, sends. If client replied: timing already reset (Step 8). |
| 10 | Meeting Scheduled | Odoo Native | Client books via rep's Calendly link or Google Calendar. `google_calendar` module syncs event to Odoo (every 15-30 min). Meeting-Lead Auto-Linker matches attendee email to partner → finds active lead → links meeting to lead automatically. Meeting visible on lead record. |
| 11 | Meeting Recorded | External | Apollo records (video + transcript). Fallback: Google Meet if Apollo unavailable. |
| 12 | Client MOM Generated | Odoo App + Claude | **n8n fetches Apollo transcript via Playwright (no API available)** -> passes to Odoo app. Odoo app calls Claude to generate MOM. Saved as DRAFT email for rep. Logged to chatter. |
| 13 | Presale Ticket Created | Odoo App + Claude | Sales creates ticket in Odoo Projects. Odoo app calls Claude to gist ALL prior discussions. Gist pushed as first note. Ticket = primary presale source. |
| 14 | Discussion Sync to Ticket | Odoo App | Odoo app monitors new discussions on the lead. **AI processes full transcripts and generates detailed presale MOMs, stripping financial numbers (pricing, discounts, payment terms) before syncing to ticket.** |
| 15 | Daily Presale Agenda (10:30 AM) | Odoo App + Claude | See Section 11 for full detail. Generates ticket-wise agenda with customer responses, new info, queries, who needs to answer. Individual ticket owners get only their ticket updates. |
| 16 | Presale Meeting Recorded | External | Internal presale meetings recorded. Team mentions ticket # when switching topics. |
| 17 | Presale MOM Split by Ticket | n8n | n8n fetches presale recording, sends to Claude. Claude splits MOM by ticket #. n8n writes each section to its Odoo ticket. |
| 18 | AI Drafts Presale Emails | Odoo App + Claude | Two parallel outputs: (1) Presale MOM logged to ticket for internal team. (2) Draft client email created as activity on the LEAD - appears in rep's "My Activities" for review and send. See Section 10. |
| 19 | WBS Generated (AI + Human Loop) | n8n + Odoo | AI generates initial WBS. Pre-sale team validates and modifies. Once marked "Ready for Proposal", triggers proposal generation. See Section 9. |
| 20 | Proposal from WBS + Templates | n8n + Claude | Presale clicks "Request Proposal from AI" in Odoo -> triggers n8n flow -> n8n pulls proposal template from Google Drive + WBS data from Sheets -> Claude generates scope, team, financial sections -> n8n writes completed proposal back to Google Drive -> link attached to ticket. |
| 21 | Rep Reviews & Sends Proposal | Odoo | Reviews proposal, customizes, sends to client from Odoo (tracked). |
| 22 | Tracking & Close | Odoo Native | Pipeline updates, follow-up reminders. Win: handoff to delivery. Loss: reason logged. |
| 23 | Lead Closure Retrospective | Odoo App + Claude | On lead status change to Won or Lost, AI performs full retro. **Retro logged to the linked presale ticket (not lead) so it's visible to the entire team.** See Section 12. |

---

## 5. Follow-up Email System (Steps 7-9)

After the initial auto-acknowledgment email (Step 6), the system creates scheduled follow-up activities with AI-drafted emails. The sales team reviews and sends these daily. If a client replies, all pending follow-ups are cancelled and rescheduled from the reply date with updated context.

### How It Works - Technical Detail:

| Component | Implementation | Detail |
|-----------|---------------|--------|
| Initial Email (Step 6) | Automation Rule + Odoo App | On lead assignment: Odoo app calls Claude to **generate a fully AI-written acknowledgment email**, tailored to the client's inquiry (industry, service, questions asked). Positions us as experts in what the client is looking for. **Includes assigned rep's personal calendar booking link.** Sent automatically from Odoo. |
| Follow-up Scheduling (Step 7) | Automation Rule | Same rule that sends initial email also creates 3 activities. **Standard: Day 2/5/10. Optimized by lead score (see below). Weekends are skipped - if a follow-up falls on Sat/Sun, it moves to Monday.** All assigned to lead owner. |
| AI Draft Generation (Step 8) | Scheduled Action + Odoo App | **Daily scheduled action (9 AM):** Finds follow-up activities due today or tomorrow. Calls Claude with lead context + follow-up #. **Fully AI-generated email (not template-based)** - Claude writes the complete email with full creative control based on context. Draft saved in activity notes. |
| Daily Review (Step 9) | Odoo Native Activities | Rep opens 'My Activities' filtered by today. Reviews AI-drafted email, edits if needed, sends from Odoo. Marks activity as done. |
| Reply-Aware Timing | Custom Module Override (`message_post`) + Odoo App | On incoming email: Cancel pending follow-ups. Classify reply intent (interested/not interested/OOO/referral). If interested: **same follow-up cycle restarts from reply date with same gaps.** E.g., client replies Day 3 -> cancel Day 5 follow-up -> next follow-up now Day 3+4=Day 7, then Day 3+8=Day 11. If not interested: stop. If OOO: reschedule to return date. |
| Sequence End | Odoo App | After final follow-up with no reply: Lead status set to 'No Response'. Optional: re-engagement queue. |

### Follow-up Timing - Standard vs Score-Optimized:

| Lead Score | Follow-up #1 | Follow-up #2 | Follow-up #3 | Rationale |
|-----------|-------------|-------------|-------------|-----------|
| **Standard (default)** | **Day 2** | **Day 5** | **Day 10** | Default for all leads |
| **Hot (score >80)** | Day 1 | Day 3 | Day 7 | High-intent leads need faster engagement |
| **Warm (score 40-80)** | Day 2 | Day 5 | Day 10 | Standard pacing |
| **Cold (score <40)** | Day 3 | Day 7 | Day 14 | Lower urgency, more breathing room |

> **Weekend handling:** All follow-up dates are calculated on **business days only**. If a follow-up falls on Saturday or Sunday, it automatically moves to the next Monday. This prevents emails being sent when clients are unlikely to read them.

### Follow-up Email Content - Fully AI-Generated:

Follow-up emails are **fully AI-generated** by Claude (not template-based). This provides more personalized, contextual communication. Claude receives:

- Lead data: company name, industry, contact name, title, enriched fields
- Follow-up number: 1st, 2nd, or 3rd (tone escalation guidance)
- Previous emails sent (subjects and key points - avoid repetition)
- Any replies received (if reply-aware rescheduling occurred)
- Lead score and qualification notes (tailor urgency)
- **Rep's personal calendar booking link** to include in email
- Tone guidance: 1st = warm/helpful, 2nd = value-adding, 3rd = direct/final

Claude writes the full email - subject line, body, CTA - with creative freedom based on the context. The rep always reviews before sending.

### Sample Follow-up Sequence:

| # | Day | Tone | Subject Pattern | Goal |
|---|-----|------|----------------|------|
| 1 | Day 2 | Warm, helpful | Quick follow-up on your inquiry about [topic] | Check if they saw initial email. Offer to answer questions. |
| 2 | Day 5 | Value-adding | Thought this might help: [relevant resource/insight] | Provide value. Share case study or relevant insight for their industry. |
| 3 | Day 10 | Direct, final | Should I close your file? | Breakup email. Creates urgency. Often gets highest reply rate. |

*Note: Day numbers are defaults (adjusted by lead score). Weekend days are skipped. When a client replies, the system resets timing from the reply date. The rep always has final say - they review and send manually.*

---

## 6. Junk / Marketing Lead Filtering (Step 2)

Before spending API credits on enrichment, the Odoo app classifies lead quality. This runs inside Odoo as an automated action triggered on lead creation.

All junk/marketing leads go to Marketing User (no auto-delete). This allows the marketing team to understand junk lead sources and work on reducing them.

| Aspect | Detail |
|--------|--------|
| How it works | Odoo automated action fires on new lead creation. Odoo app calls Claude with lead data (email, subject, body, source). Claude classifies as GENUINE, MARKETING, or JUNK. |
| If Genuine | Field x_lead_quality = 'genuine'. Lead continues to enrichment. |
| If Junk / Marketing | Field x_lead_quality = 'marketing' or 'junk'. **All junk/marketing leads go to Marketing User (never auto-deleted).** Marketing User reviews to understand sources and patterns, then decides to delete/recycle. |
| Cost saving | Enrichment ~$0.02/lead. Junk filter ~$0.003/lead. If 40% inbound is junk: net saving on wasted enrichment. |

---

## 7. Meeting Recording & Client MOM (Steps 11-12)

Two types of MOM: Client MOM (external, for client) and Presale MOM (internal, split by ticket). Client MOM runs mostly inside Odoo. Presale MOM needs n8n for recording fetch.

### A. Client Meeting MOM (Step 12):

| Aspect | Detail |
|--------|--------|
| Recording source | Apollo records client meeting (video + transcript). **n8n fetches transcript via Playwright (Apollo has no API). Playwright logs into Apollo, extracts recording/transcript -> passes to Odoo.** |
| MOM generation | Odoo app calls Claude with transcript. Generates: attendees, discussion points, decisions, action items, next steps, key signals (budget, timeline, objections). |
| Output | 1. DRAFT email in Odoo - rep reviews and sends to client. 2. Full MOM logged to lead record in Odoo chatter. |
| Why draft? | Rep should review before sending. AI may misinterpret context or include internal signals not meant for client. |
| Who sends? | **Always the sales rep who attended the meeting.** They can verify accuracy since they were present. Draft is assigned to the meeting attendee (the lead owner). |

### B. Presale Meeting MOM (Steps 16-17):

| Aspect | Detail |
|--------|--------|
| Recording source | Internal presale meeting recorded **on Apollo**. Multiple tickets discussed, team mentions ticket # per topic. **Transcript fetched via Playwright (same as client meetings).** |
| Processing | n8n fetches recording from Apollo via Playwright -> sends transcript to Claude. Claude identifies ticket #s and splits MOM per ticket. n8n writes each section to correct ticket in Odoo. |
| Why n8n? | Recording is external (not in Odoo). n8n handles the fetch + split + write-back pipeline. |

---

## 8. Presale Ticket Lifecycle (Steps 13-20)

The presale ticket in Odoo Projects is the PRIMARY source for technical evaluation.

### Key Design Decisions:

- **Ticket as Primary Source:** Presale/tech team works from TICKET, not lead. Lead remains the sales view with financial info.
- **Financial Data Excluded:** Pricing, discounts, payment terms stay on lead only. **AI processes full transcripts/discussions and generates detailed presale MOMs, but strips out any financial numbers (pricing, discounts, payment terms) before syncing to ticket.** The ticket gets rich technical context without exposing commercial details.
- **Ticket # Convention:** Confirmed verbal cue: **"Moving to ticket 12345"** when switching topics in presale meetings. AI uses this to split MOM accurately.
- **WBS Human-in-the-Loop:** AI generates initial WBS. Pre-sale team validates and modifies. Version history maintained (AI version vs finalized version). Only after human approval does proposal generation trigger.
- **Proposal from Templates:** Pre-sale team maintains proposal templates **on Google Drive** (existing practice). **n8n fetches templates from Drive, passes to Claude for generation, writes completed proposals back to Drive.** Template ownership is with the pre-sale team.

---

## 9. WBS & Proposal Generation (Steps 19-21)

| Stage | Who | System | What Happens |
|-------|-----|--------|-------------|
| Presale marks ticket ready | Presale | Odoo | Marks ticket status as 'Ready for WBS' in Odoo. |
| AI generates initial WBS | n8n + Claude | n8n | n8n pulls ticket data (requirements, MOMs, gist). Claude generates WBS. **Uses the WBS Skill (see below).** Output in Google Sheet. |
| **Human validates WBS** | **Presale Team** | **Sheets + Odoo** | **Pre-sale team reviews AI-generated WBS. Makes modifications as needed. Google Sheets revision history used: AI version named "AI Generated", latest revision is human-modified.** |
| Tech team estimates | Tech Team | Sheets | Opens Sheet, fills effort estimates per line item. Multiple people can edit collaboratively. |
| WBS review | Presale + Tech Lead | Sheets + Odoo | Review estimates. Mark as 'Estimation Complete' in Odoo ticket. |
| **Presale requests proposal via UI button** | **Presale** | **Odoo** | **Presale clicks "Request Proposal from AI" button on the ticket in Odoo. This triggers the proposal generation flow.** |
| Proposal generated | n8n + Odoo App + Claude | n8n + Odoo | **Flow: n8n pulls proposal template from Google Drive -> passes template + WBS data to Claude -> Claude generates new scope, team, and financial sections -> n8n writes the completed proposal back to Google Drive as a new document -> link attached to Odoo ticket.** |
| Rep reviews & sends | Sales Rep | Odoo | Reviews proposal, customizes, sends to client from Odoo (tracked). |

### WBS Skill in Claude

A dedicated Claude skill called **"WBS"** is configured for the pre-sale team:

- **Purpose:** Understand project requirements and generate WBS in the format the pre-sale team needs
- **Training:** Pre-sale team provides the skill with:
  - Sample WBS documents
  - The specific format/structure they need
  - Column definitions (Module, Task, Subtask, Complexity, Hours, Rate, etc.)
  - Templates per service type
- **Usage:** When a ticket is marked "Ready for WBS", this skill is invoked with all ticket context
- **Output:** Structured WBS that pre-sale team can immediately review and modify

---

## 10. AI-Drafted Emails for Presale Tickets

**Purpose:** After presale discussions or when customers reply via email, AI drafts client-facing emails summarizing confirmations, open questions, and next steps. Drafts appear in the rep's **"My Activities"** on the lead - same place as follow-up email drafts - so reps have a single workflow for all outbound email actions.

### How It Works:

| Aspect | Detail |
|--------|--------|
| Trigger | After presale meeting MOM is logged to the ticket, OR when a customer replies via email to the sales team member |
| What happens in parallel | 1. **Presale MOM** gets logged on the presale ticket (for internal team reference). 2. **Draft client email** gets created as an activity on the LEAD in "My Activities" (for the sales rep to review and send). |
| What AI receives | Presale discussion/MOM for that ticket, customer's latest email replies, full conversation history, any confirmations made, any open questions identified by presale |
| What AI drafts | Client-facing email covering: confirmations of what was discussed, follow-up queries from presale, references to past conversations, next steps |
| Output | **Draft email created as an activity on the LEAD** - appears in rep's "My Activities" view, same as follow-up drafts |
| Human review | Sales rep opens "My Activities", sees the presale email draft alongside any follow-up drafts, reviews/edits, sends from Odoo |

### Why "My Activities" on the Lead (Not the Ticket)?

- **Single workflow:** Reps check one place ("My Activities") for ALL email drafts - follow-ups and presale emails alike
- **Lead = client communication hub:** All outbound emails to clients go from the lead record. Tickets are for internal presale work.
- **MOM stays on ticket:** The detailed internal MOM is on the ticket for the presale team. The client-facing email draft is on the lead for the sales rep.

### Example Scenarios:

1. **After presale meeting:** MOM logged to ticket. AI also creates a draft email activity on the lead - summarizing what to confirm with the client and what questions to ask. Rep sees it in "My Activities" next morning.
2. **Customer replies via email:** Customer sends answers to technical questions. AI drafts a follow-up email activity on the lead - acknowledging answers and raising new points from the presale team's analysis.
3. **Pending queries:** Presale identifies questions during internal discussion. AI drafts an email activity on the lead asking the client those specific questions with proper context.

---

## 11. Daily Presale Agenda - 10:30 AM

**Timing: 10:30 AM daily.**

Every day at 10:30 AM, the system reviews all open tickets that need presale discussion and generates a ticket-wise agenda.

### What the Agenda Contains (Per Ticket):

| Item | Detail |
|------|--------|
| **Customer Responses** | Has the customer responded? What did they say? Any new answers received? |
| **New Information** | Any new information that has come in from the customer since last agenda |
| **Queries to Discuss** | What open queries need to be discussed in presale? |
| **Who Needs to Answer** | Which specific team member is responsible for addressing each query? |
| **Ticket Status** | Current status, blockers, action items from previous discussions |

### Individual Assignment Logic:

- **Agenda is posted directly on each ticket** in Odoo
- Everyone subscribed to a ticket gets the update notification
- If someone is on 5 tickets, they get **5 separate ticket updates** to follow
- This allows them to **prepare specifically** for each ticket without information overload
- They know exactly which tickets need their input before the meeting starts

### Technical Implementation:

| Component | Detail |
|-----------|--------|
| Scheduled Action | Runs daily at 10:30 AM |
| Data Source | All open presale tickets in Odoo Projects |
| AI Processing | Claude analyzes each ticket: recent activity, customer replies, pending items, assigned person |
| Output Format | **Agenda posted as a note on each individual ticket in Odoo** |
| Delivery | **Posted on the ticket itself.** All ticket subscribers get notified via Odoo's built-in subscription/notification system. No separate Teams delivery needed for agenda - the ticket IS the delivery channel. |
| AI Model | Claude Haiku 4.5 (cost-efficient for summarization - see Section 18) |

---

## 12. Lead Closure Retrospective

**Trigger:** When a lead status changes to **Won** or **Lost**.

AI performs a comprehensive retrospective of the entire lead lifecycle.

> **Important: Retro is logged at the TICKET level, not the lead level.** Leads are not accessible to everyone on the team (e.g., presale, tech). Since the presale ticket is the shared workspace visible to all relevant team members, the retro is posted to the linked presale ticket. This ensures everyone involved in the deal can see the learnings. When the lead status changes to Won/Lost, the Odoo app finds the linked presale ticket and adds the retro there.
>
> **Fallback:** If a lead has no linked presale ticket (e.g., small deal closed directly without presale), the retro is logged at the lead level instead.

### What the Retro Covers:

| Area | What AI Analyzes |
|------|-----------------|
| **What We Did Well** | Effective communication, quick responses, good technical evaluation, strong proposal |
| **What Could Be Improved** | Missed follow-ups, slow response times, gaps in technical understanding, proposal weaknesses |
| **Time Analysis** | Total time from lead to close. Time spent in each stage. Were there bottlenecks? |
| **Repeat Communication** | Were there repeated questions or clarifications? Did we ask the same thing twice? Did the client have to repeat themselves? |
| **Response Time Audit** | Average time to respond to client emails. Any delays? |
| **Presale Efficiency** | How many presale meetings were needed? Were they productive? |
| **Proposal Quality** | Was the proposal accepted as-is or required multiple revisions? |
| **Key Learnings** | Specific, actionable insights for future deals of similar nature |

### Output:

- **Full retro document logged to the linked PRESALE TICKET in Odoo** (not the lead - tickets are visible to all team members)
- Summary posted to Teams channel for team visibility
- Key learnings tagged for searchability (by industry, deal size, outcome)

### Technical Detail:

| Aspect | Detail |
|--------|--------|
| Trigger | Automation rule on lead stage change to Won/Lost |
| Flow | Lead status changes -> Odoo app finds linked presale ticket -> generates retro -> posts to ticket. **If no ticket exists, retro is logged at lead level as fallback.** |
| What AI receives | Complete lead history: all emails, MOMs, presale notes, ticket discussions, WBS, proposal, timeline of all activities |
| AI Model | Claude Sonnet 4.6 (needs analytical depth - see Section 18) |
| Output | Structured retro document posted as a note on the presale ticket |
| Why ticket? | Leads have restricted access (sales only). Tickets are visible to presale, tech, and sales - everyone who needs the learnings. |

---

## 13. Centralized Email Management

**Solution:** Odoo native Gmail OAuth 2.0 per rep (via `google_gmail` module) + Gmail Workspace Add-on (Apps Script) + custom `mail_smart_link` Odoo module. Full spec: `odoo19-gmail-crm-integration-spec.md`

**Goal:** Every sales team member works through Odoo for ALL email communication. Their email needs to be connected to Odoo so all conversations are centralized.

**Current setup:** Each rep has their own email address. They CC sales@ on all customer communications. This pattern is formalized in Odoo - each rep's email is connected via Gmail OAuth 2.0, and sales@ serves as the shared alias that creates leads.

> **Google Workspace Business Starter:** Plain IMAP/SMTP with username/password is no longer supported by Google (deprecated May 2025). All Gmail connections must use OAuth 2.0. Odoo 19's `google_gmail` module handles this — each rep authorizes Odoo once via Google OAuth consent flow. Requires a Google Cloud Project with OAuth client ID configured.

### Requirements & Solutions:

| Requirement | Solution |
|-------------|----------|
| **Email Connection** | Odoo native: Gmail OAuth 2.0 per rep (via `google_gmail` module). Incoming mail fetched via OAuth-authenticated IMAP, outgoing via Gmail SMTP — both authenticated through OAuth, not passwords. Each rep's email flows through Odoo. |
| **Incoming Reply Logging** | Odoo native: `In-Reply-To` / `References` headers auto-match replies to existing lead threads. |
| **Reply from Odoo** | Odoo native: Reps send from Odoo UI via OAuth-authenticated Gmail SMTP. Emails appear in Gmail Sent folder automatically. |
| **New Thread Matching** | **`mail_smart_link` module** (custom): Overrides `message_new` on `crm.lead`. When a known customer sends a new email (no thread reference), routes to their existing active lead instead of creating a duplicate. |
| **Thread Linking** | **Gmail Workspace Add-on**: Reps can manually search and link any email to any lead from within Gmail. |
| **Emails from Gmail logged** | **Gmail Workspace Add-on**: "Log This Email" button logs Gmail-sent emails to Odoo leads. Dedup via RFC 2822 Message-ID. |
| **Odoo context in Gmail** | **Gmail Workspace Add-on**: Contextual sidebar shows partner info + associated leads when opening any email. |

### Three Components:

| Component | Technology | What It Does |
|-----------|-----------|--------------|
| **Odoo Native Config** | Gmail OAuth 2.0 per rep (`google_gmail` module) | Incoming email fetch (every 5 min) via OAuth-authenticated IMAP, outgoing via OAuth-authenticated Gmail SMTP, thread matching via headers, sales@ alias for new leads |
| **Gmail Workspace Add-on** | Google Apps Script | Contextual sidebar (Odoo context in Gmail), log email to lead, create lead from Gmail, manual lead linking, duplicate prevention via Message-ID |
| **`mail_smart_link` module** | Custom Odoo module | Overrides `message_new` on `crm.lead` — routes new emails from known customers to existing active leads (prevents duplicate lead creation) |

### Data Flows:

| Scenario | What Happens |
|----------|-------------|
| Rep sends from Odoo | Logged in Odoo chatter (auto) + appears in Gmail Sent (auto). No action needed. |
| Rep sends from Gmail, CCs sales@ | Odoo IMAP fetches from sales@ → `mail_smart_link` routes to existing lead. No action needed. |
| Rep sends from Gmail, forgets CC | Rep opens sent email in Gmail → Add-on sidebar shows lead → clicks "Log This Email". Manual but recoverable. |
| Customer replies to Odoo thread | Odoo native: auto-linked via `In-Reply-To` header. No action needed. |
| Customer sends NEW email (known contact) | `mail_smart_link` intercepts: finds partner → finds active lead → attaches email to existing lead. No duplicate created. |
| Customer sends NEW email (unknown) | Odoo default: creates new lead. Correct behavior. |
| Duplicate prevention | Three layers: Add-on pre-check (Message-ID) → Odoo native dedup (message_process) → idempotent message_post. |

---

## 14. Who Does What - Odoo Native vs Odoo App vs n8n

Three clear layers. Odoo native for built-in features (Community Edition). Odoo custom app for AI-powered features (calls Claude directly). n8n only for external system integrations.

### Odoo Native (FREE - Community Edition):

| Feature | Why Here |
|---------|----------|
| CRM Pipeline & Stages | Built-in, all reps use daily |
| Lead Assignment Rules | Native round-robin / territory (no custom dev) |
| Email Send / Receive / Track | Mail gateway with conversation tracking |
| Calendar Sync (Google) | Two-way Google Calendar sync via `google_calendar` module (per-user OAuth, same Cloud Project as Gmail). Meeting-Lead Auto-Linker connects synced meetings to CRM leads. |
| Presale Tickets (Projects) | Built-in project/task module |
| Automation Rules + Custom Overrides | `base_automation` for lead creation, assignment, stage change, calendar sync. Custom `message_post` overrides for mail-related triggers (more reliable). |
| Activities (daily tasks) | 'My Activities' view for daily rep workflow |
| Dashboards & Reports | Built-in reporting engine |

### Odoo Custom App (~$100/mo Claude API):

| Feature | Why Here |
|---------|----------|
| Junk / Marketing Detection | Automated action calls Claude on lead create |
| Data Enrichment (30 fields) | Fills custom fields via Claude API |
| Lead Scoring (0-100) | Scores stored in Odoo, computed by Claude |
| Auto-Ack + Rep's Calendar Link | Personalized email sent FROM Odoo with rep's booking link |
| AI Follow-up Email Drafter | Claude generates contextual drafts per follow-up |
| Reply-Aware Timing Adjuster | Resets follow-up schedule on client reply |
| Client MOM (draft) | MOM saved as draft email in Odoo for rep review |
| Discussion Gist -> Ticket | Summarizes discussions when ticket created |
| Discussion Sync to Ticket | Monitors lead activity, syncs non-financial to ticket |
| Daily Presale Agenda (10:30 AM) | Generated by Claude, individual assignments, posted on tickets |
| **AI Presale Email Drafting** | **MOM on ticket (internal) + draft client email on lead's "My Activities" (for rep to send)** |
| Proposal from WBS + Templates | UI button triggers n8n flow: pulls template from Google Drive + WBS from Sheets, Claude generates, writes back to Drive |
| **Lead Closure Retro** | **Full retrospective on won/lost - logged to presale ticket for team visibility** |
| **Centralized Email Matching** | **`mail_smart_link` module auto-routes new emails from known customers to existing leads** |

### n8n (FREE - self-hosted):

| Feature | Why Here |
|---------|----------|
| **All Apollo Data Access (Playwright)** | **Apollo confirmed: NO API available. All data (recordings, conversations, prospects) extracted via Playwright browser automation.** |
| Presale MOM Split by Ticket | Needs recording file from external source |
| WBS to Google Sheets | Sheets API integration for collaborative editing |
| **Google Drive (Proposals)** | **Fetches proposal templates from Drive, writes generated proposals back to Drive** |
| Teams Webhook Alerts | External push notifications via webhook |
| Stale Deal Monitor | Queries Odoo for stuck deals (stage-wise thresholds), alerts via Teams |
| Prospect Import (Outbound) | Apollo search via Playwright for outbound |

---

## 15. Odoo Custom App - What It Does

A single Odoo module (Python-based) that integrates Claude API. Installed like any Odoo app. Contains automated actions, server actions, and scheduled jobs. **Replaces Enterprise AI features** with our own Claude-powered equivalents.

| Feature | Odoo Trigger | What the App Does | AI Model |
|---------|-------------|-------------------|----------|
| Junk Filter | Automated action: on lead create | Calls Claude with lead data. Sets x_lead_quality. If junk: reassigns to Marketing User. | Haiku 4.5 |
| Enrichment | After junk filter passes | **Primary source: Apollo data fetched via Playwright (n8n).** Claude structures raw Apollo data into 30 custom fields on the lead. | Haiku 4.5 |
| Lead Scoring | After enrichment completes | Calls Claude with enriched data + **ICP criteria (provided by sales team in a structured format)**. Sets x_lead_score (0-100). Sales team fills out an ICP definition form; Claude uses it as scoring rubric. | Haiku 4.5 |
| Auto-Ack Email | After assignment | **Fully AI-generated acknowledgment email.** Tailored to client's inquiry - references their industry/service/questions, positions our expertise. Injects assigned rep's calendar link. Queues via Odoo mail gateway. | Sonnet 4.6 |
| Follow-up Email Drafter | Scheduled action: daily **9 AM** | Finds follow-up activities due today/tomorrow. Calls Claude with lead context + follow-up #. **Fully AI-generated emails.** Saves draft in activity notes. | Sonnet 4.6 |
| Reply-Aware Timing | Custom module `message_post` override on `crm.lead` | Detects reply on lead with pending follow-ups. Cancels pending activities. Classifies reply intent. Reschedules. | Haiku 4.5 |
| Meeting-Lead Auto-Linker | On calendar event sync | Matches attendee emails to partners and active leads. Links meeting to lead automatically. Enables post-meeting triggers (e.g., create follow-up activity). | N/A (no AI) |
| Client MOM | Transcript received (from n8n) | Calls Claude to generate structured MOM. Creates draft email. Logs to chatter. | Sonnet 4.6 |
| Ticket Gist | On presale ticket creation | Calls Claude to summarize all lead discussions. Posts gist as first note on ticket. | Sonnet 4.6 |
| Discussion Sync | Custom module `message_post` override on `crm.lead` (extends reply-aware override) | **AI processes full discussions, generates detailed presale MOM, strips financial numbers (pricing/discounts/payment terms) before syncing to linked ticket.** | Sonnet 4.6 |
| Presale Agenda | Scheduled action: daily **10:30 AM** | Queries all active presale tickets. Generates ticket-wise agenda with individual assignments. Posts to Teams via n8n. | Haiku 4.5 |
| **Presale Email Drafting** | **n8n callback + custom module `message_post` override on `project.task`** | **Creates draft client email as activity on the LEAD (not ticket). Appears in rep's "My Activities" alongside follow-up drafts. MOM stays on ticket for internal team.** | **Sonnet 4.6** |
| Proposal Generation | Manual trigger: presale clicks "Request Proposal from AI" button on ticket | **Triggers n8n flow: n8n pulls proposal template from Google Drive + WBS data from Sheet -> Claude generates scope, team, financial sections -> n8n writes completed proposal back to Google Drive -> link attached to ticket in Odoo.** | Opus 4.6 |
| **Lead Closure Retro** | **Automated action: on lead stage change to Won/Lost** | **Analyzes complete lead history. Generates structured retrospective. Posts retro to linked presale TICKET (not lead) for team-wide visibility.** | **Sonnet 4.6** |
| **Email Thread Matching** | **On incoming email from unknown thread** | **Matches new email threads to existing leads/contacts by email/domain.** | **Haiku 4.5** |

---

## 16. n8n Workflows (External Only)

n8n only handles what Odoo cannot: external API calls, recording processing, Sheets generation, Playwright scraping, and webhook pushes.

| # | Workflow | Trigger | Actions |
|---|---------|---------|---------|
| W1 | Apollo Recording Fetch | Meeting ended (calendar event) | **Playwright logs into Apollo -> fetches transcript (no API available).** Passes transcript to Odoo app for MOM generation. |
| W2 | Presale MOM Splitter | Presale meeting recording ready | Fetches presale recording -> sends transcript to Claude. Claude splits by ticket #. n8n writes each section to correct Odoo ticket. |
| W3 | WBS Generator | Presale marks ticket ready | Pulls ticket data from Odoo -> **invokes WBS Skill** -> generates WBS in Google Sheet. Notifies tech team in Teams. |
| W4 | Teams Notifications | Various Odoo webhooks | Receives events from Odoo (new lead, assignment, stale deal, retro complete). Pushes formatted messages to Teams channels. |
| W5 | Stale Deal Monitor | Daily schedule | Queries Odoo for stuck deals. **Threshold is configurable per pipeline stage** (e.g., Qualified: X days, Meeting: Y days, Proposal: Z days). Alerts rep + manager via Teams. |
| W6 | Prospect Import (Outbound) | Weekly schedule | **Playwright scrapes Apollo search results** -> dedup -> import to Odoo. |
| **W7** | **Apollo Data Scraper (Playwright)** | **Scheduled / On-demand** | **Playwright logs into Apollo for ALL data extraction: conversations, enrichment data, prospect search. See Section 17.** |
| **W8** | **Proposal Generator** | **Presale clicks "Request Proposal" in Odoo** | **n8n pulls proposal template from Google Drive + WBS data from Sheet -> calls Claude to generate scope/team/financial sections -> writes completed proposal back to Google Drive -> links to Odoo ticket.** |

---

## 17. Apollo Data Extraction via Playwright

**Problem:** Apollo confirmed they do **NOT** support API access for recordings, conversations, or most data operations. There is no Apollo API available for our use cases.

**Solution:** Use Playwright (headless browser automation) to log into Apollo and extract ALL needed data dynamically. This is the **sole method** for Apollo integration.

We will proceed with Playwright despite the ToS risk. Apollo doesn't offer the API features we need, and we don't want to move away from Apollo.

### How It Works:

| Aspect | Detail |
|--------|--------|
| Tool | Playwright (Node.js or Python) |
| Hosting | Runs within n8n (n8n has Playwright support) or as a standalone scheduled script |
| Authentication | Uses Apollo credentials (stored securely in n8n credentials store) |
| What it extracts | **Meeting recordings & transcripts, conversation threads, messages, contact/company data, search results for prospect import** |
| Frequency | Scheduled (e.g., every few hours) or triggered on-demand (e.g., after meeting ends) |
| Output | Extracted data pushed to Odoo via API (Odoo XML-RPC or JSON-RPC) |

### Use Cases:

1. **Meeting Recording/Transcript Fetch:** After a client meeting, Playwright extracts the recording and transcript from Apollo. Passed to Odoo for MOM generation.
2. **Conversation Import:** Extract Apollo conversation history and log it to the relevant lead in Odoo. Gives sales reps full context without switching to Apollo.
3. **Data Enrichment Supplement:** Extract enrichment data from Apollo (tech stack, funding, recent news) and pass to Odoo enrichment pipeline.
4. **Contact Discovery:** Extract contact details from Apollo that may not be in the CRM yet.
5. **Prospect Import (Outbound):** Search Apollo for prospects, extract results, dedup, and import to Odoo.

### Technical Considerations:

| Concern | Mitigation |
|---------|-----------|
| Apollo rate limits / detection | Use realistic browser fingerprinting, human-like delays, rotate sessions |
| Session management | Store and reuse Apollo session cookies to minimize logins |
| Data freshness | Schedule runs at reasonable intervals (not aggressive) |
| Maintenance | Apollo UI changes may break selectors - need monitoring and selector updates |
| Apollo ToS | **Accepted risk.** Apollo doesn't provide the API we need. We proceed with Playwright. Will monitor for any ToS enforcement. |

---

## 18. AI Model Selection & Cost Optimization

**Principle:** Use the most cost-effective model for each activity based on complexity requirements.

| Activity | Model | Why This Model | Est. Cost/Call |
|----------|-------|---------------|----------------|
| Junk / Marketing Filter | **Claude Haiku 4.5** | Simple classification task. Fast, cheap. | ~$0.003 |
| Data Enrichment | **Claude Haiku 4.5** | Structured data extraction. Haiku handles well. | ~$0.02 |
| Lead Scoring | **Claude Haiku 4.5** | Scoring with clear criteria. Doesn't need deep reasoning. | ~$0.01 |
| Auto-Ack Email (AI-generated) | **Claude Sonnet 4.6** | Fully AI-generated, tailored to client's inquiry. Needs contextual writing quality. | ~$0.03 |
| Reply Intent Classification | **Claude Haiku 4.5** | Simple classification (interested/OOO/etc). | ~$0.003 |
| Discussion Sync (MOM + financial filter) | **Claude Sonnet 4.6** | Generates detailed presale MOMs and strips financial data. Needs content generation quality. | ~$0.03 |
| Email Thread Matching | **Claude Haiku 4.5** | Pattern matching on email/domain. | ~$0.003 |
| Daily Presale Agenda | **Claude Haiku 4.5** | Summarization of structured data. | ~$0.01 |
| Follow-up Email Drafting | **Claude Sonnet 4.6** | Needs nuanced, contextual writing. | ~$0.03 |
| Client MOM Generation | **Claude Sonnet 4.6** | Needs to identify key signals, structure complex info. | ~$0.05 |
| Ticket Discussion Gist | **Claude Sonnet 4.6** | Summarizing diverse conversations. | ~$0.03 |
| Presale Email Drafting | **Claude Sonnet 4.6** | Needs contextual understanding and good writing. | ~$0.03 |
| Lead Closure Retro | **Claude Sonnet 4.6** | Deep analysis across full lead history. | ~$0.08 |
| Presale MOM Split by Ticket | **Claude Sonnet 4.6** | Needs to identify topics and split accurately. | ~$0.05 |
| **Proposal Generation** | **Claude Opus 4.6** | **Highest quality needed. Client-facing document. Complex synthesis of WBS + template + context.** | ~$0.30 |
| **WBS Generation (Skill)** | **Claude Sonnet 4.6** | Needs analytical depth to break down requirements. | ~$0.08 |

### Estimated Monthly Cost (10 reps, ~200 leads/month):

| Category | Est. Monthly Cost |
|----------|------------------|
| Haiku tasks (high volume, simple: junk filter, scoring, enrichment, reply classification, email matching) | ~$10-18 |
| Sonnet tasks (medium-high volume: auto-ack emails, follow-ups, MOMs, gists, presale emails, retros, discussion sync) | ~$55-80 |
| Opus tasks (low volume, proposals only) | ~$15-30 |
| **Total estimated** | **~$80-128/mo** |


---

## 19. Odoo Configuration Required

### A. Custom Fields on Lead / Contact:

| Field | Type | Set By | Purpose |
|-------|------|--------|---------|
| x_lead_quality | Selection | Odoo App | genuine / marketing / junk (AI classifier) |
| x_lead_score | Integer (0-100) | Odoo App | Overall lead score from AI |
| x_followup_stage | Integer | Odoo App | Current follow-up # (1, 2, 3) |
| x_last_reply_date | Datetime | Odoo App | Last client reply date (for timing reset) |
| x_reply_intent | Selection | Odoo App | interested / not_interested / ooo / referral |
| x_is_it_company | Boolean | Odoo App | IT company flag (enrichment) |
| x_employee_count | Integer | Odoo App | Company headcount |
| x_annual_revenue | Monetary | Odoo App | Annual revenue (USD) |
| x_tech_stack | Text (JSON) | Odoo App | Full technology stack |
| x_is_decision_maker | Boolean | Odoo App | Contact has buying authority |
| x_seniority | Selection | Odoo App | C-level / VP / Director / Manager |
| x_contact_score | Integer (0-100) | Odoo App | Contact quality score |
| x_intent_score | Integer (0-100) | Odoo App | Buying intent score |
| x_linkedin_url | Char (URL) | Odoo App | LinkedIn profile URL |
| + 9 more | | Odoo App | See data-enrichment-fields.csv for complete list |

### B. Custom Fields on User / Salesperson Profile:

| Field | Type | Set By | Purpose |
|-------|------|--------|---------|
| **x_calendar_link** | **Char (URL)** | **Manual** | **Salesperson's personal Calendly booking link (used in auto-ack and follow-up emails). Currently Calendly Free — future upgrade path: Cal.com (self-hosted, free, open source).** |

### C. Odoo Setup Tasks:

| Task | Who | Detail |
|------|-----|--------|
| Install Custom App | Odoo Team | Install the AI integration module. Configure Claude API key. |
| Create Marketing User | Odoo Team | User who receives junk/marketing leads. Filtered view. |
| Lead Assignment Rules | Odoo Team | Configure round-robin or territory rules. Native feature. |
| Follow-up Automation Rule | Odoo Team | On lead assignment: create 3 scheduled activities (Day 2/5/10). |
| Reply Detection | In-house Team | Custom `message_post` override on `crm.lead` — handles reply-aware timing reset + discussion sync to ticket. More reliable than `base_automation` for mail events. |
| Pipeline Stages | Odoo Team | New -> Qualified -> Meeting -> Tech Review -> Proposal -> Negotiation -> Won / Lost |
| Projects Module | Odoo Team | Configure for presale tickets. Add fields: Linked Lead, WBS Sheet URL, Status. |
| Calendar Sync | Odoo Team | Install `google_calendar` module. Enable Google Calendar API in same Google Cloud Project (used for Gmail OAuth + Gmail Add-on). Each rep clicks 'Sync with Google' in Odoo Calendar → OAuth consent → done. |
| **Rep Calendar Links** | **Sales Team** | **Each salesperson enters their calendar booking link in their Odoo profile (x_calendar_link field).** |
| Email Alias | Odoo Team | Set up sales@ alias creating leads in CRM. |
| **Email Gateway per Rep** | **Odoo Team** | **Install Odoo's `google_gmail` module. Configure Google Cloud Project with OAuth client ID. Each rep authorizes Odoo via OAuth consent flow (one-time). All incoming/outgoing through Odoo via OAuth 2.0.** |
| **Retro Automation Rule** | **In-house Team** | **On lead stage change to Won/Lost: trigger retro generation. Retro posted to linked presale ticket (not lead).** |
| **Presale Email Trigger** | **In-house Team** | **Custom `message_post` override on `project.task` + n8n callback. Triggers AI email drafting when discussions are posted to tickets.** |
| **ICP Scoring Criteria** | **Sales Team** | **Sales team fills out a structured ICP definition form (target industries, company size, seniority, tech stack, etc.). Claude uses this as the scoring rubric.** |
| **Stale Deal Thresholds** | **Sales Team + Odoo Team** | **Define days-in-stage thresholds per pipeline stage (e.g., Qualified: X days, Meeting: Y days). Configurable in Odoo settings.** |

---

## 20. Phase 2 Roadmap

Items noted for Phase 2 implementation. These are validated ideas that need further exploration before building.

### Phase 2 Item 1: AI Learning for WBS (Continuous Improvement)

| Aspect | Detail |
|--------|--------|
| **Concept** | AI generates WBS, pre-sale team manually modifies it. We maintain version history using Google Sheets revision history. Over time, Claude learns from the delta between AI output and human corrections. |
| **How it works** | 1. AI generates WBS in Google Sheet. 2. n8n names the Sheets revision as **"AI Generated"** via Sheets API. 3. Humans modify and finalize. The latest version is the human-modified one. 4. System can compare "AI Generated" revision vs latest to see what changed. 5. When generating future WBS, Claude receives examples of past AI-vs-human diffs as context. |
| **Technical approach** | Use **Google Sheets revision history** with named revisions. AI-generated version is named "AI Generated". Human modifications become the latest revision. n8n can pull both versions via Sheets API for comparison. When invoking the WBS Skill, include recent diffs as few-shot examples in the prompt. |
| **Goal** | Reduce human modifications over time. AI learns the team's preferences, estimation patterns, and common adjustments. |

### Phase 2 Item 2: WhatsApp for Odoo Management

| Aspect | Detail |
|--------|--------|
| **Concept** | Allow the sales team to use **WhatsApp** to interact with Odoo. View lead status, reply to customers, get notifications - all from WhatsApp. |
| **Use cases** | 1. Check lead status: "What's the status of lead #1234?" 2. Reply to customers: Forward a message to a bot that sends it as an email from Odoo. 3. Get notifications: New lead assigned, customer replied, etc. |
| **Platform** | **WhatsApp.** |
| **Status** | **Phase 2 - not in V1 scope.** Questions to resolve later: Security implications? WhatsApp Business API cost? Bot framework? |
| **Technical options** | WhatsApp Business API (paid). Bot connects to Odoo via XML-RPC. n8n can bridge between WhatsApp and Odoo. |

---

## Next Steps

1. Review this document and confirm all decisions are captured correctly
2. In-house team: confirm custom fields and configuration feasibility in Community Edition
3. Set up rep Calendly links in Odoo profiles + configure `google_calendar` module for two-way sync
4. Configure Odoo email gateway: Install `google_gmail` module, set up Google Cloud OAuth, each rep authorizes via OAuth + sales@ alias
5. Build Gmail Workspace Add-on (Apps Script) — 7 phases per spec
6. Build `mail_smart_link` Odoo module — smart email routing
7. Train the WBS Skill with existing WBS template
8. Pre-sale team: confirm proposal templates on Google Drive are ready for Claude to read
9. Select the pilot team
10. Begin Odoo app development + n8n/Playwright setup + Gmail Add-on in parallel
