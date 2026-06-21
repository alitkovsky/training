## Garmin AI Coach — Project Context

This repository implements a daily Garmin health data pipeline for training plan
adaptation using n8n, Supabase, and the Claude API (claude-opus-4-8) as the AI analysis layer.

**Key files:**
- `training/plan.md`              — Active training plan (living document; AI may annotate)
- `prompts/daily-analysis.md`     — Coaching context for daily_analysis.py
- `prompts/weekly-review.md`      — Monday weekly review prompt
- `data/today.json`               — Ephemeral daily biometric data written by garmin-api (gitignored)
- `reports/`                      — Daily and weekly AI coaching reports (versioned)
- `scripts/garmin_fetch.py`       — Garmin data fetcher (python-garminconnect)
- `scripts/garmin_api.py`         — HTTP sidecar: /fetch, /health
- `scripts/garmin_bulk_import.py` — Historical data backfill from 2026-01-01
- `supabase/schema.sql`           — Full database schema

**Stack:**
- n8n (Docker, port 5678) — data pipeline only (no LLM nodes)
- python-garminconnect — Garmin Health API client
- Supabase (training schema) — PostgreSQL storage for wellness, activities, reports
- Claude Code cloud routine (claude-sonnet-4-6) — scheduled daily analysis via claude.ai/code/routines + Supabase MCP
- Telegram Bot — report delivery + command control (via n8n Telegram node)

**Daily automated flow:**
1. 07:50 — iOS Shortcut opens Garmin Connect on iPhone → triggers BT sync
2. 08:05 — n8n: fetch Garmin data via garmin-api:8765/fetch → upsert Supabase → save data/today.json
3. 08:15 — Claude Code cloud routine: reads Supabase via MCP → coaching analysis →
            write reports/YYYY-MM-DD.md + upsert training.daily_reports
4. 08:20 — n8n: read report → send to Telegram

**Manual analysis trigger:**
Go to https://claude.ai/code/routines → "Garmin Daily Coaching Analysis" → Run now.

**Coaching principles for AI analysis:**
- HRV delta vs 7-day average matters more than the absolute value
- Body Battery < 30 on waking = clearest single-metric rest-day flag
- ACWR 0.8–1.3 is the safe zone; flag > 1.3 explicitly (injury risk)
- ACWR is unreliable until 28 days of data exist — skip ACWR flagging during warmup
- The plan is a ceiling, not a floor — AI recommends reduction, not invention
- Zone distribution review is weekly (Monday), not daily

## Dev-Workflow Skills (kisune)

Spec-driven development uses the kisune dev-workflow skills installed at `.agents/skills/`.

### Skill Routing

For planning, specification, review, debugging, or any multi-step workflow task:

1. Match manually:
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

2. Before executing, state: "I'll use **@skill-name** — [reason]." and wait for confirmation.

3. For simple edits, lookups, and quick questions: proceed without confirmation.
