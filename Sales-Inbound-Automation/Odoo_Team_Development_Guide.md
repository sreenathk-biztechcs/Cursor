# Odoo Team - Development Guide

**Inbound Sales Automation | Odoo 19 CE + Custom App + Claude AI**

This document is the step-by-step guide for the in-house Odoo development team. It covers what to build, in what order, what R&D to do first, and how to use Claude Code for development.

---

## Before You Start: R&D Items (Do These First)

One unknown needs answers before full development begins. Start this immediately so it doesn't block later work.

### R&D 1: Playwright + Apollo Proof of Concept

**Why:** Apollo has no API. ALL Apollo data access (recordings, conversations, enrichment) is via Playwright browser automation. We need to verify this works reliably.

**Who:** This can be done by the dev team (not Odoo-specific). Run in parallel with Odoo R&D.

**What to build:**
- Playwright script that logs into Apollo
- Extracts a meeting recording/transcript
- Extracts contact/company enrichment data
- Extracts conversation threads

**How to start (give this to Claude Code):**
```
Build a Playwright proof-of-concept for Apollo.io:
1. Create a Node.js or Python script using Playwright
2. Log into Apollo using credentials (handle 2FA if needed)
3. Navigate to a specific meeting recording and extract the transcript
4. Navigate to a contact page and extract enrichment data (company, employee count, tech stack, etc.)
5. Navigate to conversations and extract message threads
6. Output extracted data as JSON
7. Handle session management - store and reuse cookies to minimize logins
8. Add human-like delays between actions to avoid detection

This is a proof-of-concept to verify feasibility. Keep it simple.
```

---

## Development Order (Step by Step)

Build in this order. Each phase builds on the previous one.

### Phase A: Foundation (Week 1-2)

#### A1. Create the Custom Odoo Module Skeleton

**Give this to Claude Code:**
```
Create an Odoo 19 Community Edition custom module called "sales_ai_integration" with:

Module structure:
- __manifest__.py (depends on: crm, project, base_automation, mail, contacts)
- models/ directory
- wizards/ directory
- views/ directory
- data/ directory (for automation rules and scheduled actions)
- security/ directory (ir.model.access.csv)

The module should:
1. Add custom fields to crm.lead:
   - x_lead_quality (Selection: genuine/marketing/junk)
   - x_lead_score (Integer 0-100)
   - x_followup_stage (Integer)
   - x_last_reply_date (Datetime)
   - x_reply_intent (Selection: interested/not_interested/ooo/referral)
   - x_is_it_company (Boolean)
   - x_employee_count (Integer)
   - x_annual_revenue (Monetary)
   - x_tech_stack (Text)
   - x_is_decision_maker (Boolean)
   - x_seniority (Selection: c_level/vp/director/manager/other)
   - x_contact_score (Integer 0-100)
   - x_intent_score (Integer 0-100)
   - x_linkedin_url (Char)

2. Add custom field to res.users:
   - x_calendar_link (Char - URL for calendar booking)

3. Add custom fields to project.task (presale tickets):
   - x_linked_lead_id (Many2one to crm.lead)
   - x_wbs_sheet_url (Char)
   - x_ticket_status (Selection: open/ready_for_wbs/wbs_done/ready_for_proposal/proposal_sent/closed)

4. Create a settings model for the module:
   - Claude API key (stored securely)
   - ICP scoring criteria (Text field for JSON configuration)
   - Stale deal thresholds per stage (configurable)

5. Add a helper class for calling Claude API using the Anthropic Python SDK.
   - Method: call_claude(model, system_prompt, user_message) -> response text
   - Support for Haiku, Sonnet, and Opus models
   - Error handling and retry logic

Create all files with proper Odoo 19 conventions. Include security access rules.
```

---

#### A2. Pipeline Stages Configuration

**Give this to Claude Code:**
```
In the sales_ai_integration Odoo module, create a data file that sets up CRM pipeline stages:

Stages (in order):
1. New
2. Qualified
3. Meeting
4. Tech Review
5. Proposal
6. Negotiation
7. Won (is_won = True)
8. Lost

Use data/crm_stages.xml with noupdate="1".
```

---

### Phase B: Lead Intake & Qualification (Week 2-3)

#### B1. Junk / Marketing Filter

