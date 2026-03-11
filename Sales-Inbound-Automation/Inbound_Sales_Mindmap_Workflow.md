# Inbound Sales Strategy — Mindmap Workflow
## Every Action, Every Step, Every Claude Agent

**Stack:** Odoo 19 CE + Custom Claude App + Gmail Workspace Add-on + n8n
**Date:** March 2026

---

## MASTER FLOW OVERVIEW

```
LEAD ARRIVES
     │
     ▼
[1] JUNK FILTER ──── Junk/Spam ──────────────────► Marketing User (archived)
     │
     ▼ (Genuine lead only)
[2] DATA ENRICHMENT (Apollo via Playwright)
     │
     ▼
[3] LEAD SCORING (ICP 0–100)
     │
     ▼
[4] LEAD ASSIGNMENT (Round-robin / Territory)
     │
     ▼
[5] AUTO-ACKNOWLEDGMENT EMAIL sent to client
     │
     ▼
[6] FOLLOW-UP SEQUENCE SCHEDULED (Day 2 / 5 / 10)
     │
     ├──── Client Replies ──► [7] REPLY HANDLER ──► Reset cycle / Move stage
     │
     ├──── Client Books Meeting ──► [8] MEETING MANAGEMENT
     │                                    │
     │                              Meeting Happens
     │                                    │
     │                             [9] CLIENT MOM GENERATION
     │                                    │
     │                             [10] PRESALE TICKET CREATION
     │                                    │
     │                    ┌──────────────┤
     │                    │              │
     │              [11] DAILY          [12] PRESALE EMAIL DRAFTER
     │              AGENDA (10:30AM)    (Post each presale meeting)
     │                    │
     │              [13] WBS GENERATION
     │                    │
     │              [14] PROPOSAL GENERATION
     │                    │
     │              Client Decision
     │                 /       \
     │              WON        LOST
     │                 \       /
     │              [15] RETROSPECTIVE
     │
     └──── No Response after Day 10 ──► Stale Deal Alert ──► Manager Escalation
```

---

## DETAILED MINDMAP — NODE BY NODE

---

## [1] JUNK FILTER

```
TRIGGER: New lead created in Odoo (from email / web form)
     │
     ├─► [1.1] Extract lead data
     │         • Email address
     │         • Email subject & body
     │         • Company name (if present)
     │         • Source channel
     │
     ├─► [1.2] Claude classifies as:
     │         • GENUINE     → proceed to enrichment
     │         • MARKETING   → assign to Marketing User, tag "marketing-promo"
     │         • JUNK/SPAM   → assign to Marketing User, tag "junk"
     │         • JOB SEEKER  → assign to Marketing User, tag "job-inquiry"
     │
     └─► [1.3] Outcome logging
               • Log classification + confidence score on lead chatter
               • If GENUINE: trigger enrichment pipeline
               • If not GENUINE: stop all further automation
```

**Claude Agent:** `JunkFilterAgent`
**Model:** Haiku 4.5 (low cost, fast)
**Trigger:** Odoo automation rule on lead create
**Input:** Email subject, body, sender domain, company name
**Output:** `{classification: "genuine|marketing|junk|job_seeker", confidence: 0-100, reason: "..."}`

---

## [2] DATA ENRICHMENT

```
TRIGGER: Lead classified as GENUINE
     │
     ├─► [2.1] n8n: Playwright logs into Apollo
     │         • Searches company by name + domain
     │         • Extracts company profile
     │         • Extracts contact profile
     │         • Fetches conversation history (if any)
     │
     ├─► [2.2] Raw Apollo data sent to Claude
     │
     ├─► [2.3] Claude structures data into 30 Odoo fields:
     │         COMPANY FIELDS:
     │         • Industry, Sub-industry
     │         • Employee count (range)
     │         • Annual revenue (range)
     │         • HQ country, city
     │         • Founded year
     │         • Tech stack (from Apollo)
     │         • Funding stage
     │         • LinkedIn URL
     │         • Website
     │         CONTACT FIELDS:
     │         • Job title, Seniority level
     │         • Direct email (verified)
     │         • Direct phone
     │         • LinkedIn profile URL
     │         • Decision-making authority (yes/no)
     │         LEAD CONTEXT FIELDS:
     │         • Likely pain point (inferred)
     │         • Similar companies we've won
     │         • ICP match signals (list)
     │         • Enrichment confidence score
     │         • Data source + date
     │
     └─► [2.4] Odoo fields updated via API
               • Chatter note: "Enriched from Apollo on [date]"
               • Missing fields flagged for manual fill
```

