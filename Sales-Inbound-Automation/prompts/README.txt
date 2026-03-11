==============================================================================
INBOUND SALES AI — PROMPT LIBRARY
Review & Approval Guide for Sales / Presale Team
==============================================================================

WHO SHOULD REVIEW THESE FILES:
  - Sales Head       → Review: 01, 02, 03, 04, 05, 06, 07, 13
  - Presale Team     → Review: 08, 09, 10, 11, 12, 14, 15, 16
  - Both             → Review: 03 (ICP scoring criteria is critical)

HOW THIS WORKS:
  Each file contains the EXACT instructions given to Claude AI for one task.
  Claude reads these instructions before generating any output.

  Think of it like a briefing document you'd give a new sales hire.
  The better the briefing, the better the output.

HOW TO REVIEW:
  1. Read each prompt file.
  2. Add your feedback in the FEEDBACK SECTION at the bottom of each file.
  3. Mark your review status: [ ] Pending  [~] In Review  [x] Approved
  4. Hand back to the dev team — they will update the code accordingly.

WHAT TO LOOK FOR:
  - Does the tone match how we communicate with clients?
  - Are the rules correct for our business? (word limits, structure, etc.)
  - Are there scenarios we handle differently that aren't covered?
  - For scoring/classification: are the criteria accurate for our ICP?
  - For emails: does the writing style feel like us?

IMPORTANT:
  - Do NOT change the "OUTPUT FORMAT" sections — those are technical.
  - Do NOT change text inside { } or [ ] brackets in format sections.
  - Everything else is fair game to edit / rewrite.

FILES IN THIS FOLDER:
  Phase 1 — Core Pipeline (build first):
    01_junk_filter.txt              → Filters spam / junk leads
    02_enrichment_structurer.txt    → Structures Apollo data (technical, less review needed)
    03_lead_scoring.txt             → Scores leads 0-100 against ICP ← CRITICAL
    04_auto_ack_email.txt           → First email to client after lead arrives ← CRITICAL
    05_followup_emails.txt          → Day 2/5/10 follow-up emails ← CRITICAL
    06_reply_classifier.txt         → Classifies client replies
    07_client_mom.txt               → Meeting minutes + client email

  Phase 2 — Presale Intelligence:
    08_ticket_gist.txt              → Presale ticket onboarding summary
    09_daily_agenda.txt             → Daily 10:30 AM standup agenda
    10_presale_mom.txt              → Internal presale meeting minutes
    11_presale_email.txt            → Client email after presale meetings
    12_wbs_generator.txt            → Work breakdown structure
    13_retrospective.txt            → Won/Lost deal analysis
    14_no_show_followup.txt         → When client misses a meeting

  Phase 3 — Advanced:
    15_meeting_prep_brief.txt       → Pre-meeting brief for rep
    16_proposal_generator.txt       → Full sales proposal ← MOST IMPORTANT

==============================================================================