**Give this to Claude Code:**
```
In the sales_ai_integration Odoo module, implement the junk lead filter:

1. Create an automated action (base_automation) that triggers on lead creation.

2. The action calls a server action that:
   a. Gets the lead data: email_from, name, description, source
   b. Calls Claude Haiku 4.5 with this prompt:
      "Classify this lead as GENUINE, MARKETING, or JUNK based on the email, subject, and body.
       Return only one word: GENUINE, MARKETING, or JUNK."
   c. Sets x_lead_quality field based on response
   d. If MARKETING or JUNK: reassigns the lead to the Marketing User (configurable in settings)

3. Create an automation rule data file: data/automation_junk_filter.xml

Make sure:
- All junk/marketing leads go to Marketing User (never auto-deleted)
- Marketing User should be configurable in the module settings
- If Claude API call fails, default to 'genuine' (don't block the pipeline)
```

---

#### B2. Data Enrichment

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement data enrichment:

1. This runs AFTER the junk filter passes (x_lead_quality = 'genuine').

2. The flow:
   a. Lead is marked genuine
   b. Module sends a webhook/signal to n8n to trigger Apollo data scraping for this contact
   c. n8n uses Playwright to scrape Apollo for company/contact data
   d. n8n calls back to Odoo with raw Apollo data (via Odoo JSON-RPC API)
   e. Module receives raw data, calls Claude Haiku 4.5 to structure it
   f. Claude returns structured JSON matching our 30 custom fields
   g. Module writes the structured data to the lead's custom fields

3. Claude prompt should be:
   "Given this raw company and contact data from Apollo, extract and structure the following fields as JSON:
    [list all 30 fields with expected types]
    If a field cannot be determined, set it to null."

4. Create an endpoint or method that n8n can call to deliver Apollo data back to Odoo.

Handle cases where Apollo data is incomplete - fill what's available, leave rest as null.
```

---

#### B3. Lead Scoring

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement lead scoring:

1. Runs after enrichment completes (all custom fields populated).

2. The ICP criteria is stored in module settings as a JSON/text field.
   Sales team fills this out. Example format:
   {
     "ideal_industries": ["SaaS", "Fintech", "Healthcare"],
     "min_employee_count": 50,
     "preferred_seniority": ["c_level", "vp", "director"],
     "preferred_tech_stack": ["Python", "React", "AWS"],
     "min_revenue": 1000000,
     "decision_maker_bonus": 20,
     "it_company_bonus": 15
   }

3. Call Claude Haiku 4.5 with:
   - The enriched lead data
   - The ICP criteria from settings
   - Prompt: "Score this lead 0-100 based on how well it matches the ICP criteria.
     Return JSON: {score: number, qualification: 'hot'|'warm'|'cold', reasoning: string}"

4. Set x_lead_score, and log the reasoning to the lead chatter.

5. Create a view in the module settings where the sales team can edit the ICP criteria.
   Keep it simple - a text area where they paste/edit JSON, with a description of the format.
```

---

### Phase C: Auto-Ack & Follow-up System (Week 3-4)

#### C1. Auto-Acknowledgment Email

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement the auto-ack email:

1. Automation rule: triggers on lead assignment (user_id field changes from empty to a user).

2. The action:
   a. Gets the lead data (what the client asked about, their industry, etc.)
   b. Gets the assigned rep's calendar link from res.users.x_calendar_link
   c. Calls Claude Sonnet 4.6 with prompt:
      "Write a personalized acknowledgment email to this lead.
       The client inquired about: [lead description/subject].
       Our company expertise relevant to their inquiry: [from enrichment data].
       Tone: professional, confident, welcoming.
       Position us as experts in what they're asking about.
       End with a call to action to book a meeting using this link: [calendar_link].
       Keep it concise - 4-6 sentences max.
       Return JSON: {subject: string, body_html: string}"
   d. Creates and sends the email from Odoo using the lead's assigned rep as sender
   e. Tracks opens/replies via Odoo mail gateway

