# Garmin AI Training Coach — Project Implementation Guide

**Project:** Daily Garmin health data pipeline → Supabase → Local LLM analysis → Training plan adaptation  
**Stack:** n8n (Docker) · python-garminconnect · Supabase · LM Studio (gemma-4-12b) · Google Gemini fallback · agy + kisune dev-workflow skills  
**Repository:** Separate repo with kisune skills already installed at `.agents/skills/`

---

## Overview and Expert Context

The approach described in this document aligns with the current state of AI coaching practice. Research published in 2026 confirms that dynamically adjusting training intensity based on daily HRV data, compared to following a predefined training plan, more effectively improves VO₂max and performance while reducing the proportion of non-responders to training.[cite:40] Leading AI coaching platforms now implement daily readiness assessments where HRV, sleep quality, and stress markers are evaluated to adjust training intensity automatically.[cite:43] The key expert insight is that HRV-derived readiness scores are the most sensitive and actionable leading indicator of training stress, ahead of all other biometric signals.[cite:46]

The system architecture proposed here mirrors what elite-level self-coached athletes are building in 2026: a Garmin data pipeline feeding an LLM with structured context about the training plan, producing a daily coaching report and suggested adjustments.[cite:45] The training plan lives as a Markdown file in the repository and is treated as a living document — compared against each day's biometrics and updated by the agent when warranted.

---

## Assessment of the Approach

The core idea — morning data pull → store → analyse → compare with plan → suggest adjustments — is sound and well-supported by sports science. A few important nuances:

- **Acute:chronic workload ratio (ACWR)** is the most important macro signal. A ratio between 0.8 and 1.3 is the safe training zone; above 1.5 is high injury risk. The database must accumulate enough history (minimum 28 days) to compute this reliably.[cite:48]
- **HRV trend over 7 days vs 30-day baseline** is more meaningful than any single morning reading. The LLM prompt must include rolling statistics, not just yesterday's value.[cite:39]
- **The plan is a ceiling, not a floor.** The AI's job is primarily to say "don't do today's session as written" rather than to invent new sessions. Plan adjustments should be additive and cautious.
- **Zone distribution review** is best done weekly (Monday morning), not daily. The daily report should focus on readiness and last-session quality; the weekly report on load distribution and plan adherence.[cite:39]
- **MacBook Air M4 16 GB** is sufficient for gemma-4-12b (Q4 quantised: ~7 GB VRAM). For coaching prompts under 2,000 tokens, inference time is 10–25 seconds. If latency becomes an issue at longer prompts, drop to gemma-4-e4b (7.9B) first before switching to qwen3.5-9b.

---

## Repository Structure

```
your-repo/
├── AGENTS.md                          # agy project constitution
├── training/
│   └── plan.md                        # Active training plan (living document)
├── scripts/
│   ├── garmin_fetch.py                # Garmin data fetcher
│   ├── requirements.txt               # Python dependencies
│   └── .env.example                   # Credential template
├── n8n/
│   ├── workflows/
│   │   ├── daily-morning-workflow.json
│   │   └── weekly-review-workflow.json
│   └── README.md
├── supabase/
│   └── schema.sql                     # Full DB schema
├── reports/
│   └── .gitkeep                       # Daily reports written here
├── .agents/
│   └── skills/                        # kisune skills (already installed)
├── .env.example
└── README.md                          # This document
```

---

## Part 1 — Infrastructure Setup

### 1.1 Verify and Update n8n (Docker)

```bash
# Check current status
docker ps | grep n8n

# Check current version
docker exec -it n8n n8n --version

# Pull latest image
docker pull n8nio/n8n:latest

# Restart with latest (adjust to your compose setup)
docker compose pull n8n && docker compose up -d n8n

# Confirm n8n is accessible
open http://localhost:5678
```

If using a raw `docker run` command (not Compose), update it to pin a recent version tag and add the environment variables needed for LM Studio and Supabase credentials.