**Claude Agent:** `EnrichmentStructurerAgent`
**Model:** Haiku 4.5
**Trigger:** n8n webhook after Apollo scrape completes
**Input:** Raw Apollo JSON dump
**Output:** Structured JSON matching 30 Odoo field names → written to lead record

---

## [3] LEAD SCORING

```
TRIGGER: Enrichment complete (or enrichment failed after 2 min timeout)
     │
     ├─► [3.1] Pull ICP criteria from Odoo config
     │         (Filled by sales team — stored as JSON config)
     │         • Target industries (weighted list)
     │         • Target employee count range
     │         • Target revenue range
     │         • Target geographies
     │         • Target job titles / seniority
     │         • Disqualifying signals (competitors, blacklisted domains)
     │
     ├─► [3.2] Pull lead enrichment fields
     │
     ├─► [3.3] Claude scores lead 0–100:
     │         SCORING BREAKDOWN:
     │         • Industry fit:          0–25 pts
     │         • Company size fit:      0–20 pts
     │         • Revenue fit:           0–15 pts
     │         • Contact seniority:     0–15 pts
     │         • Geography fit:         0–10 pts
     │         • Inquiry intent:        0–10 pts
     │         • Disqualifiers:         –20 pts max
     │
     ├─► [3.4] Write score to Odoo:
     │         • `lead_score` field updated
     │         • Score band tag applied:
     │           90–100 → "Hot 🔥"
     │           70–89  → "Warm"
     │           50–69  → "Neutral"
     │           <50    → "Cold"
     │         • Scoring rationale logged to chatter
     │
     └─► [3.5] Score gates:
               • Score ≥ 50 → proceed to assignment
               • Score < 50 → assign to rep but flag "Review before outreach"
               • Score < 20 → suggest disqualify (rep decision)
```

**Claude Agent:** `LeadScoringAgent`
**Model:** Haiku 4.5
**Trigger:** After enrichment write-back
**Input:** Enriched lead fields + ICP config JSON
**Output:** `{score: 0-100, band: "hot|warm|neutral|cold", breakdown: {...}, rationale: "..."}`

---

## [4] LEAD ASSIGNMENT

```
TRIGGER: Lead score calculated
     │
     ├─► [4.1] Odoo native round-robin rule fires
     │         (or territory/industry routing if configured)
     │
     ├─► [4.2] Rep assigned as lead owner
     │
     ├─► [4.3] Odoo activity created for rep:
     │         "New lead assigned — review and send auto-ack"
     │
     ├─► [4.4] Teams notification sent (n8n):
     │         "@RepName — New [Hot/Warm] lead: [Company] | Score: [X]"
     │
     └─► [4.5] Rep's calendar link fetched from Odoo profile
               (used in next step — auto-ack email)
```

**No Claude agent needed** — Odoo native automation + n8n Teams notification.

---

## [5] AUTO-ACKNOWLEDGMENT EMAIL

```
TRIGGER: Lead assigned to rep
     │
     ├─► [5.1] Pull context for email generation:
     │         • Client's original inquiry (email body)
     │         • Client name, company, role
     │         • Enriched pain point signals
     │         • Rep name, designation
     │         • Rep's calendar link (from profile)
     │         • Company intro / value prop (from config)
     │
     ├─► [5.2] Claude drafts personalized auto-ack:
     │         STRUCTURE:
     │         • Warm opening acknowledging their specific inquiry
     │         • 2–3 lines on how we address their pain
     │         • Soft social proof (1 line — industry or use case)
     │         • Calendar invite CTA (rep's link)
     │         • Rep signature
     │         RULES:
     │         • Max 150 words
     │         • No generic template feel
     │         • Must reference their actual ask
     │         • Never oversell / no hyperbole
     │
     ├─► [5.3] Draft created as Odoo email on lead
     │         • Status: "Draft — pending rep review"
     │         • Activity created: "Review & send auto-ack" (due: same day)
     │
     └─► [5.4] Rep reviews in "My Activities"
               • Edits if needed
               • Clicks Send → email goes from rep's Gmail via Odoo
               • Activity marked Done
               • Lead stage moves to "Contacted"
```