Make sure the email comes FROM the assigned rep (not a generic address).
```

---

#### C1b. Meeting-Lead Auto-Linker

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement the Meeting-Lead Auto-Linker:

1. Create an automated action that triggers on calendar.event creation or write (when google_calendar syncs a meeting).

2. The action:
   a. Extract attendee email addresses from the calendar event
   b. Search res.partner for matching emails
   c. If partner found → search crm.lead for active leads with that partner
   d. If exactly one active lead → link meeting to that lead (set opportunity_id on the calendar event)
   e. If multiple active leads → link to most recent active lead (highest id)
   f. If no lead found → no action (just a regular meeting)

3. This enables:
   - Meeting appears on the lead's record (visible in chatter)
   - Post-meeting triggers become possible (e.g., "meeting completed → create follow-up activity")
   - Reps see lead context directly on calendar events

No AI needed for this — pure Odoo logic.
```

---

#### C2. Follow-up Activity Scheduling

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement follow-up scheduling:

1. Same automation rule as auto-ack (on lead assignment) also creates follow-up activities.

2. Determine follow-up days based on lead score:
   - Hot (score > 80): Day 1, Day 3, Day 7
   - Warm (score 40-80): Day 2, Day 5, Day 10
   - Cold (score < 40): Day 3, Day 7, Day 14

3. Weekend handling: If a follow-up date falls on Saturday, move to Monday.
   If Sunday, move to Monday. Use Python's weekday() method.

4. Create 3 mail.activity records on the lead:
   - Activity type: "Follow-up Email" (create a custom activity type)
   - Date: calculated business day
   - User: lead owner
   - x_followup_stage: 1, 2, or 3
   - Note: will be filled by AI drafter later

5. Set x_followup_stage = 1 on the lead.
```

---

#### C3. AI Follow-up Email Drafter (9 AM Daily)

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement the follow-up email drafter:

1. Scheduled action (ir.cron) that runs daily at 9:00 AM.

2. The action:
   a. Find all follow-up activities due today or tomorrow that don't have a draft yet
   b. For each activity:
      - Get the lead data, enrichment fields, lead score
      - Get the follow-up number (1st, 2nd, or 3rd from x_followup_stage)
      - Get all previous emails sent on this lead (subjects and snippets)
      - Get any replies received
      - Get the rep's calendar link
      - Determine tone: 1st = warm/helpful, 2nd = value-adding, 3rd = direct/final

   c. Call Claude Sonnet 4.6 with:
      "Write a follow-up email for this lead.
       Follow-up #: [1/2/3]
       Tone guidance: [warm/value-adding/direct]
       Lead info: [enrichment data]
       Previous emails sent: [subjects] - DO NOT repeat these topics
       Any client replies: [if any]
       Include calendar booking link: [link]

       This is fully AI-generated - write a complete, personalized email.
       Return JSON: {subject: string, body_html: string}"

   d. Save the draft in the activity's note field
   e. Rep sees it when they open "My Activities"

3. Make sure the cron job handles errors gracefully - if one lead fails, continue with others.
```

---

#### C4. Reply-Aware Timing Reset

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement reply detection and follow-up reset:

1. Override message_post on crm.lead in the custom module.
   This is more reliable than base_automation for mail-related triggers.
   Detect incoming emails by checking message_type='email' and confirming
   the sender is not an internal user (not in res.users).

2. When an external email is detected, the override:
   a. Cancel all pending follow-up activities on this lead (unlink them)
   b. Set x_last_reply_date = now
   c. Call Claude Haiku 4.5 to classify reply intent:
      "Classify this email reply intent as one of:
       INTERESTED, NOT_INTERESTED, OOO, REFERRAL.
       Email content: [reply body]
       Return only one word."
   d. Set x_reply_intent based on response

   e. Based on intent:
      - INTERESTED: Create new follow-up activities using same gaps from reply date
        (e.g., if standard was Day 2/5/10, new schedule is reply_date+2, reply_date+5, reply_date+10)
        Apply weekend skipping.
      - NOT_INTERESTED: No new follow-ups. Log to chatter.
      - OOO: If return date mentioned, schedule single follow-up on return date.
      - REFERRAL: Log to chatter. Rep handles manually.
