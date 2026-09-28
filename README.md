# AI Lead Rescue & Quote Follow-Up Command Center

A complete, portfolio-ready sales operations demo for service businesses. It captures inquiries, tracks quotes, identifies overdue follow-ups, and prepares AI-assisted follow-up drafts for human review.

## The business problem

Small service businesses often collect leads from websites, ads, referrals and freelance platforms, but the handoff after the first inquiry is messy. Quotes are sent, follow-ups are missed, and potential revenue goes cold because there is no single system showing **who needs attention next**.

This project solves that workflow problem without turning customer communication into a risky black box: automation detects overdue quotes and prepares a draft, while a human remains in control of the final message.

## Features

- Modern responsive admin dashboard
- Public lead-intake / quote request form
- SQLite database with leads, activities and reminders
- Lead pipeline: New → Contacted → Qualified → Quote Sent → Waiting → Won/Lost
- Quote amount + automatic next-follow-up scheduling
- Background follow-up automation (runs every 60 seconds by default)
- AI lead summaries
- AI follow-up email drafts
- Human-in-the-loop workflow — drafts are never auto-sent
- Dashboard KPIs and pipeline visualization
- Search and status filters
- Lead detail view with activity timeline
- Realistic demo data using safe `.example` email domains
- One-click demo reset API
- Works without an AI key using a deterministic fallback
- Optional OpenAI Responses API integration
- Zero third-party Python dependencies
- Unit tests for database, quote workflow and automation

## Stack

**Frontend:** HTML5, CSS3, Vanilla JavaScript  
**Backend:** Python standard-library HTTP server  
**Database:** SQLite  
**AI:** Optional OpenAI Responses API + local demo fallback  
**Automation:** Python background worker + SQLite reminder queue

## Quick start

### Windows

```powershell
cd lead-rescue-command-center
python app.py
```

Or double-click `run.bat`.

### Linux / WSL / macOS

```bash
cd lead-rescue-command-center
./run.sh
```

Open:

- Dashboard: `http://127.0.0.1:8000`
- Public intake form: `http://127.0.0.1:8000/intake`

The SQLite database is generated automatically at `data/lead_rescue.db` and demo data is seeded on the first run.

## Optional AI API setup

The demo does **not** require a paid API. Without a key, summaries and follow-up drafts use a deterministic fallback so every feature can still be demonstrated.

To enable a live OpenAI model:

1. Copy `.env.example` to `.env`.
2. Add your API key:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.6-luna
```

Use a model that is available to your API account. The backend calls the OpenAI Responses API.

## Automation workflow

1. A lead is captured through the public form or dashboard.
2. The team qualifies the lead.
3. A quote is recorded and a follow-up date is scheduled.
4. The background engine checks for overdue quote follow-ups.
5. It creates one reminder and prepares a personalized AI draft.
6. The salesperson reviews/copies the draft and contacts the client.
7. The reminder is marked complete and the activity is recorded.

This design intentionally keeps **message sending human-controlled**.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | App + AI mode |
| GET | `/api/dashboard` | KPI and pipeline data |
| GET/POST | `/api/leads` | List/create leads |
| GET/PATCH | `/api/leads/:id` | Read/update a lead |
| POST | `/api/leads/:id/ai-summary` | Generate lead brief |
| POST | `/api/leads/:id/followup-draft` | Generate follow-up draft |
| POST | `/api/leads/:id/quote` | Track a quote and schedule follow-up |
| POST | `/api/leads/:id/status` | Change pipeline status |
| GET | `/api/reminders` | Open follow-up queue |
| POST | `/api/reminders/:id/complete` | Complete reminder |
| POST | `/api/automation/run` | Manually run overdue check |
| POST | `/api/demo/reset` | Restore demo dataset |

## Tests

From the project root:

```bash
python -m unittest discover -s tests -v
```

## Production notes

This repository is intentionally a portfolio/MVP build. Before deploying for a real business, add authentication/role permissions, CSRF protection if cookie auth is introduced, rate limiting, secrets management, backups, audit retention rules, email-provider integration and organization-level data separation.

## Portfolio story

**Problem:** service businesses lose revenue when quotes and inquiries are scattered across inboxes and spreadsheets.  
**Solution:** a single command center that captures leads, surfaces overdue follow-ups, and prepares context-aware AI drafts while keeping a human in control.  
**Outcome:** faster response workflow, fewer forgotten quotes, clearer pipeline visibility, and less repetitive admin work.

---

Built as a full-stack portfolio project focused on practical business automation rather than a generic chatbot demo.
