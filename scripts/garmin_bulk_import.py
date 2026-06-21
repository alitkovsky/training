#!/usr/bin/env python3
"""
garmin_bulk_import.py — Historical backfill of Garmin data into Supabase.

Iterates dates and upserts training.daily_wellness and training.activities.

Usage:
    python garmin_bulk_import.py                          # 2026-01-01 → yesterday
    python garmin_bulk_import.py --from 2026-03-01        # partial range
    python garmin_bulk_import.py --from 2026-03-01 --to 2026-04-01
    python garmin_bulk_import.py --dry-run                # print rows, no DB writes
"""

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta

import garminconnect
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

RATE_LIMIT_SEC = 2.0   # seconds between Garmin API calls per date
DEFAULT_START = date(2026, 1, 1)


# ── helpers ──────────────────────────────────────────────────────────────────

def safe_get(fn, *args, label=""):
    try:
        return fn(*args)
    except Exception as e:
        print(f"  [WARN] {label or fn.__name__}: {e}", file=sys.stderr)
        return None


def login(email, password, retries=3):
    for attempt in range(1, retries + 1):
        try:
            client = garminconnect.Garmin(email, password)
            client.login()
            return client
        except Exception as e:
            print(f"[WARN] Login attempt {attempt}/{retries}: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(30)
    raise RuntimeError("Garmin login failed after retries")


def normalize_wellness(d: str, garmin: dict) -> dict:
    """Map raw Garmin fetch payload to training.daily_wellness schema."""
    hrv = (garmin.get("hrv") or {}).get("hrvSummary") or {}
    sleep = (garmin.get("sleep") or {}).get("dailySleepDTO") or {}
    stress = garmin.get("stress") or {}
    bb = ((garmin.get("body_battery") or [{}])[0]) or {}
    spo2 = garmin.get("spo2") or {}
    resp = garmin.get("respiration") or {}

    total_sec = sleep.get("sleepTimeSeconds") or 0
    deep_sec = sleep.get("deepSleepSeconds") or 0
    rem_sec = sleep.get("remSleepSeconds") or 0
    light_sec = sleep.get("lightSleepSeconds") or 0
    awake_sec = sleep.get("awakeSleepSeconds") or 0

    bb_values = bb.get("bodyBatteryValuesArray") or []
    bb_wake = max((v for _, v in bb_values if v is not None), default=None) if bb_values else None

    sleep_scores = sleep.get("sleepScores") or {}
    sleep_score = (sleep_scores.get("overall") or {}).get("value")

    def pct(part, total):
        return round(part / total * 100, 1) if total else None

    return {
        "date": d,
        "hrv_weekly_avg": hrv.get("weeklyAvg"),
        "hrv_last_night": hrv.get("lastNightAvg"),
        "hrv_status": hrv.get("status"),
        "hrv_feedback": hrv.get("feedbackPhrase"),
        "sleep_duration_h": round(total_sec / 3600, 2) if total_sec else None,
        "sleep_score": sleep_score,
        "sleep_deep_pct": pct(deep_sec, total_sec),
        "sleep_rem_pct": pct(rem_sec, total_sec),
        "sleep_light_pct": pct(light_sec, total_sec),
        "sleep_awake_pct": pct(awake_sec, total_sec),
        "body_battery_wake": bb_wake,
        "body_battery_sleep_gain": bb.get("charged"),
        "resting_hr": (garmin.get("sleep") or {}).get("restingHeartRate"),
        "stress_avg": stress.get("avgStressLevel"),
        "stress_max": stress.get("maxStressLevel"),
        "spo2_avg": spo2.get("averageSpO2") or spo2.get("avgSleepSpO2"),
        "spo2_min": spo2.get("lowestSpO2"),
        "respiration_avg": resp.get("avgSleepRespirationValue"),
        "raw_json": garmin,
    }


def normalize_activity(a: dict, fallback_date: str) -> dict:
    """Map a Garmin activity dict to training.activities schema."""
    hr_zones = [a.get(f"hrTimeInZone_{z}", 0) or 0 for z in range(1, 6)]
    total_zone_sec = sum(hr_zones)

    def zone_pct(i):
        return round(hr_zones[i] / total_zone_sec * 100, 1) if total_zone_sec else None

    speed = a.get("averageSpeed") or 0
    duration = a.get("duration")

    start_date = (a.get("startTimeLocal") or fallback_date)[:10]

    return {
        "garmin_id": a.get("activityId"),
        "date": start_date,
        "activity_name": a.get("activityName"),
        "activity_type": (a.get("activityType") or {}).get("typeKey"),
        "sport_type": str((a.get("activityType") or {}).get("parentTypeId", "")),
        "duration_sec": round(duration) if duration else None,
        "distance_m": a.get("distance"),
        "elevation_gain_m": a.get("elevationGain"),
        "avg_speed_kmh": round(speed * 3.6, 2) if speed else None,
        "avg_pace_sec_per_km": round(1000 / speed) if speed > 0 else None,
        "avg_hr": round(a["averageHR"]) if a.get("averageHR") is not None else None,
        "max_hr": round(a["maxHR"]) if a.get("maxHR") is not None else None,
        "hr_zone_1_pct": zone_pct(0),
        "hr_zone_2_pct": zone_pct(1),
        "hr_zone_3_pct": zone_pct(2),
        "hr_zone_4_pct": zone_pct(3),
        "hr_zone_5_pct": zone_pct(4),
        "training_stress_score": a.get("trainingStressScore"),
        "aerobic_training_effect": a.get("aerobicTrainingEffect"),
        "anaerobic_training_effect": a.get("anaerobicTrainingEffect"),
        "training_load_abs": a.get("activityTrainingLoad"),
        "avg_power_w": round(a["avgPower"]) if a.get("avgPower") else None,
        "avg_cadence": round(
            a.get("averageRunningCadenceInStepsPerMinute")
            or a.get("avgBikingCadenceInRevPerMinute")
        ) if (a.get("averageRunningCadenceInStepsPerMinute") or a.get("avgBikingCadenceInRevPerMinute")) else None,
        "calories": round(a["calories"]) if a.get("calories") is not None else None,
        "raw_json": a,
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Garmin historical backfill")
    parser.add_argument("--from", dest="start", default=str(DEFAULT_START),
                        help="Start date YYYY-MM-DD (default: 2026-01-01)")
    parser.add_argument("--to", dest="end", default=str(date.today() - timedelta(days=1)),
                        help="End date YYYY-MM-DD inclusive (default: yesterday)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print rows without writing to DB")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start > end:
        print("[ERROR] --from must be before --to", file=sys.stderr)
        return 1

    if not EMAIL or not PASSWORD:
        print("[ERROR] GARMIN_EMAIL and GARMIN_PASSWORD required in .env", file=sys.stderr)
        return 1

    if not args.dry_run and (not SUPABASE_URL or not SUPABASE_SERVICE_KEY):
        print("[ERROR] SUPABASE_URL and SUPABASE_SERVICE_KEY required in .env", file=sys.stderr)
        return 1

    sb = None
    if not args.dry_run:
        sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    print(f"Logging in to Garmin Connect...")
    try:
        client = login(EMAIL, PASSWORD)
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    # Fetch all activities for the range in one call (more efficient)
    print(f"Fetching activities for {start} → {end}...")
    raw_activities = safe_get(
        client.get_activities_by_date,
        str(start), str(end),
        label="get_activities_by_date"
    ) or []
    print(f"  Found {len(raw_activities)} activities")

    # Group activities by date
    activities_by_date: dict[str, list] = {}
    for a in raw_activities:
        d = (a.get("startTimeLocal") or "")[:10]
        activities_by_date.setdefault(d, []).append(a)

    # Iterate each day and upsert wellness + activities
    current = start
    stats = {"wellness_ok": 0, "wellness_skip": 0, "activities_ok": 0}

    while current <= end:
        d = str(current)
        print(f"\n── {d} ──")

        # Fetch wellness signals for this date
        garmin = {
            "fetch_date": d,
            "hrv":          safe_get(client.get_hrv_data, d, label="hrv"),
            "sleep":        safe_get(client.get_sleep_data, d, label="sleep"),
            "stress":       safe_get(client.get_stress_data, d, label="stress"),
            "body_battery": safe_get(client.get_body_battery, d, label="body_battery"),
            "spo2":         safe_get(client.get_spo2_data, d, label="spo2"),
            "respiration":  safe_get(client.get_respiration_data, d, label="respiration"),
            "activities":   activities_by_date.get(d, []),
        }

        wellness_row = normalize_wellness(d, garmin)

        if wellness_row.get("sleep_duration_h") is None and wellness_row.get("hrv_last_night") is None:
            print(f"  [SKIP] No meaningful data for {d}")
            stats["wellness_skip"] += 1
        else:
            if args.dry_run:
                print(f"  [DRY] wellness: sleep={wellness_row.get('sleep_duration_h')}h "
                      f"hrv={wellness_row.get('hrv_last_night')} "
                      f"bb={wellness_row.get('body_battery_wake')}")
            else:
                # Remove raw_json for the wellness upsert to keep it concise;
                # we store it but cast via json module to ensure serializability
                row_copy = {**wellness_row, "raw_json": json.loads(json.dumps(wellness_row["raw_json"], default=str))}
                sb.schema("training").table("daily_wellness").upsert(row_copy, on_conflict="date").execute()
                print(f"  [OK] wellness upserted")
            stats["wellness_ok"] += 1

        # Upsert activities for this date
        day_activities = activities_by_date.get(d, [])
        if day_activities:
            mapped = [normalize_activity(a, d) for a in day_activities]
            if args.dry_run:
                for m in mapped:
                    print(f"  [DRY] activity: {m.get('activity_type')} "
                          f"{round((m.get('distance_m') or 0)/1000,1)}km "
                          f"tss={m.get('training_stress_score')}")
            else:
                rows = [
                    {**m, "raw_json": json.loads(json.dumps(m["raw_json"], default=str))}
                    for m in mapped
                ]
                sb.schema("training").table("activities").upsert(rows, on_conflict="garmin_id").execute()
                print(f"  [OK] {len(rows)} activities upserted")
            stats["activities_ok"] += len(day_activities)

        current += timedelta(days=1)
        if current <= end:
            time.sleep(RATE_LIMIT_SEC)

    print(f"\n── Done ──")
    print(f"Wellness upserted: {stats['wellness_ok']}, skipped: {stats['wellness_skip']}")
    print(f"Activities upserted: {stats['activities_ok']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