```

---

### Phase D: Meeting & MOM (Week 4-5)

#### D1. Client MOM Generator

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement client MOM generation:

1. Create an API endpoint or method that n8n can call when it has a meeting transcript.
   n8n sends: {lead_id: int, transcript: string}

2. The method:
   a. Receives transcript from n8n (originally scraped from Apollo via Playwright)
   b. Calls Claude Sonnet 4.6:
      "Generate a structured Meeting Minutes (MOM) from this transcript.
       Format:
       - Attendees
       - Discussion Points (numbered)
       - Decisions Made
       - Action Items (with owner if identifiable)
       - Next Steps
       - Key Signals (budget mentioned, timeline, objections, buying intent)

       Also generate a client-safe version (exclude internal signals, budget discussions,
       and anything that should stay internal).

       Return JSON: {
         full_mom: string (HTML),
         client_email_subject: string,
         client_email_body: string (HTML, client-safe version)
       }"

   c. Log full MOM to lead chatter (internal note)
   d. Create a draft email activity on the lead assigned to the lead owner
      with the client-safe email in the activity note
   e. Rep sees it in "My Activities", reviews, sends

3. The draft must be assigned to the rep who attended the meeting (the lead owner).
```

---

### Phase E: Presale System (Week 5-7)

#### E1. Presale Ticket Creation + Discussion Gist

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement presale ticket creation:

1. When a sales rep creates a presale ticket (project.task) and links it to a lead
   via x_linked_lead_id:

2. Automated action triggers on project.task creation where x_linked_lead_id is set.

3. The action:
   a. Fetch ALL discussions from the linked lead:
      - All emails (sent and received)
      - All chatter messages
      - All activity notes
      - All MOMs logged
   b. Call Claude Sonnet 4.6:
      "Summarize all discussions for this lead into a comprehensive gist for the presale team.
       Include: what the client needs, their technical requirements, their concerns,
       any decisions made so far, timeline expectations.
       EXCLUDE: all financial information (pricing, discounts, payment terms, budget numbers).
       Format as structured HTML with clear sections."
   c. Post the gist as the first message on the ticket
   d. Subscribe the lead owner to the ticket
```

---

#### E2. Discussion Sync (Lead to Ticket)

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement discussion sync from lead to ticket:

1. Extend the message_post override on crm.lead (same override as C4 Reply-Aware Timing).
   After handling reply detection, also check if the lead has a linked presale ticket
   (x_linked_lead_id is set on a project.task).

2. If a linked ticket exists, the override also:
   a. Get the new discussion/email content
   b. Call Claude Sonnet 4.6:
      "Process this discussion and create a detailed summary for the presale team.
       Strip ALL financial information: pricing, discounts, payment terms, budget numbers,
       rates, costs, or any monetary figures.
       Keep all technical, requirement, and timeline information.
       Return the cleaned summary as HTML."
   c. Post the cleaned summary to the linked presale ticket as a note
```

---

#### E3. Daily Presale Agenda (10:30 AM)

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement the daily presale agenda:

1. Scheduled action (ir.cron) that runs daily at 10:30 AM.

2. The action:
   a. Query all open presale tickets (x_ticket_status in ['open', 'ready_for_wbs', 'wbs_done'])
   b. For EACH ticket:
      - Get recent activity since last agenda (messages, emails, status changes)
      - Get the assigned user
      - Call Claude Haiku 4.5:
        "Generate a presale agenda update for this ticket.
         Include:
         1. Has the customer responded? What did they say?
         2. Any new information from the customer
         3. Open queries that need discussion
         4. Who needs to answer each query
         5. Current status and any blockers

         Keep it concise and actionable. Format as HTML."
      - Post the agenda as a note ON THE TICKET itself
      - All ticket subscribers will be auto-notified by Odoo

3. Each ticket gets its own agenda post.
   People subscribed to multiple tickets get multiple notifications.
```

---

#### E4. Presale Email Drafter (After Presale Meetings)

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement presale email drafting:

This creates TWO outputs after presale discussions:
1. MOM logged to the TICKET (internal - done by n8n/MOM splitter)
2. Draft client email created as activity on the LEAD (for rep to review and send)

Implementation:
1. Create a method that n8n calls after presale MOM is split and posted to a ticket.
   n8n sends: {ticket_id: int, mom_content: string}

   Additionally, override message_post on project.task to detect when
   a customer-related discussion is posted to a ticket. This catches
   scenarios where discussions are added outside of the n8n MOM flow.

2. The method:
   a. Get the linked lead from the ticket (x_linked_lead_id)
   b. Get full conversation history with the client
   c. Call Claude Sonnet 4.6:
      "Based on this internal presale meeting discussion, draft a client-facing email.

       Presale MOM: [mom_content]
       Previous client conversations: [history]

       The email should:
       - Confirm any decisions/findings from the presale discussion
       - Ask any open questions identified by the presale team
       - Reference relevant past conversations with the client
       - Be professional and clear

       Return JSON: {subject: string, body_html: string}"

   d. Create a mail.activity on the LEAD (not the ticket):
      - Activity type: "Presale Email Draft"
      - Assigned to: lead owner
      - Note: the drafted email content

   e. Rep sees it in "My Activities" alongside follow-up email drafts

This ensures reps have ONE place to check for all outbound email drafts.
```

