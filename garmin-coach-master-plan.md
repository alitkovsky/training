# Garmin AI Coaching System — Master Development Plan

**Version:** 3.0 — Complete phased plan  
**Stack:** n8n (Docker) · python-garminconnect · Supabase (training schema) · Antigravity/agy · Telegram Bot · iOS Shortcuts  
**Repository:** Separate repo with kisune skills at `.agents/skills/`

---

## Research Findings on Your Three Questions

### Q1 — Can Garmin sync be automated?

**Short answer: Not via API, but iOS Shortcuts provides a reliable workaround.**

Garmin does not expose a sync trigger via any API — there is no endpoint you can call
to force a watch→phone→cloud sync. The sync is always initiated by the Garmin Connect
app on the phone when it detects the watch over Bluetooth.

**What you can control:**
- Garmin Connect auto-sync setting: in the app go to Garmin Devices → Device Settings
  → System → Auto Sync → set to **"Frequent"**. This syncs whenever phone and watch
  are in Bluetooth range, typically every 15 minutes throughout the day.
- With "Frequent" auto-sync enabled, by 08:00 your watch data from overnight and the
  previous evening will already be synced — you don't need to trigger anything manually.

**iOS Shortcuts as a safety net:**
Set an iOS Shortcut automation at 07:50 that opens the Garmin Connect app. Opening
the app triggers an immediate sync. By 08:00 the sync is complete and n8n can fetch
at 08:05.

Setup in iOS Shortcuts:
1. Automation tab → New Personal Automation → Time of Day → 07:50 → Daily
2. Add Action: Open App → Garmin Connect
3. Disable "Ask Before Running"

This cannot be done on macOS alone — the Garmin Connect app and Bluetooth connection
live on the phone. The Shortcut runs on iPhone.

**The retry logic you described is exactly right.** See Phase 4 for n8n implementation.

---

### Q2 — Telegram Bot: free, bidirectional, with control commands

**Yes — fully free, native n8n node, fully bidirectional.**

- **Sending:** n8n Telegram node → send formatted Markdown messages to your personal
  chat or a private group
- **Receiving:** n8n Telegram Trigger node → listens for incoming messages, routes by
  command text (/status, /force_sync, /report, /plan, etc.)
- **Security:** Filter by Chat ID so only your account can issue commands
- **Cost:** Completely free. BotFather creates the bot token at no charge.

Commands you can send from Telegram to control the system:
- /status — last 3 days biometric summary from Supabase
- /report — today's full coaching report
- /sync — force an immediate Garmin data fetch
- /plan — today's session from training/plan.md
- /week — last weekly review summary

---

### Q3 — Adding workouts to the Garmin calendar via API

**Garmin has an official Training API for this — but it requires gated developer
program approval (same process as the Health API).**

The Training API allows publishing structured workouts and training plans directly
to the Garmin Connect calendar. Once published, they sync to the watch automatically.

For personal use without developer program access, the **unofficial python-garminconnect**
library includes a `schedule_workout()` method that replicates what the Garmin Connect
web app does when you drag a workout onto the calendar. This works reliably for personal use.

The workflow:
1. agy generates an adjusted weekly plan → writes to training/plan.md
2. A Python script reads the plan and calls client.schedule_workout(workout_id, date)
3. Sessions appear in Garmin Connect calendar and sync to the Fenix 6

Creating structured workouts (intervals, HR-capped easy runs) also works — the watch
displays step-by-step instructions during the session.

This is a **Phase 5** feature — build it after the core pipeline is stable.

---

## Master Architecture

```
iPhone (07:50)
  └─ iOS Shortcut opens Garmin Connect → triggers BT sync

n8n (08:05) — DATA PIPELINE
  ├─ Check if today's data exists in Supabase
  ├─ If yes → proceed
  ├─ If no → retry in 15 min (max 3 retries)
  │   └─ On 3rd failure → Telegram alert "⚠️ Sync failed, please sync manually"
  ├─ garmin_fetch.py → normalise → Supabase upsert
  └─ Write data/today.json to repo

Antigravity/agy (08:15) — AI ANALYSIS
  ├─ Reads data/today.json + training/plan.md
  ├─ Claude Sonnet analysis via Workspace quota
  └─ Writes reports/YYYY-MM-DD.md

n8n (08:20) — REPORT DELIVERY
  ├─ Reads reports/YYYY-MM-DD.md
  ├─ Saves to Supabase training.daily_reports
  └─ Sends formatted report to Telegram

Telegram Bot — CONTROL INTERFACE
  ├─ Receives /status, /report, /sync, /force commands
  └─ Routes to relevant n8n sub-workflows

agy (Monday 08:30) — WEEKLY REVIEW
  └─ Full week analysis → annotates training/plan.md

n8n (Phase 5) — CALENDAR SYNC
  └─ Pushes next week's sessions to Garmin calendar
```

