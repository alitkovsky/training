The main plan is in `garmin-coach-master-plan.md`. It is the most recent, but still need some data from the previous plan in `garmin-ai-training-coach.md`. Use only listed down items from the old plan `garmin-ai-training-coach.md`.

What to Keep from the Old Plan
Yes — take these pieces wholesale, they are thorough and not duplicated in the master plan:
1 — The Full Supabase Schema ( supabase/schema.sql )
The master plan mentions the schema but doesn’t reproduce it. The old plan has the complete, production-quality schema with all columns, indexes, and the ACWR view. Keep everything — just add the  training.  schema prefix to each  CREATE TABLE  statement since your DB already has an existing schema, and add the  training.workouts  table from the master plan:

```sql
-- at the top of schema.sql:
CREATE SCHEMA IF NOT EXISTS training;

-- then all tables become:
CREATE TABLE training.daily_wellness (...)
CREATE TABLE training.activities (...)
CREATE TABLE training.daily_reports (...)
CREATE TABLE training.weekly_reviews (...)
CREATE VIEW training.v_acwr AS ...

-- add from master plan Phase 5:
CREATE TABLE training.workouts (...)
```

2 —  garmin_fetch.py  (the complete script)
The master plan references the script but doesn’t contain it. The old plan has the full working implementation with  safe_get()  wrappers, all API calls, and the JSON structure. Copy it verbatim — it’s solid.
3 — The n8n Normalise Function Node (Node 3 JavaScript)
The old plan has the complete JS normalisation code that parses Garmin’s nested JSON into flat columns. The master plan omits this detail. You’ll need it when building Phase 1, Step 1.5.
4 — The Training Plan Format ( training/plan.md )
The old plan has the exact structured Markdown table format with the correct column headers that the prompt template expects. Use it as your template.
5 — Prompt Engineering Notes (Part 9 of old plan)
The coaching rationale — HRV delta vs absolute, Body Battery < 30 as a rest-day flag, temperature 0.35, 600-word cap — is valuable expert context. Add it to  prompts/daily-analysis.md  as a comment block or to  AGENTS.md  as a coaching principles section.
6 — Known Limitations Table (Part 8 of old plan)
The  host.docker.internal  detail (for n8n to reach LM Studio) and the ACWR 28-day warmup gate logic are things you’d rediscover the hard way. Move both into the master plan’s Phase 6 polish checklist.
---
What to Drop from the Old Plan

Old Plan Element -> Why Drop It
LM Studio setup (Part 1.2) -> Replaced by Antigravity/agy
Gemini HTTP fallback node (Node 7b/7c) -> Antigravity handles model selection internally
Node 6 build-prompt JS in n8n -> Promptlives in `prompts/daily-analysis.md` now
Node 7 HTTP Request to LM Studio -> Antigravity is the LLM caller now
Node 8 Supabase save from n8n -> agy writes `reports/`, n8n reads and saves to Supabase after
`model_used` field in `daily_reports`
Still useful - keep it, just default to `claude-sonnet-agy`

---
`agy -p “$(cat prompts/daily-analysis.md)”`:

```
Or in Antigravity IDE: `Read prompts/daily-analysis.md and execute the coaching analysis.`

**Coaching principles for agy sessions:**
- HRV delta vs 7-day average matters more than the absolute value
- Body Battery < 30 on waking = clearest single-metric rest-day flag
- ACWR 0.8–1.3 is the safe zone; flag > 1.3 explicitly (injury risk)
- The plan is a ceiling, not a floor — AI recommends reduction, not invention
- Zone distribution review is weekly (Monday), not daily

## Skill Routing (kisune dev-workflow)

For planning, specification, review, debugging, or any multi-step workflow task:

1. Read `@using-kisune` to identify the correct skill, OR match manually:
   - Planning / spec writing     → `@spec-driven-planning`
   - Task breakdown / implement  → `@spec-driven-implementation`
   - Reviewing a spec            → `@spec-review`
   - Debugging                   → `@systematic-debug`
   - Git operations              → `@git-workflow`
   - Security audit              → `@security-review`
   - TDD                         → `@test-driven-development`
   - Code review                 → `@review`
   - Brainstorming               → `@brainstorming`
   - Scrutinizing a decision     → `@scrutinize`
   - Parallel agent work         → `@spawn-agents`
   - Completion validation       → `@completion-validation`
   - Creating a new skill        → `@skill-maker`

2. Before executing, state: "I'll use **@skill-name** — [reason]." and wait for confirmation.
3. For simple edits, lookups, and quick questions: proceed without confirmation.

```