---

### Phase F: WBS & Proposal (Week 7-8)

#### F1. "Request Proposal from AI" Button

**Give this to Claude Code:**
```
In the sales_ai_integration module, add a "Request Proposal from AI" button on presale tickets:

1. Add a button to the project.task form view (only visible when x_ticket_status = 'wbs_done').

2. The button action:
   a. Sets x_ticket_status = 'ready_for_proposal'
   b. Sends a webhook to n8n with: {ticket_id, lead_id, wbs_sheet_url}
   c. n8n handles the rest:
      - Pulls proposal template from Google Drive
      - Pulls WBS data from Google Sheet
      - Calls Claude Opus 4.6 to generate the proposal
      - Writes completed proposal to Google Drive
      - Calls back to Odoo with the Google Drive link
   d. On callback: store the proposal URL on the ticket and notify the rep

3. Add a status indicator on the ticket form: "Proposal: Pending / Generated / Sent"
```

---

### Phase G: Retro & Closing (Week 8)

#### G1. Lead Closure Retrospective

**Give this to Claude Code:**
```
In the sales_ai_integration module, implement lead closure retro:

1. Automation rule: triggers on crm.lead stage change to Won or Lost.

2. The action:
   a. Gather COMPLETE lead history:
      - All emails (sent and received, with timestamps)
      - All activities and their completion dates
      - All MOMs
      - Presale ticket discussions (if ticket exists)
      - WBS and proposal data
      - Timeline of stage changes
      - Response times (time between client email and our reply)

   b. Call Claude Sonnet 4.6:
      "Perform a comprehensive retrospective on this deal.
       Outcome: [Won/Lost]

       Analyze:
       1. What We Did Well - specific examples from the history
       2. What Could Be Improved - specific gaps identified
       3. Time Analysis - total duration, time per stage, bottlenecks
       4. Repeat Communication - did we ask the same thing twice? Did the client repeat themselves?
       5. Response Time Audit - average response time, any delays
       6. Presale Efficiency - number of meetings, productivity
       7. Proposal Quality - revisions needed?
       8. Key Learnings - actionable insights for similar future deals

       Be specific and reference actual events from the history.
       Format as structured HTML."

   c. If the lead has a linked presale ticket: post retro on the TICKET
      (tickets are visible to all team members)
   d. If NO linked ticket: post retro on the LEAD as fallback
   e. Send summary to Teams via n8n webhook
```

---

### Phase H: Email Smart Routing (Week 8-9)

#### H1. `mail_smart_link` Odoo Module

**Why:** When a known customer sends a NEW email (not a reply to an existing Odoo thread), Odoo's default behavior creates a duplicate lead. This module prevents that by routing the email to the existing active lead.

**Give this to Claude Code:**
```
Create a new Odoo 19 CE module called "mail_smart_link" with:

Module structure:
- __manifest__.py (depends on: crm, mail, fetchmail, google_gmail)
- models/__init__.py
- models/crm_lead.py

The module overrides message_new on crm.lead:

1. When message_new is triggered for crm.lead:
   a. Extract sender email from the incoming message
   b. Search res.partner for matching email
   c. If partner found:
      - Search crm.lead for active leads where partner_id = partner
        OR email_from matches sender email
      - If exactly ONE active lead: call message_post on that lead (attach the email),
        return the existing lead (do NOT create a new one)
      - If MULTIPLE active leads: attach to the most recent lead (highest id),
        post an internal note flagging that multiple leads exist, return that lead
      - If NO active leads: fall through to default behavior (create new lead)
   d. If no partner found: fall through to default (create new lead)

Key requirements:
- Only override message_new, not message_process
- Only applies to crm.lead model
- Only search active leads: [['active', '=', True]]
- Log an info message when smart-linking occurs for auditability
- Keep it lightweight and surgical

```

---

### Phase I: Gmail Workspace Add-on (Week 9-11)

