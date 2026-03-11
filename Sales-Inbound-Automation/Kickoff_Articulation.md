# Inbound Sales Automation - Kickoff Articulation

**For: Team Kickoff Meeting | March 2026**

---

## What Are We Building?

We are automating our inbound sales pipeline end-to-end using **Odoo 19 Community Edition** + a **custom Odoo app powered by Claude AI** + **Gmail Workspace Add-on** + **n8n for external integrations**.

The goal: every sales rep works inside Odoo for everything - lead management, emails, follow-ups, presale, proposals. AI handles the heavy lifting (drafting emails, scoring leads, generating MOMs, creating WBS, writing proposals). Humans review and send.

---

## The Big Picture

```
Lead comes in
    |
    v
AI filters junk --> Junk goes to Marketing User
    |
    v (genuine leads only)
AI enriches from Apollo (via Playwright) --> 30 fields filled
    |
    v
AI scores lead (0-100) using ICP criteria from sales team
    |
    v
Lead assigned to rep (Odoo round-robin)
    |
    v
AI sends personalized auto-ack email + rep's calendar link
    |
    v
AI creates follow-up schedule (Day 2/5/10, adjusted by score, weekends skipped)
    |
    v
AI drafts each follow-up email (fully AI-generated, appears in "My Activities")
    |
    v
Rep reviews draft --> edits if needed --> sends from Odoo
    |
    v
Client books meeting via calendar link
    |
    v
Meeting recorded on Apollo --> Playwright fetches transcript
    |
    v
AI generates Client MOM --> draft email for rep to review and send
    |
    v
Presale ticket created --> AI summarizes all prior discussions
    |
    v
Daily 10:30 AM agenda posted on each ticket (subscribers notified)
    |
    v
After presale meetings:
  - MOM logged to ticket (internal)
  - Draft client email created on lead (rep's "My Activities")
    |
    v
AI generates WBS --> Human validates --> Tech estimates --> "Ready for Proposal"
    |
    v
Rep clicks "Request Proposal from AI" --> n8n pulls template from Google Drive
--> Claude generates proposal --> writes back to Google Drive
    |
    v
Rep reviews proposal --> sends to client
    |
    v
Lead Won or Lost --> AI generates full retrospective on the ticket
```

---

## Four Layers of the System

### 1. Odoo Native (Free - Community Edition)
What Odoo already does out of the box. No development needed.

- CRM pipeline & stages
- Lead assignment (round-robin / territory)
- Email send / receive / track (Gmail OAuth 2.0 per rep via `google_gmail` module)
- Google Calendar two-way sync (`google_calendar` module) + Meeting-Lead Auto-Linker
- Presale tickets (Projects module)
- Activities ("My Activities" daily task view)
- Automation rules
- Dashboards & reports

### 2. Custom Odoo App (Built by In-House Team)
A single Odoo module that calls Claude AI. This is where our intelligence lives.

| Feature | What It Does |
|---------|-------------|
| Junk Filter | Classifies leads as genuine/marketing/junk |
| Enrichment | Structures Apollo data into 30 lead fields |
| Lead Scoring | Scores 0-100 based on sales team's ICP criteria |
| Auto-Ack Email | AI-generated first email tailored to client's inquiry + rep's calendar link |
| Follow-up Drafter | AI writes full follow-up emails (Day 2/5/10) |
| Reply Handler | Detects replies, classifies intent, resets follow-up cycle |
| Client MOM | Generates MOM from meeting transcript, creates draft for rep |
| Ticket Gist | Summarizes all discussions when presale ticket is created |
| Discussion Sync | Syncs discussions to ticket, strips financial data |
| Presale Agenda | Daily 10:30 AM agenda posted on each ticket |
| Presale Email Drafter | After presale meetings: MOM on ticket + draft client email on lead |
| Retro Generator | Full retrospective when lead is won/lost |
| Meeting-Lead Auto-Linker | Auto-links synced calendar meetings to CRM leads by matching attendee emails |
| `mail_smart_link` module | Auto-routes new customer emails to existing leads (prevents duplicates) |