**Claude Agent:** `AutoAckDrafterAgent`
**Model:** Sonnet 4.6
**Trigger:** Lead assignment event
**Input:** Inquiry text, enriched fields, rep profile, ICP value prop config
**Output:** Full email draft (subject + body) → saved as Odoo mail.message draft

---

## [6] FOLLOW-UP SEQUENCE SCHEDULING

```
TRIGGER: Auto-ack sent (lead stage = "Contacted")
     │
     ├─► [6.1] Calculate follow-up schedule:
     │         BASE SCHEDULE:
     │         • Follow-up 1: Day 2 after ack sent
     │         • Follow-up 2: Day 5 after ack sent
     │         • Follow-up 3: Day 10 after ack sent
     │         ADJUSTMENTS:
     │         • Hot lead (≥90): Day 1 / Day 3 / Day 7
     │         • Cold lead (<50): Day 3 / Day 7 / Day 14
     │         • Weekends skipped (roll to Monday)
     │         • Public holidays skipped (from config)
     │
     ├─► [6.2] 3 Odoo activities scheduled on the lead
     │         Each: "Send follow-up email [1/2/3]"
     │         Each activity linked to a draft that will be created on due date
     │
     └─► [6.3] Follow-up drafts created by Claude on each due date:
```

### [6.3] FOLLOW-UP EMAIL DRAFTER (runs on each due date)

```
     │
     ├─► Pull full context:
     │   • Original inquiry
     │   • Auto-ack sent (content + date)
     │   • Prior follow-ups sent (content + dates)
     │   • Lead score + enrichment data
     │   • Any chatter notes from rep
     │   • Which follow-up number this is (1, 2, or 3)
     │
     ├─► Claude generates follow-up:
     │   FOLLOW-UP 1 (Day 2):
     │   • Gentle check-in
     │   • Add one new value angle not in ack
     │   • Keep it short (under 100 words)
     │
     │   FOLLOW-UP 2 (Day 5):
     │   • More specific — reference their industry or company
     │   • One concrete case study or stat
     │   • Ask a specific question to prompt reply
     │
     │   FOLLOW-UP 3 (Day 10):
     │   • "Final nudge" tone — respectful, not pushy
     │   • Different CTA (e.g. "even 15 min would help")
     │   • Leave door open
     │
     └─► Draft saved on lead → activity "Review & send follow-up [X]" created
```

**Claude Agent:** `FollowUpDrafterAgent`
**Model:** Sonnet 4.6
**Trigger:** Scheduled Odoo job per follow-up activity due date
**Input:** Full lead thread history, enrichment, follow-up number, prior emails
**Output:** Email subject + body → saved as Odoo draft + activity reminder

---

## [7] REPLY HANDLER

```
TRIGGER: Inbound email received on a lead with active follow-up sequence
     │
     ├─► [7.1] Claude classifies reply intent:
     │         • INTERESTED        → reset sequence, move stage to "Engaged"
     │         • MEETING_BOOKED    → cancel remaining follow-ups, move to "Meeting Scheduled"
     │         • NOT_INTERESTED    → mark "Disqualified", log reason, stop sequence
     │         • WRONG_PERSON      → create task "Find correct contact at [Company]"
     │         • OOO               → extract return date, reschedule follow-ups
     │         • REFERRAL          → create note "Referred by [Name] to [New Contact]"
     │         • GENERIC_POSITIVE  → reset cycle, create activity "Reply with value add"
     │         • UNSUBSCRIBE       → stop all sequences, tag "Unsubscribed"
     │
     ├─► [7.2] Actions based on classification:
     │         INTERESTED / MEETING_BOOKED:
     │         • Cancel pending follow-up activities
     │         • Move lead stage
     │         • Notify rep via activity + Teams
     │         OOO:
     │         • Pause sequence until return date
     │         • Resume sequence automatically on return date
     │         NOT_INTERESTED:
     │         • Move to "Lost" (reason: "Not Interested")
     │         • Stop all sequences
     │
     └─► [7.3] Rep notified in all cases:
               • Activity: "Reply received from [Company] — classified as [X]"
               • Chatter: Classification + confidence + original reply text
```