**Why:** Reps sometimes send emails from Gmail directly (not from Odoo). This add-on gives them Odoo CRM context inside Gmail and lets them log emails, create leads, and manually link emails to leads.

**Who:** This is a Google Apps Script project, NOT an Odoo module. Can be built by the dev team in parallel with Odoo work.

#### I1. Foundation + Settings

**Give this to Claude Code:**
```
Create a Gmail Workspace Add-on (Google Apps Script) project:

File structure:
- appsscript.json (manifest with contextual triggers, scopes)
- Code.gs (entry point: onHomepage, onGmailMessageOpen)
- OdooApi.gs (JSON-RPC wrapper for Odoo /jsonrpc endpoint)
- Cards.gs (CardService UI builders)
- Settings.gs (credential storage/validation)
- DuplicateCheck.gs (dedup logic using Message-ID)
- Utils.gs (email parsing, HTML sanitization)

Phase 1 deliverables:
1. Settings card where rep enters Odoo URL, username, password
2. Store credentials in PropertiesService.getUserProperties()
3. Authenticate against Odoo via JSON-RPC common/authenticate
4. Cache UID for subsequent calls
5. OdooApi.gs: wrapper function odooExecute(model, method, args, kwargs)
   that calls Odoo's /jsonrpc endpoint with execute_kw

OAuth scopes needed:
- gmail.addons.current.message.metadata
- gmail.addons.current.message.readonly
- script.external_request
- userinfo.email

Acceptance: Can authenticate against Odoo and fetch a partner record.

```

#### I2. Contextual Sidebar

**Give this to Claude Code:**
```
In the Gmail Workspace Add-on, implement the contextual sidebar:

1. onGmailMessageOpen trigger fires when rep opens any email
2. Extract sender email from message metadata
3. Search Odoo res.partner by email: [['email', 'ilike', senderEmail]]
4. If partner found, search crm.lead by partner AND email:
   ['|', ['partner_id', '=', partnerId], ['email_from', 'ilike', senderEmail], ['active', '=', true]]
5. Render sidebar card showing:
   - Partner info: name, email, phone, company
   - List of associated leads: name, stage, expected revenue, salesperson
   - Each lead clickable (opens in Odoo)
   - Action buttons: "Log This Email", "Create New Lead"
6. If no partner/lead found: show "No matching contact" with "Create Lead" button

Add caching: cache partner lookups in CacheService.getUserCache() with 10-min TTL.

Acceptance: Opening an email from a known contact shows partner + leads in sidebar.
```

#### I3. Log Email to Lead

**Give this to Claude Code:**
```
In the Gmail Workspace Add-on, implement "Log Email to Lead":

1. When rep clicks "Log This Email":
   - If one lead found → pre-select it
   - If multiple → show lead picker (search by name/partner name)
   - If none → show search input
2. Extract full email data:
   - RFC 2822 Message-ID header (critical for dedup)
   - Subject, From, To, Cc, Date
   - Email body (HTML preferred, plain text fallback)
3. Duplicate check: search mail.message where [['message_id', '=', rfcMessageId]]
   - If found → show "Already logged" with link
   - If not found → proceed
4. Call message_post on crm.lead with:
   body, subject, message_type="email", subtype_xmlid="mail.mt_comment",
   email_from, message_id=rfcMessageId
5. Show success card with link to lead

Acceptance: Rep can log email to lead, dedup works, email appears in Odoo chatter.
```

#### I4. Create Lead from Email

**Give this to Claude Code:**
```
In the Gmail Workspace Add-on, implement "Create New Lead":

1. Pre-fill form: subject → lead name, sender name → contact name, sender email, body snippet → description
2. Optional fields: expected revenue, priority, tags (fetch crm.tag list)
3. On submit:
   a. Check/create res.partner for sender email
   b. Create crm.lead: {name, partner_id, email_from, contact_name, description, type: "lead", user_id: currentUid}
   c. Log the email to the new lead via message_post (same as Log Email flow)
4. Show success card with link to new lead

Acceptance: Rep can create lead from email, partner auto-created, email auto-logged.
```

---

## Odoo Configuration Tasks (No Development Needed)

These are setup tasks in the Odoo UI, not code changes.