### 3. Gmail Workspace Add-on (Apps Script)
Bridges Gmail and Odoo — gives reps Odoo context inside Gmail.

| Feature | What It Does |
|---------|-------------|
| Contextual Sidebar | Shows partner info + associated leads when opening any email in Gmail |
| Log Email to Lead | One-click logging of Gmail-sent emails to Odoo leads |
| Create Lead from Gmail | Create a new lead directly from an email in Gmail |
| Manual Lead Linking | Search and link any email to any lead |
| Duplicate Prevention | Three-layer dedup via RFC 2822 Message-ID |

### 4. n8n Workflows (External Integrations Only)
n8n handles what Odoo can't touch directly.

| Workflow | What It Does |
|---------|-------------|
| Apollo Recording Fetch | Playwright scrapes transcript from Apollo after meetings |
| Apollo Data Scraper | Playwright extracts conversations, enrichment data, prospects |
| Presale MOM Splitter | Splits presale meeting MOM by ticket # |
| WBS Generator | Generates WBS in Google Sheets from ticket data |
| Proposal Generator | Pulls template from Google Drive, Claude generates, writes back |
| Teams Notifications | Pushes alerts to Teams channels |
| Stale Deal Monitor | Daily check for stuck deals (stage-wise thresholds) |

---

## Key Decisions Already Made

| Decision | Answer |
|----------|--------|
| Odoo edition | **Community Edition only** (no Enterprise) |
| Who builds the app | **In-house team** |
| Apollo integration | **All via Playwright** (Apollo has no API) |
| Follow-up timing | **Day 2/5/10 standard**, optimized by lead score, weekends skipped |
| Follow-up content | **Fully AI-generated** (not templates) |
| Junk leads | **All go to Marketing User** (no auto-delete) |
| Financial data on tickets | **AI strips financial numbers** before syncing to ticket |
| Ticket # convention | **"Moving to ticket 12345"** verbal cue in presale meetings |
| WBS template | **Existing template** will be used |
| Proposal templates | **Google Drive**, owned by pre-sale team |
| Retro location | **Presale ticket** (fallback: lead if no ticket) |
| Calendar links | **Each rep's link in their Odoo profile** |
| Client MOM | **Always sent by the rep who attended the meeting** |
| Stale deal thresholds | **Configurable per pipeline stage** |
| Email centralization | **Gmail Add-on + `mail_smart_link` module** (no Enterprise needed) |
| Pilot | **One team first**, then scale |
| Appointment scheduling | **Calendly Free** (current), future: Cal.com self-hosted |

---

## AI Cost

| Model | Used For | Est. Monthly |
|-------|---------|-------------|
| Claude Haiku 4.5 | Junk filter, enrichment, scoring, reply classification, email matching | ~$10-18 |
| Claude Sonnet 4.6 | Auto-ack emails, follow-ups, MOMs, gists, presale emails, retros, discussion sync | ~$55-80 |
| Claude Opus 4.6 | Proposals only (highest quality needed) | ~$15-30 |
| **Total** | | **~$80-128/mo** |

---

## What Needs Research Before We Start

| Item | Why | Who |
|------|-----|-----|
| **Playwright + Apollo feasibility** | Build a proof-of-concept: can we reliably log in and extract data? How stable are selectors? | Dev Team |

---

## Phase 2 Items (Not in V1)

1. **AI Learning for WBS** - AI learns from human modifications over time (version history via Sheets revision naming)
2. **WhatsApp for Odoo** - Sales team manages leads via WhatsApp

---

## Next Steps After Kickoff

1. Dev team builds Playwright proof-of-concept for Apollo
2. Dev team starts Gmail Workspace Add-on development (7 phases per spec)
3. Odoo team builds `mail_smart_link` module for smart email routing
4. Sales team fills out ICP scoring criteria form
5. Sales team sets up Calendly links in Odoo profiles + configure `google_calendar` module
6. Pre-sale team confirms proposal templates on Google Drive
7. Define stale deal thresholds per pipeline stage
8. Select pilot team
9. Begin development: Odoo custom app + n8n workflows + Gmail Add-on in parallel