Minimum recommended `docker-compose.yml` additions:

```yaml
services:
  n8n:
    image: n8nio/n8n:latest
    environment:
      - N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true
      - N8N_COMMUNITY_PACKAGES_ENABLED=true
      - EXECUTIONS_DATA_SAVE_ON_SUCCESS=all
    volumes:
      - n8n_data:/home/node/.n8n
      - ./scripts:/home/node/scripts   # Mount scripts directory
    ports:
      - "5678:5678"
    restart: unless-stopped
```

### 1.2 LM Studio Setup

1. Open LM Studio → **Developer** tab → enable **Local Server**
2. Ensure **google/gemma-4-12b** (or your quantised variant) is loaded
3. Set **Context Length** to `8192` (needed for full plan + biometrics prompt)
4. Enable **"Keep model in memory between requests"**
5. Default endpoint: `http://127.0.0.1:1234/v1`

**Model selection guide for M4 16 GB:**

| Model | Size (Q4) | Fits 16 GB? | Coaching quality | Use when |
|---|---|---|---|---|
| gemma-4-12b | ~7 GB | ✅ Yes | Excellent | Default choice |
| qwen3.5-9b | ~5.5 GB | ✅ Yes | Very good | If gemma-4 is slow |
| gemma-4-e4b (7.9B) | ~4.5 GB | ✅ Yes | Good | Speed priority |

If the system becomes sluggish during inference, check Activity Monitor for memory pressure. If any swap is occurring, drop to the 7.9B model.

### 1.3 Google Gemini via HTTP (Workspace)

For the Gemini fallback in n8n, use the **HTTP Request node** directly (not the OpenAI node):

- **URL:** `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=YOUR_API_KEY`
- **Method:** POST
- **Body:**
```json
{
  "contents": [{"parts": [{"text": "{{ $json.prompt }}"}]}],
  "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1500}
}
```

Store the API key in n8n Credentials as an **HTTP Header Auth** credential or as a plain environment variable injected via Docker.

---

## Part 2 — Supabase Database

### 2.1 Project Setup