---

## Phased Development Plan

---

## Phase 1 — Core Data Pipeline
**Goal:** Reliable daily Garmin data → Supabase. Nothing else.
**Duration:** 1–2 days

### 1.1 — Supabase Setup

- [ ] Open your second Supabase project (consent_logs)
- [ ] Run in SQL Editor: `CREATE SCHEMA training;`
- [ ] Run full schema.sql with `training.` prefix on all tables
- [ ] Go to Project Settings → Data API → Extra schemas → add `training`
- [ ] Test connection: insert and read a test row via REST API

### 1.2 — Python Environment

- [ ] Create scripts/requirements.txt:
  ```
  garminconnect>=0.2.19
  python-dotenv>=1.0.0
  supabase>=2.0.0
  ```
- [ ] Create scripts/.env (gitignored):
  ```
  GARMIN_EMAIL=your@email.com
  GARMIN_PASSWORD=yourpassword
  SUPABASE_URL=https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY=your-service-role-key
  ```
- [ ] Test garmin_fetch.py manually → confirm JSON output

### 1.3 — Historical Bulk Import

- [ ] Run: `python garmin_bulk_import.py 2026-01-01 > data/bulk_import.ndjson`
- [ ] Run: `python supabase_bulk_upsert.py`
- [ ] Verify ~166 rows in training.daily_wellness
- [ ] Verify activities in training.activities

### 1.4 — n8n Docker Verification

- [ ] Confirm running: `docker ps | grep n8n`
- [ ] Update: `docker compose pull n8n && docker compose up -d n8n`
- [ ] Add scripts volume to docker-compose.yml: `./scripts:/home/node/scripts`
- [ ] Confirm Execute Command node can run garmin_fetch.py

### 1.5 — n8n Daily Data Workflow (v1)

```
[Schedule Trigger 08:05]
      ↓
[Execute Command: garmin_fetch.py]
      ↓
[Function: Normalise JSON]
      ↓
[Supabase: Upsert training.daily_wellness]
      ↓
[Supabase: Upsert training.activities]
      ↓
[Write File: data/today.json]
```

- [ ] Build and test with manual execution
- [ ] Confirm data in Supabase and data/today.json written
- [ ] Enable schedule trigger

**Phase 1 done when:** data/today.json is written every morning with correct data.

---

## Phase 2 — Training Plan + agy Analysis
**Goal:** Daily coaching report generated by agy from real data.
**Duration:** 1–2 days

### 2.1 — Training Plan File

Create training/plan.md with this structure:

```markdown
# Training Plan — [Phase Name]
**Phase:** Base 2
**Current Week:** 1 of 16
**Target Race:** [Race, Date]
**Weekly TSS Target:** 380–420

## Week 1 (Mon DD Mon – Sun DD Mon)

| Day | Session | Type | Duration | Target | TSS est. |
|-----|---------|------|----------|--------|---------|
| Mon | Easy run | Z1-2 | 45 min | <142 bpm | 40 |
...

**Week notes:** [coaching intent for the week]
```

- [ ] Fill in your current training block
- [ ] Commit to repo

### 2.2 — Prompt Files

- [ ] Create prompts/daily-analysis.md (see template in previous guide)
- [ ] Create prompts/weekly-review.md
- [ ] Test manually in Antigravity IDE

### 2.3 — Antigravity Scheduled Task

- [ ] Open Antigravity → /schedule
- [ ] Name: Daily Garmin Coaching Analysis
- [ ] Cron: 15 8 * * * (08:15 — after n8n data fetch)
- [ ] Prompt: contents of prompts/daily-analysis.md
- [ ] Enable Keep in Menu Bar in Antigravity preferences
- [ ] Test manually, then let it run automatically next morning

**Phase 2 done when:** reports/YYYY-MM-DD.md exists every morning with analysis.

---

## Phase 3 — Telegram Bot
**Goal:** Receive reports in Telegram; control the system via commands.
**Duration:** 1 day

### 3.1 — Create the Bot