**Claude Agent:** `ReplyClassifierAgent`
**Model:** Haiku 4.5
**Trigger:** `mail_smart_link` module routes incoming email → webhook
**Input:** Reply email body, sender, lead context
**Output:** `{intent: "...", confidence: 0-100, action: "...", ooo_return_date: "..."}`

---

## [8] MEETING MANAGEMENT

```
TRIGGER: Client books via rep's Calendly / Cal.com link
     │
     ├─► [8.1] Calendly webhook → n8n → Odoo:
     │         • Meeting created in Odoo calendar
     │         • Linked to lead via Meeting-Lead Auto-Linker
     │         (matches attendee emails to existing leads)
     │
     ├─► [8.2] Lead stage → "Meeting Scheduled"
     │
     ├─► [8.3] Auto-reminders sent (Odoo native):
     │         • 24h before: "Looking forward to our call tomorrow"
     │         • 1h before: "See you in 1 hour — here's the link"
     │
     ├─► [8.4] Pre-meeting prep (optional, Phase 2):
     │         Claude drafts "meeting prep brief" for rep:
     │         • Company snapshot (from enrichment)
     │         • Likely objections based on industry
     │         • Suggested talking points
     │         • Prior email context summary
     │
     ├─► [8.5] Meeting happens on Apollo (recorded)
     │
     ├─► [8.6] Post-meeting — No-show handling:
     │         If rep marks "No Show":
     │         • Claude drafts no-show follow-up email
     │         • Activity: "Review & send no-show follow-up"
     │         • Lead stage → "Follow-up Needed"
     │
     └─► [8.7] Lead stage → "Meeting Done"
               Triggers → [9] CLIENT MOM GENERATION
```

**Claude Agents needed:**
- `MeetingPrepBriefAgent` (Phase 2) — Sonnet 4.6
- `NoShowFollowUpAgent` — Sonnet 4.6

---

## [9] CLIENT MOM GENERATION

```
TRIGGER: Meeting done + transcript available in Apollo
     │
     ├─► [9.1] n8n: Playwright fetches transcript from Apollo
     │         • Logs in to Apollo
     │         • Navigates to meeting recording
     │         • Extracts full transcript text
     │         • Returns to n8n webhook
     │
     ├─► [9.2] Claude generates Client MOM:
     │         STRUCTURE:
     │         • Meeting date, attendees
     │         • Client's key pain points discussed
     │         • Our proposed solution / what we showcased
     │         • Client's questions + our responses
     │         • Next steps agreed (numbered list)
     │         • Client's timeline + urgency signals
     │         • Action items: [Rep] vs [Client]
     │         RULES:
     │         • Professional but warm tone
     │         • Max 400 words
     │         • No financial figures in MOM
     │         • Bullet points, not paragraphs
     │
     ├─► [9.3] MOM logged internally to lead chatter
     │         (internal note — client cannot see)
     │
     ├─► [9.4] Draft client email created on lead:
     │         Subject: "Summary of our call — [Date]"
     │         Body: Client-facing MOM (slightly warmer tone)
     │         + Next steps clearly stated
     │         + Calendar link for next meeting (if applicable)
     │
     ├─► [9.5] Activity created for rep:
     │         "Review & send meeting MOM to [Company]"
     │         Due: same day
     │         Assigned: rep who attended the meeting
     │
     └─► [9.6] Rep reviews, edits, sends
               Lead stage → "MOM Sent"
```

**Claude Agent:** `ClientMOMAgent`
**Model:** Sonnet 4.6
**Trigger:** n8n webhook after transcript fetched
**Input:** Full meeting transcript, lead enrichment data, attendee list
**Output:** `{internal_mom: "...", client_email_subject: "...", client_email_body: "..."}`

---

## [10] PRESALE TICKET CREATION

