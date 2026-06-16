#!/usr/bin/env python3
"""
garmin_fetch.py — Daily Garmin health data fetcher.

Fetches the past 24 hours of Garmin health data and outputs JSON to stdout.
Called by n8n's Execute Command node every morning at 08:05.

Usage:
    python garmin_fetch.py
    python garmin_fetch.py | python -m json.tool   # pretty-print for debugging

Output JSON written to stdout. Errors written to stderr.
Exit code 0 on success, 1 on failure.
"""

import garminconnect
import json
import sys
import os
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

EMAIL    = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")


def safe_get(fn, *args, default=None):
    """
    Call fn(*args) and return its result, or default on any exception.
    Ensures a single failing API endpoint doesn't crash the whole fetch.
    """
    try:
        return fn(*args)
    except Exception as e:
        print(f"[WARN] safe_get failed for {fn.__name__}: {e}", file=sys.stderr)
        return default


def login_with_retry(email, password, retries=3, delay_sec=30):
    """Login to Garmin Connect with retry logic (token expiry mitigation)."""
    import time
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            client = garminconnect.Garmin(email, password)
            client.login()
            return client
        except Exception as e:
            last_err = e
            print(f"[WARN] Login attempt {attempt}/{retries} failed: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(delay_sec)
    raise RuntimeError(f"Garmin login failed after {retries} attempts: {last_err}")


def main():
    if not EMAIL or not PASSWORD:
        print("[ERROR] GARMIN_EMAIL and GARMIN_PASSWORD must be set in .env", file=sys.stderr)
        return 1

    today     = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))

    try:
        client = login_with_retry(EMAIL, PASSWORD)
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    result = {
        "fetch_date":       today,
        "hrv":              safe_get(client.get_hrv_data,           today),
        "sleep":            safe_get(client.get_sleep_data,         today),
        "stress":           safe_get(client.get_stress_data,        today),
        "body_battery":     safe_get(client.get_body_battery,       today),
        "resting_hr":       safe_get(client.get_rhr_day,            today),
        "spo2":             safe_get(client.get_spo2_data,          today),
        "respiration":      safe_get(client.get_respiration_data,   today),
        "activities":       safe_get(client.get_activities,         0, 5),  # last 5
        "training_status":  safe_get(client.get_training_status,   today),
        "training_load":    safe_get(client.get_training_load,     today),
    }

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