- [ ] Open Telegram → search BotFather → /newbot
- [ ] Name: GarminCoach (or your choice)
- [ ] Copy the API token

### 3.2 — n8n Telegram Credentials

- [ ] n8n → Settings → Credentials → New → Telegram API → paste token
- [ ] Get your Chat ID: message the bot, then check
  `https://api.telegram.org/bot<TOKEN>/getUpdates`

### 3.3 — Report Delivery (add to daily workflow)

Add after Write File node:

**Node: Read Report File** → read reports/{{ today }}.md as text

**Node: Telegram — Send Message**
- Chat ID: your personal chat ID (n8n env variable)
- Parse mode: Markdown

Message format:
```
📊 *Daily Coaching Report — {{ date }}*

*Recommendation:* {{ recommendation }}

*Biometrics:*
• HRV: {{ hrv_last_night }}ms (7d avg: {{ hrv_weekly_avg }}ms)
• Sleep: {{ sleep_h }}h (score: {{ sleep_score }}/100)
• Body Battery: {{ body_battery }}/100
• ACWR: {{ acwr }}

{{ analysis_summary_2_sentences }}
```

### 3.4 — Command Bot Workflow (second n8n workflow, always-on)

```
[Telegram Trigger: Message received]
       ↓
[Filter: Chat ID = yours only]  ← security gate
       ↓
[Switch: command text]
  /status  → Supabase: last 3 days summary → reply
  /report  → read today's report file → send full text
  /sync    → Execute Command: garmin_fetch.py → reply "Sync triggered"
  /plan    → read training/plan.md → send today's session
  /week    → Supabase weekly_reviews → send last review
  unknown  → reply with command list
```

- [ ] Build the command routing workflow
- [ ] Test each command from Telegram
- [ ] Confirm Chat ID filter blocks other senders

### 3.5 — Error Alerts

Add Error Trigger node → Telegram alert:
```
⚠️ *Garmin Coach Error*
Workflow: {{ $workflow.name }}
Node: {{ $execution.lastNodeExecuted }}
Error: {{ $json.error.message }}
Time: {{ $now }}
```

**Phase 3 done when:** Reports arrive in Telegram automatically and all 5 commands work.

---

## Phase 4 — Sync Reliability (Retry Logic + iOS Shortcut)
**Goal:** Automated sync trigger + smart retry that alerts you on failure.
**Duration:** Half a day

### 4.1 — iOS Shortcut on iPhone

- [ ] Open Shortcuts → Automation → New Personal Automation
- [ ] Trigger: Time of Day → 07:50 → Daily
- [ ] Action: Open App → Garmin Connect
- [ ] Disable "Ask Before Running"
- [ ] Test: Garmin Connect opens and syncs at 07:50

### 4.2 — n8n Retry Logic (replace simple trigger)

```
[Schedule Trigger 08:05]
       ↓
[HTTP Request: Supabase — check today's row in training.daily_wellness]
       ↓
[IF: row exists AND hrv_last_night is not null]
  YES → continue to normal fetch/analysis flow
  NO  → [Increment retry counter]
         [IF counter < 3]
           YES → [Wait 15 min] → loop back to check
           NO  → [Telegram: ⚠️ Garmin sync failed after 3 attempts.
                  Please sync manually and run /sync in chat.]
                 [Stop]
```

Supabase check query:
```sql
SELECT date, hrv_last_night
FROM training.daily_wellness
WHERE date = CURRENT_DATE
LIMIT 1
```

Note: If hrv_last_night is null (watch not worn overnight), the workflow still proceeds
but the prompt context includes "HRV data unavailable — watch not worn overnight."

**Phase 4 done when:** A missed sync alerts you in Telegram with retry status; the
system never silently fails.

---

## Phase 5 — Garmin Calendar Integration
**Goal:** AI-adjusted sessions pushed to Garmin calendar → syncs to watch.
**Duration:** 2–3 days

### 5.1 — Workout Library Table in Supabase

```sql
CREATE TABLE training.workouts (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name                TEXT NOT NULL,
    type                TEXT,          -- 'easy_run', 'tempo', 'long_run', 'intervals'
    description         TEXT,
    duration_min        INTEGER,
    hr_cap_bpm          INTEGER,       -- for zone-capped sessions
    target_pace_sec_km  INTEGER,       -- for structured runs
    structure_json      JSONB,         -- Garmin step-by-step workout format
    garmin_workout_id   BIGINT         -- filled after first push to Garmin
);
```