```
TRIGGER: Rep manually creates presale ticket (or automation rule after MOM sent)
     │
     ├─► [10.1] Ticket created in Odoo Projects
     │          • Ticket # assigned (e.g., PST-1042)
     │          • Linked to CRM lead
     │          • Presale team members added as subscribers
     │
     ├─► [10.2] Claude generates "Ticket Gist":
     │          PULLS FROM:
     │          • All emails on the lead (thread history)
     │          • All internal notes on the lead
     │          • Meeting MOM(s)
     │          • Enrichment data
     │          • Lead score + ICP signals
     │          GIST STRUCTURE:
     │          • Client overview (company, size, industry)
     │          • What they're looking for (1 paragraph)
     │          • Key requirements identified so far
     │          • Open questions that need answering
     │          • Budget signals (if any — from conversation, not stated)
     │          • Timeline signals
     │          • Risk flags (if any)
     │          • Recommended presale approach
     │
     ├─► [10.3] Gist posted as first internal note on ticket
     │
     ├─► [10.4] Subscribers notified:
     │          "New presale ticket PST-1042 created for [Company]
     │           — Gist attached. Please review before daily agenda."
     │
     └─► [10.5] Financial data filtering:
               If any emails contain financial figures:
               Claude strips $ amounts before syncing to ticket
               (original retained on lead only)
```

**Claude Agent:** `TicketGistAgent`
**Model:** Sonnet 4.6
**Trigger:** Presale ticket creation event
**Input:** Full lead chatter history, all emails, MOMs, enrichment data
**Output:** Structured gist markdown → posted as ticket internal note

---

## [11] DAILY PRESALE AGENDA (10:30 AM)

```
TRIGGER: Daily cron job at 10:00 AM (posts by 10:30 AM)
     │
     ├─► [11.1] Identify all active presale tickets
     │          (Status: not "Won", "Lost", "Cancelled")
     │
     ├─► [11.2] For each ticket, Claude generates today's agenda:
     │          AGENDA STRUCTURE:
     │          • Status since last meeting
     │          • Today's meeting topic / goal
     │          • Open items from last MOM
     │          • Questions to resolve today
     │          • Documents needed
     │          • Decision needed from client (if any)
     │          RULES:
     │          • Pulled from ticket chatter (last 7 days)
     │          • Max 200 words per ticket
     │          • Action-oriented bullet points
     │
     ├─► [11.3] Agenda posted as internal note on each ticket
     │
     └─► [11.4] All ticket subscribers notified via Odoo
                (Appears in their inbox / email digest)
```

**Claude Agent:** `DailyAgendaAgent`
**Model:** Haiku 4.5 (simple, repetitive, high volume)
**Trigger:** Odoo scheduled action — daily 10:00 AM
**Input:** Ticket chatter last 7 days, open action items list
**Output:** Agenda markdown → posted to each active ticket

---

## [12] PRESALE EMAIL DRAFTER (Post-Presale Meetings)

```
TRIGGER: Rep marks presale meeting as "Done" in Odoo
         (or n8n detects transcript available for ticket-linked meeting)
     │
     ├─► [12.1] n8n fetches presale meeting transcript from Apollo
     │
     ├─► [12.2] n8n identifies ticket # from transcript
     │          (Rep says "Moving to ticket 1042" during call)
     │          Regex match → routes MOM to correct ticket
     │
     ├─► [12.3] Claude generates Presale MOM (internal):
     │          • Technical requirements discussed
     │          • Architecture decisions
     │          • Open technical questions
     │          • Clarifications needed from client
     │          • Action items: [Presale team] vs [Client]
     │          NOTE: Financial figures stripped automatically
     │
     ├─► [12.4] Internal MOM posted to presale ticket chatter
     │
     ├─► [12.5] Claude drafts client-facing email:
     │          • Summary of what was covered
     │          • Next steps for client
     │          • Documents/info requested from client
     │          • Proposed next meeting time / CTA
     │
     └─► [12.6] Draft email created on the CRM lead
                Activity: "Review & send presale update to [Company]"
                Assigned: rep who attended the presale call
```

**Claude Agents:**
- `PresaleMOMAgent` — Sonnet 4.6 (internal MOM generation)
- `PresaleEmailDrafterAgent` — Sonnet 4.6 (client email draft)
**Trigger:** Presale meeting transcript available + ticket # identified

---

## [13] WBS GENERATION

