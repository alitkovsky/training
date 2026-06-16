## Garmin AI Coach — Project Context

This repository implements a daily Garmin health data pipeline for training plan
adaptation using n8n, Supabase, and Antigravity (agy) as the AI analysis layer.

**Key files:**
- `training/plan.md`           — Active training plan (living document; AI may annotate)
- `prompts/daily-analysis.md`  — agy daily coaching prompt template
- `prompts/weekly-review.md`   — agy Monday weekly review prompt
- `data/today.json`            — Ephemeral daily biometric data written by n8n (gitignored)
- `reports/`                   — Daily and weekly AI coaching reports (versioned)
- `scripts/garmin_fetch.py`    — Garmin data fetcher (python-garminconnect)
- `supabase/schema.sql`        — Full database schema

**Stack:**
- n8n (Docker, port 5678) — data pipeline only (no LLM nodes)
- python-garminconnect — Garmin Health API client
- Supabase (training schema) — PostgreSQL storage for wellness, activities, reports
- Antigravity/agy — AI coaching analysis via Claude Sonnet (Workspace quota)
- Telegram Bot — report delivery + command control (via n8n Telegram node)

**Daily automated flow:**
1. 07:50 — iOS Shortcut opens Garmin Connect on iPhone → triggers BT sync
2. 08:05 — n8n: fetch Garmin data → upsert Supabase → write data/today.json
3. 08:15 — agy Scheduled Task: read data/today.json + training/plan.md →
            coaching analysis → write reports/YYYY-MM-DD.md
4. 08:20 — n8n: read report → save to training.daily_reports → send to Telegram

**Manual agy trigger:**
```
agy -p "$(cat prompts/daily-analysis.md)"
```
Or in Antigravity IDE: `Read prompts/daily-analysis.md and execute the coaching analysis.`

**Coaching principles for agy sessions:**
- HRV delta vs 7-day average matters more than the absolute value
- Body Battery < 30 on waking = clearest single-metric rest-day flag
- ACWR 0.8–1.3 is the safe zone; flag > 1.3 explicitly (injury risk)
- ACWR is unreliable until 28 days of data exist — skip ACWR flagging during warmup
- The plan is a ceiling, not a floor — AI recommends reduction, not invention
- Zone distribution review is weekly (Monday), not daily
- Temperature 0.35 / 600-word cap on daily reports

## Dev-Workflow Skills (kisune)

Spec-driven development uses the kisune dev-workflow skills installed at `.agents/skills/`.
Full installation and usage reference: `.agents/kisune-agy-setup.md`.

### Skill Routing

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

To start any spec workflow: "Use @spec-driven-planning to plan feature X."
Full command-to-prompt mappings: see `.agents/kisune-agy-setup.md §4`.
