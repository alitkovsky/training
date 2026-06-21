# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Python environment (local dev/testing only — production uses the garmin-api Docker sidecar)
cd scripts
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Test Garmin data fetch locally (outputs JSON to stdout)
python garmin_fetch.py
python garmin_fetch.py | python -m json.tool   # pretty-print

# Run historical bulk import (2026-01-01 to yesterday)
python garmin_bulk_import.py
python garmin_bulk_import.py --dry-run         # preview without DB writes
python garmin_bulk_import.py --from 2026-03-01 --to 2026-04-01

# Docker (compose file lives at ~/n8n-local/compose.yaml, NOT in this repo)
/usr/local/bin/docker ps                                          # check running containers
cd ~/n8n-local && /usr/local/bin/docker compose up -d             # start/restart all services
cd ~/n8n-local && /usr/local/bin/docker compose build garmin-api  # rebuild after Dockerfile changes

# Test the garmin-api sidecar
curl http://localhost:8765/health
curl http://localhost:8765/fetch | python3 -m json.tool

# Trigger daily analysis manually (runs the Claude Code scheduled agent now)
# → claude.ai/code/routines → find "Garmin Daily Coaching Analysis" → Run now
```

## Architecture

**Daily automated flow (08:05–08:20):**
```
iPhone 07:50       → iOS Shortcut opens Garmin Connect → Bluetooth sync
n8n 08:05          → garmin-api:8765/fetch → normalise → Supabase upsert → save data/today.json
Claude Code 08:15  → scheduled cloud agent reads Supabase → claude-sonnet-4-6 analysis
                   → writes reports/YYYY-MM-DD.md → upserts training.daily_reports
n8n 08:20          → reads training.daily_reports → sends to Telegram (Phase 3)
```

**AI analysis stack:** A Claude Code cloud routine (scheduled at claude.ai/code/routines) runs the prompt in `prompts/daily-analysis.md` every day at 08:15. The agent uses the Supabase MCP to read wellness/activity data and upsert the structured report. No Anthropic SDK or local Python required for the AI step.

**garmin-api sidecar:** n8n's Docker image (DHI Alpine, no package manager) cannot run Python. A separate `garmin-api` container (`scripts/Dockerfile`, `python:3.12-alpine`) exposes HTTP at port 8765. n8n calls it via HTTP Request → `http://garmin-api:8765/fetch` and `/analyze`. Both containers defined in `~/n8n-local/compose.yaml`. The repo root is bind-mounted at `/training` in garmin-api.

**Garmin sync limitation:** No API sync trigger exists. iOS Shortcut opens Garmin Connect at 07:50 for Bluetooth sync. Phase 4 adds retry logic (3 attempts × 15 min) with Telegram alert.

## Database (Supabase — `training` schema)

Schema at `supabase/schema.sql`. All tables use `training.` prefix (not `public`). REST API calls need `Content-Profile: training` header and `Prefer: resolution=merge-duplicates` for upserts.

Key tables:
- `training.daily_wellness` — one row per day, morning biometric snapshot (HRV, sleep, body battery, stress, SpO2)
- `training.activities` — one row per Garmin activity with HR zones, TSS, training load
- `training.daily_reports` — structured LLM output fields + full `report_md` text
- `training.weekly_reviews` — Monday weekly macro analysis
- `training.v_acwr` — view computing 7-day/28-day rolling workload ratio; returns NULL until 28 days of data exist (gate: `chronic_28d < 10 TSS/day`)

## Coaching Domain Rules

- **HRV:** Delta vs 7-day average matters more than absolute value
- **Body Battery < 30** on waking = clearest single-metric rest-day flag
- **ACWR safe zone:** 0.8–1.3; flag > 1.3 as injury risk. Skip ACWR flagging for first 28 days
- **Plan is a ceiling:** AI recommends reduction, not invention of new sessions
- **Zone distribution** reviewed weekly (Monday), not daily

## AI Analysis

`prompts/daily-analysis.md` — the complete prompt for the Claude Code scheduled cloud agent. Includes Supabase SQL queries to fetch wellness/activity data, the coaching framework, report structure, and instructions to upsert results to `training.daily_reports`. The cloud agent reads this file from the repo at runtime.

`prompts/weekly-review.md` — Monday weekly review prompt (Phase 6).

**Scheduled agent:** Runs daily at 08:15 Europe/Berlin via claude.ai/code/routines. Uses the Supabase MCP connector. DST-aware: fires at both 06:15 and 07:15 UTC (`15 6,7 * * *`), skips automatically if Berlin local hour ≠ 08. Routine ID: `trig_01QxCuyeTcQmN7pivzA2PWJX`. View/run at: https://claude.ai/code/routines/trig_01QxCuyeTcQmN7pivzA2PWJX

`training/plan.md` — living document. AI annotations go below `## AI Annotations`. Do not reformat the Markdown table — prompt template depends on it.

## n8n Workflow

Importable JSON at `n8n/workflows/01-daily-data-pipeline.json`. Import via n8n UI → Workflows → Import. The workflow reads `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from the container's process.env (set via garmin-api's env_file in compose.yaml).

## Phase Status

- **Phase 1.1** (Supabase schema) — ✅ complete
- **Phase 1.2** (Python env + credentials) — ✅ complete
- **Phase 1.3** (Historical bulk import) — ✅ `scripts/garmin_bulk_import.py` built
- **Phase 1.4** (n8n Docker + garmin-api sidecar) — ✅ complete
- **Phase 1.5** (n8n daily workflow JSON) — ✅ `n8n/workflows/01-daily-data-pipeline.json` built
- **Phase 2** (Claude Code scheduled analysis) — cloud routine created at claude.ai/code/routines; needs today's Supabase data + first run test
- **Phase 3–6** — not started

See `garmin-coach-master-plan.md` for full phased implementation details.
