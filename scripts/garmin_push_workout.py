#!/usr/bin/env python3
"""
garmin_push_workout.py — Create and schedule a structured workout on Garmin Connect.

Determines today's (or tomorrow's) session from the Phase 1 plan template,
builds a Garmin-format workout JSON, uploads it, and schedules it to the
target date so it appears on the watch.

Usage:
    python garmin_push_workout.py                    # push today's workout
    python garmin_push_workout.py --tomorrow         # push tomorrow's workout
    python garmin_push_workout.py --type intervals   # override type
    python garmin_push_workout.py --dry-run          # preview JSON, no upload
    python garmin_push_workout.py --week 6           # override plan week (default: $PLAN_WEEK)

Environment:
    GARMIN_EMAIL, GARMIN_PASSWORD  — Garmin Connect credentials
    PLAN_WEEK                      — current plan week number (default: 5)
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta

import garminconnect
from dotenv import load_dotenv

load_dotenv()

EMAIL      = os.getenv("GARMIN_EMAIL")
PASSWORD   = os.getenv("GARMIN_PASSWORD")
PLAN_WEEK_DEFAULT = int(os.getenv("PLAN_WEEK", "5"))
# Token cache shared with garmin_fetch.py to avoid 429 rate limits.
# Set GARMINTOKENS in .env to an absolute path, e.g. /Users/you/.garth
TOKENSTORE = os.getenv("GARMINTOKENS", os.path.expanduser("~/.garth"))

# ── pace/HR helpers ────────────────────────────────────────────────────────────

def pace_to_ms(sec_per_km: int) -> float:
    """Convert pace (sec/km) to speed (m/s) — Garmin pace zone unit."""
    return round(1000 / sec_per_km, 4)


# ── step builders ──────────────────────────────────────────────────────────────

def step_time_hr(order, kind_id, kind_key, duration_sec, hr_low, hr_high):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": kind_id, "stepTypeKey": kind_key},
        "endCondition": {
            "conditionTypeId": 2,
            "conditionTypeKey": "time",
            "conditionValue": str(int(duration_sec)),
        },
        "targetType": {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "heart_rate_zone"},
        "targetValueOne": hr_low,
        "targetValueTwo": hr_high,
    }


def step_dist_hr(order, kind_id, kind_key, distance_m, hr_low, hr_high):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": kind_id, "stepTypeKey": kind_key},
        "endCondition": {
            "conditionTypeId": 3,
            "conditionTypeKey": "distance",
            "conditionValue": str(int(distance_m)),
        },
        "targetType": {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "heart_rate_zone"},
        "targetValueOne": hr_low,
        "targetValueTwo": hr_high,
    }


def step_dist_pace(order, kind_id, kind_key, distance_m, pace_slow_sec_km, pace_fast_sec_km):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": kind_id, "stepTypeKey": kind_key},
        "endCondition": {
            "conditionTypeId": 3,
            "conditionTypeKey": "distance",
            "conditionValue": str(int(distance_m)),
        },
        "targetType": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "pace.zone"},
        "targetValueOne": pace_to_ms(pace_slow_sec_km),  # slower = lower m/s
        "targetValueTwo": pace_to_ms(pace_fast_sec_km),  # faster = higher m/s
    }


def step_time_pace(order, kind_id, kind_key, duration_sec, pace_slow_sec_km, pace_fast_sec_km):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": kind_id, "stepTypeKey": kind_key},
        "endCondition": {
            "conditionTypeId": 2,
            "conditionTypeKey": "time",
            "conditionValue": str(int(duration_sec)),
        },
        "targetType": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "pace.zone"},
        "targetValueOne": pace_to_ms(pace_slow_sec_km),
        "targetValueTwo": pace_to_ms(pace_fast_sec_km),
    }


def step_recovery(order, duration_sec):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": 4, "stepTypeKey": "recovery"},
        "endCondition": {
            "conditionTypeId": 2,
            "conditionTypeKey": "time",
            "conditionValue": str(int(duration_sec)),
        },
        "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
        "targetValueOne": None,
        "targetValueTwo": None,
    }


def repeat_group(order, reps, steps):
    return {
        "type": "RepeatGroupDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"},
        "endCondition": {
            "conditionTypeId": 7,
            "conditionTypeKey": "iterations",
            "conditionValue": str(reps),
        },
        "smartRepeat": False,
        "workoutSteps": steps,
    }


def build_workout(name, sport_key, steps, est_sec):
    sport_id = {"running": 1, "cycling": 2}.get(sport_key, 1)
    return {
        "workoutName": name,
        "sportType": {"sportTypeId": sport_id, "sportTypeKey": sport_key},
        "estimatedDurationInSecs": est_sec,
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": {"sportTypeId": sport_id, "sportTypeKey": sport_key},
            "workoutSteps": steps,
        }],
    }


# ── workout templates ──────────────────────────────────────────────────────────

def brick_run_z1(duration_min=25):
    """Brick run: 5min warmup → main Z1 block → 2min cooldown."""
    main_sec = max((duration_min - 7) * 60, 60)
    return build_workout(
        f"Brick Run {duration_min}min Z1",
        "running",
        steps=[
            step_time_hr(1, 1, "warmup",   300,      115, 130),
            step_time_hr(2, 3, "interval", main_sec, 128, 138),
            step_time_hr(3, 2, "cooldown", 120,      115, 128),
        ],
        est_sec=duration_min * 60,
    )


def easy_run_z2(distance_m=10000, hr_cap=150):
    """Easy aerobic run with HR cap — pace secondary."""
    return build_workout(
        f"Easy Run {distance_m//1000}km Z2 HR<{hr_cap}",
        "running",
        steps=[
            step_dist_hr(1, 1, "warmup",   1000, 125, 140),
            step_dist_hr(2, 3, "interval", distance_m - 2000, 135, hr_cap),
            step_dist_hr(3, 2, "cooldown", 1000, 115, 135),
        ],
        est_sec=int((distance_m / 1000) * 340),  # ~5:40/km estimate
    )


def recovery_run(duration_min=30):
    """Recovery run: all Z1."""
    return build_workout(
        f"Recovery Run {duration_min}min Z1",
        "running",
        steps=[
            step_time_hr(1, 1, "warmup",   300,              115, 128),
            step_time_hr(2, 3, "interval", (duration_min - 7) * 60, 122, 138),
            step_time_hr(3, 2, "cooldown", 120,              115, 125),
        ],
        est_sec=duration_min * 60,
    )


def intervals_1000m(reps=6, pace_sec_km=255, rest_sec=90):
    """Classic 1000m interval session with 1km warmup and cooldown."""
    band = 10
    interval = step_dist_pace(1, 3, "interval", 1000, pace_sec_km + band, pace_sec_km - band)
    recovery = step_recovery(2, rest_sec)
    rep_sec = (pace_sec_km * reps) + (rest_sec * reps)
    return build_workout(
        f"Intervals {reps}x1000m @{pace_sec_km//60}:{pace_sec_km%60:02d}/km",
        "running",
        steps=[
            step_dist_hr(1, 1, "warmup", 1000, 130, 150),
            repeat_group(2, reps, [interval, recovery]),
            step_dist_hr(3, 2, "cooldown", 1000, 120, 145),
        ],
        est_sec=rep_sec + 700,
    )


def intervals_1200m(reps=5, pace_sec_km=252, rest_sec=90):
    """5×1200m interval session."""
    band = 10
    interval = step_dist_pace(1, 3, "interval", 1200, pace_sec_km + band, pace_sec_km - band)
    recovery = step_recovery(2, rest_sec)
    rep_sec = (pace_sec_km * reps * 1.2) + (rest_sec * reps)
    return build_workout(
        f"Intervals {reps}x1200m @{pace_sec_km//60}:{pace_sec_km%60:02d}/km",
        "running",
        steps=[
            step_dist_hr(1, 1, "warmup", 1000, 130, 150),
            repeat_group(2, reps, [interval, recovery]),
            step_dist_hr(3, 2, "cooldown", 1000, 120, 145),
        ],
        est_sec=int(rep_sec) + 700,
    )


def intervals_2000m(reps=4, pace_sec_km=255, rest_sec=120):
    """4×2000m interval session."""
    band = 10
    interval = step_dist_pace(1, 3, "interval", 2000, pace_sec_km + band, pace_sec_km - band)
    recovery = step_recovery(2, rest_sec)
    rep_sec = (pace_sec_km * reps * 2) + (rest_sec * reps)
    return build_workout(
        f"Intervals {reps}x2000m @{pace_sec_km//60}:{pace_sec_km%60:02d}/km",
        "running",
        steps=[
            step_dist_hr(1, 1, "warmup", 1000, 130, 150),
            repeat_group(2, reps, [interval, recovery]),
            step_dist_hr(3, 2, "cooldown", 1000, 120, 145),
        ],
        est_sec=int(rep_sec) + 700,
    )


def tempo_with_finish_mp(total_m=12000, tempo_m=0, mp_m=3000,
                          tempo_pace=275, mp_pace=300):
    """Aerobic run with marathon-pace finish section."""
    easy_m = total_m - mp_m - 1000  # 1km warmup
    return build_workout(
        f"Aerobic {total_m//1000}km + {mp_m//1000}km @MP",
        "running",
        steps=[
            step_dist_hr(1, 1, "warmup",   1000,   125, 140),
            step_dist_hr(2, 3, "interval", easy_m, 135, 152),
            step_dist_pace(3, 3, "interval", mp_m, mp_pace + 10, mp_pace - 10),
            step_dist_hr(4, 2, "cooldown", 500,   115, 135),
        ],
        est_sec=int((total_m / 1000) * 340),
    )


def progression_run(total_km=10, start_sec_km=360, finish_sec_km=320):
    """Negative split progression run — pace per segment."""
    seg_m = (total_km * 1000) // 3
    mid_sec_km = (start_sec_km + finish_sec_km) // 2
    return build_workout(
        f"Progression {total_km}km {start_sec_km//60}:{start_sec_km%60:02d}→{finish_sec_km//60}:{finish_sec_km%60:02d}/km",
        "running",
        steps=[
            step_dist_pace(1, 1, "warmup",   seg_m, start_sec_km + 10, start_sec_km - 10),
            step_dist_pace(2, 3, "interval", seg_m, mid_sec_km + 10,   mid_sec_km - 10),
            step_dist_pace(3, 3, "interval", seg_m, finish_sec_km + 10, finish_sec_km - 10),
        ],
        est_sec=int(total_km * mid_sec_km),
    )


def long_run(distance_m=16000, hr_cap=155):
    """Long run with HR cap."""
    return build_workout(
        f"Long Run {distance_m//1000}km HR<{hr_cap}",
        "running",
        steps=[
            step_dist_hr(1, 1, "warmup",   1000, 125, 140),
            step_dist_hr(2, 3, "interval", distance_m - 2000, 135, hr_cap),
            step_dist_hr(3, 2, "cooldown", 1000, 115, 135),
        ],
        est_sec=int((distance_m / 1000) * 350),
    )


def long_run_with_mp(total_m=20000, mp_m=3000, hr_cap=155, mp_pace=300):
    """Long run with marathon-pace finish."""
    easy_m = total_m - mp_m - 1000
    return build_workout(
        f"Long Run {total_m//1000}km + {mp_m//1000}km @MP",
        "running",
        steps=[
            step_dist_hr(1, 1, "warmup",   1000,   125, 140),
            step_dist_hr(2, 3, "interval", easy_m, 135, hr_cap),
            step_dist_pace(3, 3, "interval", mp_m, mp_pace + 10, mp_pace - 10),
            step_dist_hr(4, 2, "cooldown", 1000,  115, 135),
        ],
        est_sec=int((total_m / 1000) * 345),
    )


# ── plan-week → workout mapping ────────────────────────────────────────────────
# day_of_week: 0=Mon 1=Tue 2=Wed 3=Thu 4=Fri 5=Sat 6=Sun

PHASE1_PLAN = {
    # Week 5
    5: {
        1: lambda: intervals_1000m(reps=6, pace_sec_km=255, rest_sec=90),
        2: lambda: brick_run_z1(25),
        3: lambda: easy_run_z2(10000, hr_cap=150),
        6: lambda: recovery_run(30),
    },
    # Week 6
    6: {
        1: lambda: intervals_1200m(reps=5, pace_sec_km=252, rest_sec=90),
        2: lambda: brick_run_z1(25),
        3: lambda: progression_run(total_km=10, start_sec_km=360, finish_sec_km=320),
        5: lambda: long_run(16000, hr_cap=155),
        6: lambda: recovery_run(30),
    },
    # Week 7
    7: {
        1: lambda: intervals_2000m(reps=4, pace_sec_km=255, rest_sec=120),
        2: lambda: brick_run_z1(25),
        3: lambda: easy_run_z2(8000, hr_cap=152),  # 8km with 5km tempo added below
        5: lambda: long_run(18000, hr_cap=155),
        6: lambda: recovery_run(30),
    },
    # Week 8 (Phase 1 close)
    8: {
        1: lambda: intervals_1000m(reps=6, pace_sec_km=250, rest_sec=90),
        2: lambda: brick_run_z1(30),
        3: lambda: tempo_with_finish_mp(total_m=12000, mp_m=3000, mp_pace=300),
        5: lambda: long_run_with_mp(total_m=20000, mp_m=3000, hr_cap=155, mp_pace=300),
        6: lambda: recovery_run(35),
    },
}

WORKOUT_TYPE_MAP = {
    "brick":       lambda w: brick_run_z1(25),
    "easy":        lambda w: easy_run_z2(10000),
    "recovery":    lambda w: recovery_run(30),
    "intervals":   lambda w: intervals_1000m(reps=6, pace_sec_km=255),
    "tempo":       lambda w: progression_run(10),
    "long":        lambda w: long_run(18000),
}


def select_workout(plan_week: int, target_date: date, override_type: str | None):
    """Return (workout_json, description) or (None, reason) if rest day."""
    if override_type:
        fn = WORKOUT_TYPE_MAP.get(override_type)
        if not fn:
            return None, f"Unknown workout type: {override_type}"
        return fn(plan_week), f"override:{override_type}"

    dow = target_date.weekday()  # 0=Mon
    week_plan = PHASE1_PLAN.get(plan_week, PHASE1_PLAN[5])  # fallback to week 5
    fn = week_plan.get(dow)
    if not fn:
        day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][dow]
        return None, f"Rest/bike day ({day_name}) — no run workout"
    return fn(), f"week {plan_week}, {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][dow]}"


# ── Garmin API calls ───────────────────────────────────────────────────────────

def push_workout(client: garminconnect.Garmin, workout: dict, target_date: date, dry_run: bool):
    if dry_run:
        print(json.dumps(workout, indent=2))
        return True

    # Upload workout via library method
    try:
        result = client.upload_workout(workout)
        workout_id = result.get("workoutId")
        if not workout_id:
            print(f"[ERROR] No workoutId in response: {result}", file=sys.stderr)
            return False
        print(f"[OK] Created workout {workout_id}: {workout['workoutName']}")
    except Exception as e:
        print(f"[ERROR] Failed to create workout: {e}", file=sys.stderr)
        return False

    # Schedule to target date
    try:
        client.schedule_workout(workout_id, str(target_date))
        print(f"[OK] Scheduled to {target_date}")
    except Exception as e:
        print(f"[WARN] Workout created but scheduling failed: {e}", file=sys.stderr)

    return True


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Push workout to Garmin Connect calendar")
    parser.add_argument("--tomorrow",  action="store_true",  help="Push tomorrow's session (default: today)")
    parser.add_argument("--type",      choices=list(WORKOUT_TYPE_MAP), help="Override workout type")
    parser.add_argument("--dry-run",   action="store_true",  help="Print workout JSON without uploading")
    parser.add_argument("--week",      type=int,             help="Override plan week number")
    parser.add_argument("--date",                            help="Target date YYYY-MM-DD (overrides --tomorrow)")
    args = parser.parse_args()

    plan_week = args.week or PLAN_WEEK_DEFAULT

    if args.date:
        target_date = date.fromisoformat(args.date)
    elif args.tomorrow:
        target_date = date.today() + timedelta(days=1)
    else:
        target_date = date.today()

    workout, description = select_workout(plan_week, target_date, args.type)
    if workout is None:
        print(f"[SKIP] {description}")
        return 0

    print(f"[INFO] Target: {target_date}  Plan week: {plan_week}  Session: {description}")
    print(f"[INFO] Workout: {workout['workoutName']}")

    if not args.dry_run:
        if not EMAIL or not PASSWORD:
            print("[ERROR] GARMIN_EMAIL and GARMIN_PASSWORD required", file=sys.stderr)
            return 1
        print(f"[INFO] Logging in (tokenstore: {TOKENSTORE})...")
        try:
            client = garminconnect.Garmin(EMAIL, PASSWORD)
            client.login(TOKENSTORE)  # loads cached tokens if available, saves after fresh login
        except Exception as e:
            print(f"[ERROR] Login failed: {e}", file=sys.stderr)
            return 1

    success = push_workout(client if not args.dry_run else None, workout, target_date, args.dry_run)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