### 5.2 — Calendar Push Script (scripts/garmin_calendar_push.py)

```python
import garminconnect, json, sys, os
from dotenv import load_dotenv
load_dotenv()

client = garminconnect.Garmin(os.getenv("GARMIN_EMAIL"), os.getenv("GARMIN_PASSWORD"))
client.login()

# Usage: python garmin_calendar_push.py '{"date": "2026-06-20", "workout_id": 12345678}'
payload = json.loads(sys.argv[1])
client.schedule_workout(payload["workout_id"], payload["date"])
print(json.dumps({"status": "scheduled", "date": payload["date"]}))
```

### 5.3 — Weekly Plan Push Workflow (Monday 09:00)

1. Read updated training/plan.md (after agy's weekly review annotations)
2. Match each session type to training.workouts library
3. For each match → Execute Command garmin_calendar_push.py
4. Telegram summary: "📅 Next week's plan pushed to Garmin calendar (7 sessions)"

### 5.4 — agy Skill: garmin-workout-scheduler

Create a custom kisune-style skill at .agents/skills/garmin-workout-scheduler/SKILL.md:
- Reads the weekly plan
- Identifies session types and dates
- Outputs structured JSON: {date, session_type, workout_library_id}
- n8n reads this JSON and triggers the calendar push

**Phase 5 done when:** Every Monday, next week's sessions appear in Garmin Connect
calendar and sync to the Fenix 6.

---

## Phase 6 — Polish and Reliability
**Goal:** Production-ready, self-healing, with weekly coaching loop.
**Duration:** Ongoing

- [ ] Weekly review workflow (Monday 08:30): agy analyses full week
- [ ] Plan annotation: agy marks training/plan.md with <!-- AI: --> comments;
  you approve/reject via Telegram /approve or /reject commands
- [ ] Supabase MCP in Antigravity: agy queries DB directly without pre-written JSON
- [ ] Monthly mesocycle review: agy evaluates training block, proposes next phase
- [ ] Auto-commit reports to git via n8n Execute Command (git add/commit/push)
- [ ] Backup report delivery: if agy report file missing by 09:00, n8n sends Telegram alert

---

## Complete Repository Structure

```
your-repo/
├── AGENTS.md                              # agy project constitution + coaching context
├── training/
│   └── plan.md                            # Active training plan (living document)
├── data/
│   └── today.json                         # Ephemeral daily data (gitignored)
├── scripts/
│   ├── garmin_fetch.py                    # Single-day Garmin fetcher
│   ├── garmin_bulk_import.py              # Historical bulk import
│   ├── supabase_bulk_upsert.py            # Bulk upsert to Supabase
│   ├── garmin_calendar_push.py            # Phase 5: push to Garmin calendar
│   ├── requirements.txt
│   └── .env                               # (gitignored)
├── prompts/
│   ├── daily-analysis.md                  # agy daily coaching prompt
│   └── weekly-review.md                   # agy weekly review prompt
├── reports/                               # Daily + weekly AI reports (versioned)
│   └── .gitkeep
├── supabase/
│   └── schema.sql                         # Full DB schema
├── n8n/
│   └── workflows/
│       ├── 01-daily-data-pipeline.json
│       ├── 02-telegram-command-bot.json
│       ├── 03-weekly-push.json
│       └── 04-error-alerts.json
├── .agents/
│   └── skills/                            # kisune skills (already installed)
├── .gitignore                             # includes data/ and scripts/.env
└── README.md
```

---

## Timeline Summary

| Phase | What's Built | Duration |
|---|---|---|
| Phase 1 | Supabase schema + historical import + n8n data pipeline | Days 1–2 |
| Phase 2 | training/plan.md + agy scheduled analysis + daily reports | Days 3–4 |
| Phase 3 | Telegram bot: report delivery + commands + error alerts | Day 5 |
| Phase 4 | iOS Shortcut sync trigger + n8n retry logic | Day 6 |
| Phase 5 | Garmin calendar integration (workout push to watch) | Week 2 |
| Phase 6 | Weekly review, plan annotations, reliability polish | Ongoing |

---

## What Stays Out of Scope (for Now)

- Official Garmin gated APIs (Training API, Health API) — python-garminconnect covers all
  needed personal-use functionality without developer program approval
- Multi-device support — plan is Fenix 6-specific
- Web dashboard — reports live in Telegram and Markdown files; no web UI needed
- LM Studio / local LLM — Antigravity handles all AI via Workspace Claude quota