| Task | How |
|------|-----|
| Create Marketing User | Settings > Users. Create a user for receiving junk/marketing leads. |
| Lead Assignment Rules | CRM > Configuration > Assignment Rules. Set up round-robin. |
| Pipeline Stages | CRM > Configuration > Stages. Set up: New, Qualified, Meeting, Tech Review, Proposal, Negotiation, Won, Lost. |
| Projects Module | Install Projects module. Create a "Presale" project. |
| Email Alias | Settings > Technical > Aliases. Set up sales@ alias pointing to CRM. |
| Google Gmail Module | Install `google_gmail` module. Configure Google Cloud Project with OAuth client ID and redirect URI pointing to Odoo instance. |
| Email Auth per Rep | Each rep: Settings > Technical > Incoming Mail Servers > authenticate via Google OAuth 2.0 (one-time consent flow). Outgoing mail also via OAuth-authenticated Gmail SMTP. Plain passwords no longer supported by Google. |
| Gmail Add-on Deployment | Deploy Apps Script add-on via Google Workspace Admin Console. Each rep configures Odoo credentials. |
| Rep Calendar Links | Each salesperson: Settings > Users > [user] > fill x_calendar_link field with their Calendly booking link. |
| Google Calendar Sync | Install `google_calendar` module. Enable Calendar API in same Google Cloud Project. Each rep clicks 'Sync with Google' in Odoo Calendar → OAuth consent → done. |
| ICP Criteria | Module Settings > fill in the ICP JSON based on sales team input. |
| Stale Deal Thresholds | Module Settings > define days per stage. |

---

## n8n Workflows to Build

These are built separately from the Odoo module. The Odoo module needs to expose endpoints/webhooks for n8n to call.

| # | Workflow | Triggers From | Calls Back To |
|---|---------|--------------|--------------|
| W1 | Apollo Recording Fetch | Calendar event ends | Odoo: delivers transcript for MOM generation |
| W2 | Presale MOM Splitter | Presale recording ready | Odoo: posts MOM sections to tickets, triggers presale email drafter |
| W3 | WBS Generator | Odoo webhook (ticket ready) | Google Sheets: creates WBS. Odoo: stores Sheet URL |
| W4 | Teams Notifications | Odoo webhooks | Teams: sends messages |
| W5 | Stale Deal Monitor | Daily cron | Odoo: queries leads. Teams: sends alerts |
| W6 | Prospect Import | Weekly cron | Apollo (Playwright) -> Odoo: creates leads |
| W7 | Apollo Data Scraper | Odoo webhook (enrichment needed) | Apollo (Playwright) -> Odoo: delivers enrichment data |
| W8 | Proposal Generator | Odoo webhook (proposal requested) | Google Drive + Sheets -> Claude -> Google Drive -> Odoo: stores proposal URL |

---

## Testing Checklist

Before pilot launch, verify each feature end-to-end:

- [ ] Lead creation triggers junk filter
- [ ] Genuine lead gets enriched (Apollo data flows in)
- [ ] Lead gets scored based on ICP criteria
- [ ] Assignment triggers auto-ack email with rep's calendar link
- [ ] Calendar event synced from Google Calendar auto-links to correct lead
- [ ] Follow-up activities created with correct dates (check weekend skipping)
- [ ] 9 AM cron generates email drafts in activities
- [ ] Client reply cancels pending follow-ups and reschedules
- [ ] Meeting transcript flows from Apollo -> n8n -> Odoo -> MOM draft
- [ ] Presale ticket creation generates discussion gist
- [ ] New lead discussions sync to ticket (financial data stripped)
- [ ] 10:30 AM agenda posts to each open ticket
- [ ] Presale MOM creates draft email activity on the lead
- [ ] "Request Proposal from AI" button works end-to-end
- [ ] Lead Won/Lost triggers retro on ticket (or lead if no ticket)
- [ ] Stale deal alerts fire correctly per stage threshold
- [ ] Email sent from Odoo appears in rep's Gmail Sent folder
- [ ] Email sent from Gmail with CC to sales@ logged in Odoo lead
- [ ] Email sent from Gmail without CC → rep logs via Gmail Add-on
- [ ] Customer reply to Odoo thread auto-linked
- [ ] New email from known customer → `mail_smart_link` routes to existing lead (no duplicate)
- [ ] New email from unknown sender → new lead created
- [ ] Duplicate prevention: Add-on logs first, then IMAP → no duplicate
- [ ] Duplicate prevention: IMAP first, then Add-on → no duplicate