```
TRIGGER: Presale team clicks "Generate WBS" on presale ticket
     │
     ├─► [13.1] n8n pulls context from Odoo:
     │          • All presale ticket notes and MOMs
     │          • Requirements gathered
     │          • Tech stack + architecture decisions
     │          • Client's existing systems (from enrichment + presale)
     │
     ├─► [13.2] n8n opens WBS template from Google Sheets
     │          (Company's existing WBS template structure)
     │
     ├─► [13.3] Claude populates WBS:
     │          STRUCTURE (follows existing template):
     │          • Phase 1: Discovery & Setup
     │          • Phase 2: Core Development (modules/features)
     │          • Phase 3: Integration & Testing
     │          • Phase 4: UAT & Go-Live
     │          • Phase 5: Hypercare & Support
     │          FOR EACH TASK:
     │          • Task name
     │          • Description
     │          • Dependencies
     │          • Estimated effort (placeholder — "X days")
     │          • Owner: [Dev / QA / PM / Client]
     │
     ├─► [13.4] WBS written back to Google Sheets (new tab per ticket)
     │          via n8n → Google Sheets API
     │
     ├─► [13.5] Presale team reviews WBS:
     │          • Validates tasks / scope
     │          • Adds/removes items
     │          • Sends to tech team for effort estimation
     │
     ├─► [13.6] Tech team fills in actual day estimates
     │
     └─► [13.7] Presale ticket stage → "Ready for Proposal"
```

**Claude Agent:** `WBSGeneratorAgent`
**Model:** Sonnet 4.6 (complex structured generation)
**Trigger:** Button click on presale ticket
**Input:** All presale discussion context + requirements list + WBS template structure
**Output:** Populated WBS JSON → written to Google Sheets via n8n

---

## [14] PROPOSAL GENERATION

```
TRIGGER: Rep clicks "Request Proposal from AI" on presale ticket
         (available only when stage = "Ready for Proposal")
     │
     ├─► [14.1] n8n pulls proposal template from Google Drive
     │          (pre-sale team's master template, by project type)
     │
     ├─► [14.2] n8n collects all context:
     │          • Client info (from enrichment)
     │          • Requirements (from presale MOMs)
     │          • WBS (from Google Sheets)
     │          • Tech estimates (from WBS)
     │          • Pricing (from internal config / manual input)
     │          • Rep's relationship notes (from chatter)
     │
     ├─► [14.3] Claude generates proposal:
     │          SECTIONS (follows template):
     │          1. Executive Summary
     │          2. Understanding of Your Requirements
     │          3. Our Proposed Solution
     │          4. Implementation Approach
     │          5. Team & Expertise
     │          6. Timeline (from WBS)
     │          7. Investment (pricing — filled from config)
     │          8. Why [Our Company]
     │          9. Next Steps
     │          RULES:
     │          • Client's language reflected back
     │          • Pain points from MOM woven in
     │          • No generic boilerplate sentences
     │          • Professional but not stiff tone
     │          • Opus 4.6 for highest quality
     │
     ├─► [14.4] Proposal written to Google Drive (new doc, named by ticket #)
     │
     ├─► [14.5] Presale ticket updated:
     │          • "Proposal Draft Ready" stage
     │          • Link to Google Doc added to ticket
     │          • Activity: "Review proposal draft" created for rep
     │
     └─► [14.6] Rep reviews → edits → shares with client as PDF
                Lead stage → "Proposal Sent"
```

**Claude Agent:** `ProposalGeneratorAgent`
**Model:** Opus 4.6 (highest quality — used only here)
**Trigger:** Button click on presale ticket (stage-gated)
**Input:** Template structure, all presale context, WBS, pricing
**Output:** Full proposal document → written to Google Drive via n8n

---

## [15] LEAD CLOSURE RETROSPECTIVE

