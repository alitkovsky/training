-- ============================================================
-- GARMIN AI COACH — DATABASE SCHEMA
-- Schema: training (separate from public)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS training;

-- ============================================================
-- TABLE: training.daily_wellness
-- One row per day — morning biometric snapshot
-- ============================================================
CREATE TABLE training.daily_wellness (
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

-- ============================================================
-- TABLE: training.activities
-- One row per recorded activity
-- ============================================================
CREATE TABLE training.activities (
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

-- ============================================================
-- TABLE: training.daily_reports
-- Daily AI analysis reports
-- ============================================================
CREATE TABLE training.daily_reports (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    date            DATE NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    -- Computed metrics
    acwr_7_28       NUMERIC(4,2),   -- acute:chronic workload ratio (7-day / 28-day)
    readiness_score INTEGER,         -- 0-100, derived from HRV+sleep+body battery
    weekly_tss      NUMERIC(8,1),    -- rolling 7-day TSS

    -- LLM outputs
    model_used      TEXT DEFAULT 'claude-sonnet-agy',  -- 'claude-sonnet-agy', etc.
    biometric_analysis TEXT,         -- full analysis paragraph
    plan_comparison TEXT,            -- how actual compares to planned
    suggested_adjustment TEXT,       -- specific recommendation for today
    adjustment_type TEXT,            -- 'proceed', 'reduce', 'replace', 'rest'
    alert_flags     TEXT[],          -- ['high_acwr', 'low_hrv', 'poor_sleep', etc.]

    -- Plan snapshot (which week/day the plan was on)
    plan_week       INTEGER,
    plan_day        TEXT,
    planned_session TEXT,

    -- Full report markdown (written by agy to reports/YYYY-MM-DD.md)
    report_md       TEXT
);

-- ============================================================
-- TABLE: training.weekly_reviews
-- Weekly macro reviews (run Monday morning)
-- ============================================================
CREATE TABLE training.weekly_reviews (
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
    model_used          TEXT DEFAULT 'claude-sonnet-agy',
    week_summary        TEXT,
    training_effectiveness TEXT,
    plan_adjustment_recommendation TEXT,
    next_week_guidance  TEXT,

    -- Plan state
    phase               TEXT,        -- 'base', 'build', 'peak', 'taper', 'recovery'
    plan_week           INTEGER,

    -- Full review markdown
    review_md           TEXT
);

-- ============================================================
-- TABLE: training.workouts
-- Workout library for Garmin calendar push (Phase 5)
-- ============================================================
CREATE TABLE training.workouts (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name                TEXT NOT NULL,
    type                TEXT,          -- 'easy_run', 'tempo', 'long_run', 'intervals'
    description         TEXT,
    duration_min        INTEGER,
    hr_cap_bpm          INTEGER,       -- for zone-capped sessions
    target_pace_sec_km  INTEGER,       -- for structured runs
    structure_json      JSONB,         -- Garmin step-by-step workout format
    garmin_workout_id   BIGINT,        -- filled after first push to Garmin
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_daily_wellness_date ON training.daily_wellness(date DESC);
CREATE INDEX idx_activities_date ON training.activities(date DESC);
CREATE INDEX idx_activities_type ON training.activities(activity_type);
CREATE INDEX idx_daily_reports_date ON training.daily_reports(date DESC);
CREATE INDEX idx_weekly_reviews_week ON training.weekly_reviews(week_start DESC);

-- ============================================================
-- VIEW: training.v_acwr
-- 28-day rolling Acute:Chronic Workload Ratio
-- NOTE: Requires minimum 28 days of data to be meaningful.
--       Gate: skip ACWR calculation if chronic_28d < 10 TSS/day.
-- ============================================================
CREATE VIEW training.v_acwr AS
SELECT
    date,
    AVG(training_stress_score)
        OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
        AS acute_7d,
    AVG(training_stress_score)
        OVER (ORDER BY date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW)
        AS chronic_28d,
    CASE
        WHEN AVG(training_stress_score)
            OVER (ORDER BY date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) >= 10
        THEN ROUND(
            AVG(training_stress_score)
                OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) /
            AVG(training_stress_score)
                OVER (ORDER BY date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW),
            2)
        ELSE NULL  -- insufficient data gate: < 28 days or chronic TSS too low
    END AS acwr
FROM training.activities
ORDER BY date;

-- ============================================================
-- NOTES
-- ============================================================
-- After running this schema:
-- 1. Go to Supabase → Project Settings → Data API → Extra schemas → add 'training'
-- 2. Test with: SELECT * FROM training.daily_wellness LIMIT 1;
-- 3. The v_acwr view becomes reliable after ~28 days of activity data.
--    Use the acwr IS NOT NULL gate in n8n to skip flagging during warmup period.