1. Create a new project at [supabase.com](https://supabase.com) (free tier is sufficient for this workload)
2. Go to **Project Settings → Data API** and copy:
   - **Project URL** (`https://xxxx.supabase.co`)
   - **service_role** secret key (for n8n — has full DB access)
   - **anon** public key (for read-only queries if needed)
3. In n8n, create a **Supabase credential** using the Project URL and service_role key

### 2.2 Schema

Run the following in the Supabase **SQL Editor**:

```sql
-- ============================================================
-- GARMIN AI COACH — DATABASE SCHEMA
-- ============================================================

-- Daily wellness snapshot (one row per day)
CREATE TABLE daily_wellness (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    date            DATE NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    -- HRV
    hrv_weekly_avg          NUMERIC(5,1),   -- 7-day average (ms)
    hrv_last_night          NUMERIC(5,1),   -- last night value (ms)
    hrv_status              TEXT,           -- 'BALANCED', 'UNBALANCED', etc.
    hrv_feedback            TEXT,           -- Garmin's text feedback

    -- Sleep
    sleep_duration_h        NUMERIC(4,2),   -- total sleep in hours
    sleep_score             INTEGER,        -- Garmin sleep score 0-100
    sleep_deep_pct          NUMERIC(4,1),   -- % deep sleep
    sleep_rem_pct           NUMERIC(4,1),   -- % REM sleep
    sleep_light_pct         NUMERIC(4,1),   -- % light sleep
    sleep_awake_pct         NUMERIC(4,1),   -- % awake

    -- Recovery
    body_battery_wake       INTEGER,        -- body battery on waking (0-100)
    body_battery_sleep_gain INTEGER,        -- charged during sleep
    resting_hr              INTEGER,        -- resting HR (bpm)
    stress_avg              INTEGER,        -- average stress (0-100)
    stress_max              INTEGER,        -- peak stress

    -- Respiration
    spo2_avg                NUMERIC(4,1),   -- average SpO2 %
    spo2_min                NUMERIC(4,1),
    respiration_avg         NUMERIC(4,1),   -- breaths per minute

    -- Raw JSON from Garmin for debugging
    raw_json                JSONB
);

-- Activity log (one row per recorded activity)
CREATE TABLE activities (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    garmin_id       BIGINT UNIQUE NOT NULL,
    date            DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    -- Identity
    activity_name   TEXT,
    activity_type   TEXT,           -- 'running', 'cycling', 'swimming', etc.
    sport_type      TEXT,

    -- Duration & distance
    duration_sec    INTEGER,
    distance_m      NUMERIC(10,1),
    elevation_gain_m NUMERIC(7,1),

    -- Pace / speed
    avg_pace_sec_per_km NUMERIC(6,1),
    avg_speed_kmh   NUMERIC(5,2),

    -- Heart rate
    avg_hr          INTEGER,
    max_hr          INTEGER,
    hr_zone_1_pct   NUMERIC(4,1),
    hr_zone_2_pct   NUMERIC(4,1),
    hr_zone_3_pct   NUMERIC(4,1),
    hr_zone_4_pct   NUMERIC(4,1),
    hr_zone_5_pct   NUMERIC(4,1),

    -- Training load
    training_stress_score   NUMERIC(6,1),   -- TSS
    aerobic_training_effect NUMERIC(3,1),   -- 0-5
    anaerobic_training_effect NUMERIC(3,1), -- 0-5
    training_load_abs       NUMERIC(8,1),   -- Garmin Training Load value

    -- Performance
    avg_power_w     INTEGER,                -- for cycling/running power
    avg_cadence     INTEGER,
    calories        INTEGER,
    vo2max_estimate NUMERIC(4,1),           -- if updated after activity

    -- Workout compliance
    planned_session TEXT,   -- what the plan called for (filled by n8n logic)
    compliance_score INTEGER, -- 0-100, computed later

    raw_json        JSONB
);

-- Daily AI analysis reports
CREATE TABLE daily_reports (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    date            DATE NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    -- Computed metrics
    acwr_7_28       NUMERIC(4,2),   -- acute:chronic workload ratio (7-day / 28-day)
    readiness_score INTEGER,         -- 0-100, derived from HRV+sleep+body battery
    weekly_tss      NUMERIC(8,1),    -- rolling 7-day TSS

    -- LLM outputs
    model_used      TEXT,            -- 'gemma-4-12b', 'gemini-2.0-flash', etc.
    biometric_analysis TEXT,         -- full analysis paragraph
    plan_comparison TEXT,            -- how actual compares to planned
    suggested_adjustment TEXT,       -- specific recommendation for today
    adjustment_type TEXT,            -- 'proceed', 'reduce', 'replace', 'rest'
    alert_flags     TEXT[],          -- ['high_acwr', 'low_hrv', 'poor_sleep', etc.]

    -- Plan snapshot (which week/day the plan was on)
    plan_week       INTEGER,
    plan_day        TEXT,
    planned_session TEXT
);

-- Weekly macro reviews (run Monday morning)
CREATE TABLE weekly_reviews (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    week_start      DATE NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    -- Volume
    total_distance_km   NUMERIC(7,1),
    total_duration_h    NUMERIC(5,1),
    total_tss           NUMERIC(8,1),
    long_run_distance_km NUMERIC(5,1),

    -- Zone distribution
    zone_1_2_pct        NUMERIC(4,1),
    zone_3_pct          NUMERIC(4,1),
    zone_4_5_pct        NUMERIC(4,1),

    -- Recovery
    avg_hrv_weekly      NUMERIC(5,1),
    avg_sleep_h         NUMERIC(4,2),
    avg_body_battery    NUMERIC(4,1),

    -- LLM analysis
    model_used          TEXT,
    week_summary        TEXT,
    training_effectiveness TEXT,
    plan_adjustment_recommendation TEXT,
    next_week_guidance  TEXT,

    -- Plan state
    phase               TEXT,        -- 'base', 'build', 'peak', 'taper', 'recovery'
    plan_week           INTEGER
);

-- Indexes for query performance
CREATE INDEX idx_daily_wellness_date ON daily_wellness(date DESC);
CREATE INDEX idx_activities_date ON activities(date DESC);
CREATE INDEX idx_activities_type ON activities(activity_type);
CREATE INDEX idx_daily_reports_date ON daily_reports(date DESC);
CREATE INDEX idx_weekly_reviews_week ON weekly_reviews(week_start DESC);

-- Helper view: 28-day rolling load for ACWR
CREATE VIEW v_acwr AS
SELECT
    date,
    AVG(training_stress_score) FILTER (WHERE date >= CURRENT_DATE - INTERVAL '7 days')
        OVER (ORDER BY date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS acute_7d,
    AVG(training_stress_score) FILTER (WHERE date >= CURRENT_DATE - INTERVAL '28 days')
        OVER (ORDER BY date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS chronic_28d
FROM activities;
```

### 2.3 Row Level Security (RLS)

Since this is a personal project using the service_role key in n8n, RLS can remain disabled. If you later expose any data via a web interface, enable it:

```sql
ALTER TABLE daily_wellness ENABLE ROW LEVEL SECURITY;
ALTER TABLE activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_reports ENABLE ROW LEVEL SECURITY;
-- Add policies as needed for authenticated access
```

---

## Part 3 — Python Garmin Fetch Script

### 3.1 Dependencies

`scripts/requirements.txt`:
```
garminconnect>=0.2.19
python-dotenv>=1.0.0
```

### 3.2 `.env` file (at repo root or scripts/)

```bash
GARMIN_EMAIL=your@email.com
GARMIN_PASSWORD=yourpassword
```

### 3.3 `scripts/garmin_fetch.py`

```python
#!/usr/bin/env python3
"""
Fetches the past 24 hours of Garmin health data and outputs JSON to stdout.
Called by n8n's Execute Command node every morning.
"""

import garminconnect
import json
import sys
from datetime import date, timedelta
from dotenv import load_dotenv
import os

load_dotenv()

EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")

def safe_get(fn, *args, default=None):
    try:
        return fn(*args)
    except Exception:
        return default

def main():
    today = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))

    client = garminconnect.Garmin(EMAIL, PASSWORD)
    client.login()

    result = {
        "fetch_date": today,
        "hrv":          safe_get(client.get_hrv_data, today),
        "sleep":        safe_get(client.get_sleep_data, today),
        "stress":       safe_get(client.get_stress_data, today),
        "body_battery": safe_get(client.get_body_battery, today),
        "resting_hr":   safe_get(client.get_rhr_day, today),
        "spo2":         safe_get(client.get_spo2_data, today),
        "respiration":  safe_get(client.get_respiration_data, today),
        "activities":   safe_get(client.get_activities, 0, 5),  # last 5
        "training_status": safe_get(client.get_training_status, today),
        "training_load":   safe_get(client.get_training_load, today),
    }

    print(json.dumps(result))
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

Test manually before wiring into n8n:
```bash
cd scripts
pip install -r requirements.txt
python garmin_fetch.py | python -m json.tool | head -100
```

---

## Part 4 — n8n Workflows

### 4.1 Daily Morning Workflow (07:00)

**Trigger → Fetch → Store → Compute → Prompt → LLM → Save Report → (Optional) Notify**

#### Node 1 — Schedule Trigger
- Cron: `0 7 * * *`

#### Node 2 — Execute Command (Garmin fetch)
```
python3 /home/node/scripts/garmin_fetch.py
```
- Parse stdout as JSON

#### Node 3 — Function Node (Parse + Normalise)

```javascript
const g = $input.first().json;
const sleep = g?.sleep?.dailySleepDTO ?? {};
const hrv = g?.hrv?.hrvSummary ?? {};
const bb = g?.body_battery?.[0] ?? {};
const rhr = g?.resting_hr?.restingHeartRate ?? null;
const activities = g?.activities ?? [];
const lastAct = activities[0] ?? {};

return {
  fetch_date: g.fetch_date,
  
  // HRV
  hrv_weekly_avg: hrv.weeklyAvg ?? null,
  hrv_last_night: hrv.lastNight ?? null,
  hrv_status: hrv.status ?? null,
  hrv_feedback: hrv.feedback ?? null,

  // Sleep
  sleep_duration_h: sleep.sleepTimeSeconds ? (sleep.sleepTimeSeconds / 3600).toFixed(2) : null,
  sleep_score: sleep.sleepScores?.overall?.value ?? null,
  sleep_deep_pct: sleep.deepSleepSeconds && sleep.sleepTimeSeconds
    ? ((sleep.deepSleepSeconds / sleep.sleepTimeSeconds) * 100).toFixed(1) : null,

  // Recovery
  body_battery_wake: bb.charged ?? null,
  resting_hr: rhr,
  stress_avg: g?.stress?.avgStressLevel ?? null,

  // Last activity
  last_activity_name: lastAct.activityName ?? null,
  last_activity_tss: lastAct.trainingStressScore ?? null,
  last_activity_type: lastAct.activityType?.typeKey ?? null,
  last_activity_date: lastAct.startTimeLocal?.split('T')[0] ?? null,

  // Raw for Supabase
  raw_json: g
};
```

#### Node 4 — Supabase Node (Upsert daily_wellness)
- **Resource:** Row  
- **Operation:** Create (use `ON CONFLICT` via Upsert if available, or use HTTP Request node for upsert):

```bash
# Via HTTP Request node for upsert support:
# POST https://YOUR_PROJECT.supabase.co/rest/v1/daily_wellness
# Header: Prefer: resolution=merge-duplicates
```

Map all normalised fields to the corresponding columns.

#### Node 5 — Supabase Node (Fetch recent activities for ACWR)

Query the `activities` table for the past 35 days to build context for ACWR:

```sql
select date, training_stress_score, activity_type 
from activities 
where date >= NOW() - INTERVAL '35 days'
order by date desc
```

#### Node 6 — Function Node (Build LLM Prompt)

```javascript
const d = $('Parse + Normalise').first().json;
const recentActs = $('Fetch recent activities').all()
  .map(a => a.json)
  .filter(a => a.training_stress_score);

// Compute rolling TSS
const now = new Date(d.fetch_date);
const acute = recentActs
  .filter(a => (now - new Date(a.date)) / 86400000 <= 7)
  .reduce((s, a) => s + (a.training_stress_score || 0), 0) / 7;
const chronic = recentActs
  .filter(a => (now - new Date(a.date)) / 86400000 <= 28)
  .reduce((s, a) => s + (a.training_stress_score || 0), 0) / 28;
const acwr = chronic > 0 ? (acute / chronic).toFixed(2) : null;

// Read training plan (injected by previous node or hardcoded path reference)
const plan = $('Read Training Plan').first()?.json?.content ?? '[training plan not available]';

const prompt = `You are an expert endurance coach analysing daily biometric data for an experienced marathon runner (current PB: 1:34 HM, goal: sub-3 marathon). 

## TODAY'S BIOMETRICS (${d.fetch_date})

**HRV:**
- Last night: ${d.hrv_last_night ?? 'N/A'} ms
- 7-day average: ${d.hrv_weekly_avg ?? 'N/A'} ms
- Status: ${d.hrv_status ?? 'N/A'}
- Garmin feedback: ${d.hrv_feedback ?? 'N/A'}

**Sleep:**
- Duration: ${d.sleep_duration_h ?? 'N/A'} hours
- Score: ${d.sleep_score ?? 'N/A'} / 100
- Deep sleep: ${d.sleep_deep_pct ?? 'N/A'}%

**Recovery:**
- Body Battery on waking: ${d.body_battery_wake ?? 'N/A'} / 100
- Resting HR: ${d.resting_hr ?? 'N/A'} bpm
- Average stress: ${d.stress_avg ?? 'N/A'} / 100

**Training Load:**
- Acute:Chronic Workload Ratio (7d/28d TSS): ${acwr ?? 'insufficient data'}
- Last session: ${d.last_activity_name ?? 'N/A'} on ${d.last_activity_date ?? 'N/A'} (TSS: ${d.last_activity_tss ?? 'N/A'})

## ACTIVE TRAINING PLAN

${plan}

## YOUR TASK

Respond with exactly four sections:

**1. BIOMETRIC ANALYSIS**
Interpret today's data. Flag any concerning patterns (ACWR > 1.3, HRV drop > 10% from 7d avg, body battery < 30, sleep < 6h). Be specific.

**2. PLAN COMPARISON**
What does the training plan call for today? How do today's metrics align with that session?

**3. RECOMMENDATION**
Choose one: PROCEED AS PLANNED / REDUCE INTENSITY / REPLACE WITH EASY / REST DAY
Justify with the specific metrics that drove this decision.

**4. ALERT FLAGS**
List any flags as bullet points, or write "None" if all markers are normal.

Keep your total response under 600 words. Be direct and data-driven.`;

return { prompt, acwr, acute_tss: acute.toFixed(1), chronic_tss: chronic.toFixed(1) };
```

#### Node 7 — HTTP Request Node (LM Studio)
- **URL:** `http://host.docker.internal:1234/v1/chat/completions`

> **Important:** Inside Docker, `localhost` refers to the container. Use `host.docker.internal` (macOS) to reach LM Studio on your Mac host.

```json
{
  "model": "google/gemma-4-12b",
  "messages": [{"role": "user", "content": "{{ $json.prompt }}"}],
  "temperature": 0.35,
  "max_tokens": 900
}
```

#### Node 7b — IF Node (LM Studio failed?)

If Node 7 returns an error or empty response, route to the Gemini fallback (Node 7c), otherwise continue.

#### Node 7c — HTTP Request Node (Gemini fallback)
- **URL:** `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={{ $env.GEMINI_API_KEY }}`

#### Node 8 — Supabase Node (Save to daily_reports)

Extract the LLM response text and save:
- `date`, `acwr_7_28`, `readiness_score` (derive from HRV + sleep + body battery: simple average normalised 0–100), `model_used`, `biometric_analysis`, `plan_comparison`, `suggested_adjustment`, `adjustment_type`, `plan_week`, `planned_session`

#### Node 9 — Write File Node (Optional: save MD report to repo)

Write to `reports/YYYY-MM-DD.md` for historical reference. This makes reports available in agy sessions.

### 4.2 Weekly Review Workflow (Monday 08:00)

A separate workflow triggered Monday morning that:
1. Queries `activities` and `daily_wellness` for the past 7 days from Supabase
2. Computes weekly aggregates (total TSS, zone distribution, avg HRV, avg sleep)
3. Reads `training/plan.md` to compare planned vs actual week
4. Sends a longer prompt to the LLM requesting a weekly effectiveness analysis
5. Saves to `weekly_reviews` table
6. Optionally updates `training/plan.md` via a `Write File` node if the LLM recommends a plan adjustment (with a clear `<!-- AI SUGGESTED: ... -->` annotation)

---

## Part 5 — Training Plan Format

The plan lives at `training/plan.md` and uses a structured format the LLM can reliably parse:

```markdown
# Training Plan — Marathon Build Phase
**Phase:** Base 2  
**Current Week:** 4 of 16  
**Target Race:** [Race Name, Date]  
**Weekly TSS Target:** 420–460

## Week 4 (Mon 16 Jun – Sun 22 Jun)

| Day | Session | Type | Duration | Target HR/Pace | TSS est. |
|-----|---------|------|----------|----------------|---------|
| Mon | Recovery jog | Z1-2 | 40 min | < 140 bpm | 35 |
| Tue | Tempo intervals | Z3-4 | 55 min | 4:20–4:30/km | 75 |
| Wed | REST | — | — | — | — |
| Thu | Easy aerobic | Z2 | 65 min | 140–148 bpm | 55 |
| Fri | REST or mobility | — | 30 min | — | 10 |
| Sat | Long run | Z2 | 100 min | 5:30–5:45/km | 90 |
| Sun | Easy recovery | Z1 | 45 min | < 138 bpm | 35 |

**Week notes:** First week of increased long run volume. Priority is the Saturday long run. 
Tuesday tempo can be shortened to 40 min if HRV is below weekly average.
```

The n8n workflow reads this file with a **Read Binary File** node mounted from the scripts volume, or via a Supabase storage bucket if preferred.

---

## Part 6 — agy Integration

### 6.1 AGENTS.md Section to Add

Append the following to your project's `AGENTS.md`:

```markdown
## Garmin AI Coach — Project Context

This repository implements a daily Garmin health data pipeline for training plan 
adaptation using n8n, Supabase, and a local LLM (LM Studio).

**Key files:**
- `training/plan.md` — Active training plan (living document; AI may annotate it)
- `reports/` — Daily AI coaching reports (YYYY-MM-DD.md)
- `scripts/garmin_fetch.py` — Garmin data fetcher (python-garminconnect)
- `n8n/workflows/` — n8n workflow JSON exports
- `supabase/schema.sql` — Full database schema

**Stack:**
- n8n (Docker, port 5678) — orchestration
- LM Studio (port 1234) — local LLM inference (gemma-4-12b primary)
- Google Gemini (HTTP) — cloud fallback via Google Workspace API key
- Supabase — PostgreSQL storage for wellness, activities, and reports

**Daily workflow:** Runs at 07:00. Fetches Garmin data → upserts to Supabase → 
builds ACWR + readiness context → calls LLM → saves report to `reports/` and Supabase.

**Weekly workflow:** Runs Monday 08:00. Aggregates week's data → full plan review → 
may annotate `training/plan.md` with suggested adjustments.

### Skill Routing (kisune dev-workflow)

For planning, specification, review, debugging, or any multi-step workflow task:

1. Read `@using-kisune` to identify the correct skill, OR match manually:
   - Planning / spec writing       → `@spec-driven-planning`
   - Task breakdown / implement    → `@spec-driven-implementation`
   - Reviewing a spec              → `@spec-review`
   - Debugging                     → `@systematic-debug`
   - Git operations                → `@git-workflow`
   - Security audit                → `@security-review`
   - TDD                           → `@test-driven-development`
   - Code review                   → `@review`
   - Brainstorming                 → `@brainstorming`
   - Scrutinizing a decision       → `@scrutinize`
   - Parallel agent work           → `@spawn-agents`
   - Completion validation         → `@completion-validation`
   - Creating a new skill          → `@skill-maker`

2. Before executing, state: "I'll use **@skill-name** — [reason]." and wait for confirmation.

3. For simple edits, lookups, and quick questions: proceed without confirmation.

Full kisune setup reference: `.agents/kisune-agy-setup.md`
```

### 6.2 Useful agy Prompts for This Project

```
# Plan a new n8n workflow feature using spec-driven planning:
"Use @spec-driven-planning to design the weekly review n8n workflow in Full mode."

# Debug a failing garmin_fetch.py run:
"Use @systematic-debug to investigate why garmin_fetch.py returns null for HRV data."

# Review the Supabase schema:
"Use @spec-review to review supabase/schema.sql — check completeness and 
correctness for ACWR calculations."

# Brainstorm prompt improvements:
"Use @brainstorming to explore ways to make the daily LLM prompt more effective 
for periodisation-aware training recommendations."

# After implementing a new feature:
"Use @completion-validation to verify the weekly review workflow is complete."
```

---

## Part 7 — Implementation Sequence

Follow this sequence to avoid dependency issues:

1. **[Day 1]** Set up Supabase project → run `schema.sql` → confirm tables exist
2. **[Day 1]** Install Python deps → test `garmin_fetch.py` manually → confirm JSON output
3. **[Day 1]** Verify n8n Docker is running at port 5678 → update image if needed
4. **[Day 1]** Mount `scripts/` volume in Docker → test Execute Command node in n8n
5. **[Day 2]** Build daily n8n workflow step by step (Nodes 1–5 first, no LLM yet) → confirm data reaches Supabase
6. **[Day 2]** Load gemma-4-12b in LM Studio → test `http://host.docker.internal:1234/v1/chat/completions` from n8n
7. **[Day 3]** Add Nodes 6–8 (prompt + LLM + report save) → do a manual test run
8. **[Day 3]** Create `training/plan.md` using the structured format → wire Read File node
9. **[Day 4]** Let the daily trigger run for the first time automatically at 07:00
10. **[Day 5–7]** Review first reports → tune prompt temperature and length
11. **[Week 2]** Build weekly review workflow after 7 days of data accumulate
12. **[Week 4+]** ACWR becomes reliable once 28 days of TSS data exist in Supabase

---

## Part 8 — Known Limitations and Mitigations

| Issue | Cause | Mitigation |
|---|---|---|
| Garmin login fails occasionally | Session token expires | Wrap `client.login()` in retry logic (3 attempts, 30s delay) |
| HRV data missing some mornings | Watch not worn all night | `safe_get()` wrapper returns null; prompt handles null values gracefully |
| LM Studio inference slow | Large context or model loading | Pre-warm model; use `host.docker.internal` not `localhost`; keep model in memory |
| ACWR unreliable in first 28 days | Insufficient history | Add `IF chronic_tss < 10 THEN skip ACWR` gate in Function node |
| Training plan drift | Manual edits to `plan.md` | Include a plan version header; agy can track diffs via `@git-workflow` |
| Supabase free tier row limits | Free tier: 500 MB | Schema stores ~1 KB/day; 500 MB ≈ 500 years of daily data. Not an issue. |

---

## Part 9 — Prompt Engineering Notes

The daily prompt has been designed with these expert coaching principles:

- **HRV delta**, not absolute value, is the meaningful signal. A 55 ms HRV is fine for one athlete and alarming for another. Always include the 7-day average so the model can compute the deviation.[cite:40]
- **Body Battery below 30 on waking** is the clearest single-metric "rest day" flag. It reflects accumulated physiological debt that HRV alone may miss.[cite:39]
- **ACWR between 0.8 and 1.3** is the safe training zone. The model should flag anything above 1.3 explicitly, as this is the injury risk threshold supported by sports science literature.[cite:48]
- **Temperature 0.35** keeps coaching advice consistent and conservative. Higher temperatures introduce creative plan changes that aren't warranted by the data.
- **600-word response cap** prevents the model from being verbose. Coaching advice that requires 1,500 words is usually uncertain coaching advice.

---

## Quick-Reference Checklist

```
[ ] Supabase project created, schema.sql executed, credentials in n8n
[ ] garmin_fetch.py tested manually, outputs valid JSON
[ ] n8n Docker updated to latest, scripts/ volume mounted
[ ] LM Studio running, gemma-4-12b loaded, server enabled on port 1234
[ ] host.docker.internal resolves from n8n container (test with HTTP Request node)
[ ] Gemini API key added as n8n environment variable
[ ] Daily workflow built and tested with manual execution
[ ] training/plan.md created with structured table format
[ ] reports/ directory exists in repo
[ ] AGENTS.md updated with project context and kisune routing block
[ ] First automated run reviewed (Day 5 morning)
[ ] Weekly review workflow built after 7 days of data
```