```
TRIGGER: Lead marked "Won" or "Lost" in Odoo CRM
     │
     ├─► [15.1] Claude pulls full lead history:
     │          • All emails (thread)
     │          • All activities completed
     │          • Lead score + ICP match
     │          • Time at each pipeline stage
     │          • Presale ticket notes
     │          • Proposal details
     │          • Win/loss reason (entered by rep)
     │
     ├─► [15.2] Claude generates retrospective:
     │          IF WON:
     │          • Why we won (based on signals in conversations)
     │          • Key turning points in the deal
     │          • What worked well (approach, messaging, timing)
     │          • Client's primary decision driver
     │          • Deal velocity (days from lead to close)
     │          • What to replicate for similar leads
     │
     │          IF LOST:
     │          • Likely reason we lost (from context signals)
     │          • What could have been done differently
     │          • Competitor mentioned (if any)
     │          • Price sensitivity signals (if any)
     │          • Stage where deal stalled the longest
     │          • Red flags that appeared early
     │
     ├─► [15.3] Retrospective posted to:
     │          • Presale ticket (primary location)
     │          • Lead chatter (if no presale ticket)
     │
     └─► [15.4] Manager digest:
               n8n sends Teams notification to Sales Head:
               "[Won/Lost] [Company] — [Deal Value] | [Rep] | Retro ready on ticket PST-XXXX"
```

**Claude Agent:** `RetrospectiveAgent`
**Model:** Sonnet 4.6
**Trigger:** Lead stage changed to "Won" or "Lost"
**Input:** Complete lead history, emails, presale notes, win/loss reason
**Output:** Structured retrospective markdown → posted to ticket/lead

---

## PARALLEL SYSTEM: STALE DEAL MONITOR

```
TRIGGER: Daily cron — runs at 8:00 AM
     │
     ├─► Check all active leads against stage-wise thresholds:
     │   • "New / Uncontacted" > 1 day    → Alert rep
     │   • "Contacted" > 5 days no reply  → Suggest follow-up escalation
     │   • "Meeting Scheduled" > 2 days   → Check if meeting happened
     │   • "MOM Sent" > 3 days no response → Draft re-engagement nudge
     │   • "Proposal Sent" > 7 days       → Draft follow-up on proposal
     │
     ├─► Rep-level alerts (Odoo activity created)
     │
     └─► Manager escalation (Teams) if:
         • Deal stuck > 2x threshold
         • Hot lead (score ≥ 90) stuck at any stage > threshold
```

**No Claude agent needed** — Odoo automation rules + n8n Teams notification.
*(Claude optional in Phase 2 for drafting re-engagement emails)*

---

## PARALLEL SYSTEM: EMAIL CENTRALIZATION

```
INCOMING EMAIL (any rep's Gmail)
     │
     ├─► mail_smart_link module:
     │   • Matches email sender to existing leads (by email domain + address)
     │   • Auto-routes to correct lead chatter
     │   • Prevents duplicate leads
     │
     ├─► Gmail Workspace Add-on (sidebar):
     │   • Rep opens Gmail
     │   • Sidebar shows: partner info + linked lead + recent activity
     │   • Rep can: log email to lead, create lead, link to existing lead
     │
     └─► Three-layer dedup:
         1. RFC 2822 Message-ID matching
         2. Sender email → lead email match
         3. Sender domain → company match
```

**No Claude agent needed** — Custom Odoo module + Apps Script.

---

## COMPLETE CLAUDE AGENTS SUMMARY

