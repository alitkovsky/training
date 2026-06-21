# Daily Garmin Coaching Analysis

<!--
COACHING PRINCIPLES:
- HRV delta vs 7-day average matters more than the absolute value.
  A 55 ms HRV is fine for one athlete and alarming for another.
- Body Battery < 30 on waking = clearest single-metric rest-day flag.
  It reflects accumulated physiological debt that HRV alone may miss.
- ACWR 0.8–1.3 is the safe zone. Flag > 1.3 explicitly (injury risk threshold).
  ACWR is unreliable until 28 days of TSS data exist — skip the flag until then.
- The plan is a ceiling, not a floor — AI recommends reduction, not invention.
- Zone distribution review is weekly (Monday), not daily.
- Keep total response under 600 words. Be direct and data-driven.
-->

## Data Access

All data lives in the Supabase `training` schema. Use the Supabase MCP tools.

**Step 1 — Find the project.** Call `list_projects` and select the project that contains the `training` schema (tables: daily_wellness, activities, daily_reports).

**Step 2 — Get today's date.** Run `date +%Y-%m-%d`.

**Step 3 — Fetch today's wellness row.**
```sql
SELECT * FROM training.daily_wellness WHERE date = CURRENT_DATE;
```
→ If empty: write `reports/YYYY-MM-DD.md` with "No wellness data yet — Garmin sync may not have completed." and stop.

**Step 4 — Fetch 28-day wellness trend.**
```sql
SELECT date, hrv_last_night, hrv_weekly_avg, sleep_duration_h, sleep_score,
       body_battery_wake, body_battery_sleep_gain, resting_hr, stress_avg, spo2_avg
FROM training.daily_wellness
WHERE date >= CURRENT_DATE - INTERVAL '28 days'
ORDER BY date;
```

**Step 5 — Fetch last 7 days of activities.**
```sql
SELECT date, activity_type, duration_sec, distance_m, avg_hr,
       training_stress_score, aerobic_training_effect,
       hr_zone_1_pct, hr_zone_2_pct, hr_zone_3_pct, hr_zone_4_pct, hr_zone_5_pct
FROM training.activities
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY date;
```

**Step 6 — Check ACWR** (returns NULL if < 28 days of data — skip `high_acwr` flag if NULL).
```sql
SELECT acwr, acute_7d, chronic_28d FROM training.v_acwr WHERE date = CURRENT_DATE;
```

**Step 7 — Fetch today's weather forecast.**
```sql
SELECT temp_max_c, feels_like_max_c, precipitation_prob_pct,
       wind_speed_kmh, uv_index_max, weather_description
FROM training.weather_forecast WHERE date = CURRENT_DATE;
```
→ If available, factor heat/rain/wind into the recommendation. `feels_like_max_c > 28` = heat flag.
   `uv_index_max >= 8` = high UV warning. Missing row = no forecast yet (skip silently).

**Step 8 — Check upcoming races.**
```sql
SELECT name, date, distance_m, race_type, goal_time_sec,
       date - CURRENT_DATE AS days_out
FROM training.races
WHERE date >= CURRENT_DATE
ORDER BY date
LIMIT 3;
```
→ If a race is within 14 days, that overrides the standard recommendation (taper logic).

**Step 9 — Read the training plan.** Read `training/plan.md` to find today's planned session.

---

## Report Structure

Write the report to `reports/YYYY-MM-DD.md` using exactly this structure:

---

## Daily Coaching Report — {{DATE}}

**RECOMMENDATION:** [PROCEED AS PLANNED / REDUCE INTENSITY / REPLACE WITH EASY / REST DAY]

---

### 1. BIOMETRIC ANALYSIS

Interpret today's data. For each metric, state the value and what it means in context:

- **HRV:** [last night] ms (7d avg: [avg] ms, delta: [+/-X]%) — [interpretation]
- **Sleep:** [duration]h, score [score]/100, deep [deep_pct]% — [interpretation]
- **Body Battery:** [value]/100 on waking — [interpretation]
- **Resting HR:** [value] bpm — [interpretation]
- **ACWR:** [value] (acute 7d TSS / chronic 28d TSS) — [safe / elevated / high risk]
- **Weather:** [temp_max_c]°C / feels like [feels_like_max_c]°C, [weather_description], UV [uv_index_max] — [heat/wind/rain impact]

Flag explicitly if:
- ACWR > 1.3 (injury risk zone)
- HRV drop > 10% below 7-day average
- Body Battery < 30 on waking
- Sleep < 6 hours or score < 60
- feels_like_max_c > 28°C (heat stress — reduce intensity, shift to early morning)
- uv_index_max >= 8 (high UV — early morning or indoor session recommended)
- Race within 14 days (taper flag)

### 2. PLAN COMPARISON

What does the training plan call for today? How do today's metrics align with that session?
State the planned session explicitly (type, duration, target HR/pace, TSS estimate).

### 3. RECOMMENDATION

State ONE of: **PROCEED AS PLANNED** / **REDUCE INTENSITY** / **REPLACE WITH EASY** / **REST DAY**

Justify with the specific metric(s) that drove the decision. If reducing or replacing,
state the modified session concretely (e.g., "Replace tempo with 40 min Z1 jog, HR < 138").

### 4. ALERT FLAGS

List any flags as bullet points. Write "None — all markers normal." if everything is fine.

Possible flags: `high_acwr`, `low_hrv`, `poor_sleep`, `low_body_battery`,
`elevated_resting_hr`, `high_stress`, `low_spo2`, `insufficient_acwr_data`,
`heat_stress`, `high_uv`, `race_taper`

---

## Save to Supabase

After writing the report file, upsert to `training.daily_reports`:

Fields to populate:
- `date` — today
- `readiness_score` — integer 0–100 reflecting overall recovery state
- `adjustment_type` — one of: `proceed` / `reduce` / `replace` / `rest`
- `alert_flags` — text array of flag strings
- `suggested_adjustment` — one concise sentence with the specific recommendation
- `report_md` — full markdown report text
- `model_used` — `'claude-sonnet-4-6'`

Use `ON CONFLICT (date) DO UPDATE SET ...` to handle re-runs.

---

*Report generated by Claude Code scheduled agent (claude-sonnet-4-6) from Garmin Connect data via n8n + Supabase pipeline.*