| # | Agent Name | Model | Trigger | Core Job | Priority |
|---|-----------|-------|---------|----------|----------|
| 1 | `JunkFilterAgent` | Haiku 4.5 | New lead created | Classify: genuine / marketing / junk / job-seeker | **Critical — Phase 1** |
| 2 | `EnrichmentStructurerAgent` | Haiku 4.5 | Apollo scrape done | Structure raw Apollo data → 30 Odoo fields | **Critical — Phase 1** |
| 3 | `LeadScoringAgent` | Haiku 4.5 | Enrichment complete | Score lead 0–100 against ICP criteria | **Critical — Phase 1** |
| 4 | `AutoAckDrafterAgent` | Sonnet 4.6 | Lead assigned | Draft personalized acknowledgment email | **Critical — Phase 1** |
| 5 | `FollowUpDrafterAgent` | Sonnet 4.6 | Scheduled due date | Draft Day 2/5/10 follow-up emails | **Critical — Phase 1** |
| 6 | `ReplyClassifierAgent` | Haiku 4.5 | Inbound reply received | Classify reply intent + trigger action | **Critical — Phase 1** |
| 7 | `ClientMOMAgent` | Sonnet 4.6 | Meeting transcript available | Generate client MOM + draft email | **High — Phase 1** |
| 8 | `TicketGistAgent` | Sonnet 4.6 | Presale ticket created | Summarize full lead context for presale team | **High — Phase 2** |
| 9 | `DailyAgendaAgent` | Haiku 4.5 | Daily 10:00 AM cron | Generate today's agenda for each active ticket | **High — Phase 2** |
| 10 | `PresaleMOMAgent` | Sonnet 4.6 | Presale meeting transcript | Generate internal presale MOM | **High — Phase 2** |
| 11 | `PresaleEmailDrafterAgent` | Sonnet 4.6 | After presale MOM | Draft client-facing presale update email | **High — Phase 2** |
| 12 | `WBSGeneratorAgent` | Sonnet 4.6 | Button click on ticket | Generate full WBS in Google Sheets | **Medium — Phase 2** |
| 13 | `ProposalGeneratorAgent` | Opus 4.6 | Button click (stage-gated) | Generate full sales proposal from template | **Medium — Phase 3** |
| 14 | `RetrospectiveAgent` | Sonnet 4.6 | Lead won/lost | Full deal retrospective (won analysis or loss analysis) | **Medium — Phase 2** |
| 15 | `MeetingPrepBriefAgent` | Sonnet 4.6 | 2h before meeting | Draft pre-meeting brief for rep | **Low — Phase 3** |
| 16 | `NoShowFollowUpAgent` | Sonnet 4.6 | Rep marks no-show | Draft no-show follow-up email | **Low — Phase 2** |

---

## AGENT IMPLEMENTATION ARCHITECTURE

```
All agents share one base pattern:

[Odoo Event / n8n Trigger]
         │
         ▼
[Context Builder]  ←── pulls: lead fields, chatter, emails, config
         │
         ▼
[System Prompt]    ←── agent-specific persona + rules + output format
         │
         ▼
[Claude API Call]  ←── model selected per agent (Haiku / Sonnet / Opus)
         │
         ▼
[Output Parser]    ←── validates JSON / markdown structure
         │
         ▼
[Odoo Write-back]  ←── updates fields, creates email draft, posts note
         │
         ▼
[Activity Creator] ←── creates rep activity if human review needed
```

### Shared Agent Utilities (build once, use across all agents):
- **ContextBuilder** — pulls lead + chatter + enrichment data from Odoo ORM
- **PromptLibrary** — centralized system prompts per agent (version controlled)
- **OutputParser** — validates structured outputs (JSON schema validation)
- **OdooWriter** — writes back to fields, chatter, creates drafts, creates activities
- **TokenOptimizer** — trims context to model limits, prioritizes recent + relevant
- **AuditLogger** — logs every AI call: agent, model, tokens, output, timestamp

---

## BUILD SEQUENCE (Recommended)

```
PHASE 1 — Core Pipeline (Build First)
──────────────────────────────────────
Week 1–2:  Shared utilities (ContextBuilder, OdooWriter, AuditLogger)
Week 2–3:  JunkFilterAgent + LeadScoringAgent + EnrichmentStructurerAgent
Week 3–4:  AutoAckDrafterAgent + ReplyClassifierAgent
Week 4–5:  FollowUpDrafterAgent + Schedule engine
Week 5:    ClientMOMAgent
Week 5–6:  Gmail Workspace Add-on
Week 6:    mail_smart_link module
Week 6:    Apollo Playwright proof-of-concept

PHASE 2 — Presale Intelligence
──────────────────────────────
Week 7–8:  TicketGistAgent + DailyAgendaAgent
Week 8–9:  PresaleMOMAgent + PresaleEmailDrafterAgent
Week 9:    RetrospectiveAgent + NoShowFollowUpAgent
Week 10:   WBSGeneratorAgent (n8n + Google Sheets)

PHASE 3 — Advanced
────────────────────
Week 11–12: ProposalGeneratorAgent (n8n + Google Drive)
Week 13:    MeetingPrepBriefAgent
Week 13:    Stale Deal Monitor refinements
Week 14:    Dashboards + Rep Performance Reports
```

---

*Generated: March 2026 | Stack: Odoo 19 CE + Claude API + n8n + Gmail Add-on*
