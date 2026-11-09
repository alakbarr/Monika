#!/usr/bin/env python3
"""
Monika Telemetry & Session Validator (telemetry_validator.py)

Zero-dependency Python Standard Library CLI for validating market data freshness (TTL),
session killzones (Tokyo, London Open, Judas Swing, Overlap), Rollover Blackout (21:55-22:15 UTC),
and Tier-1 news event proximity.
"""

from __future__ import annotations

import argparse
from datetime import datetime, UTC
import json
import sys
from typing import Any, Dict, List, Optional

TTL_LIMITS: Dict[str, float] = {
    "fedwatch": 12.0,
    "treasury_yields": 24.0,
    "central_bank_rates": 72.0,
    "cftc_cot": 168.0,  # 7 days
    "vix": 4.0,
    "h4_indicators": 5.0,
    "d1_indicators": 24.0,
}

COT_CONTRACT_CODES: Dict[str, str] = {
    "EURUSD": "099741",
    "GBPUSD": "096742",
    "USDJPY": "097741",
    "AUDUSD": "232741",
    "USDCAD": "090741",
    "USDCHF": "092741",
    "XAUUSD": "088691",
    "XTIUSD": "067651",
    "XBRUSD": "06765T",
    "BTCUSD": "133741",
}


def validate_telemetry_bundle(
    timestamps_json: Optional[str] = None,
    now_utc_str: Optional[str] = None,
    event_time_utc_str: Optional[str] = None,
    event_impact: str = "HIGH",
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.fromisoformat(now_utc_str.replace("Z", "+00:00")) if now_utc_str else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    freshness_results: Dict[str, Any] = {}
    stale_found = False
    reasons: List[str] = []

    if timestamps_json:
        try:
            ts_data = json.loads(timestamps_json)
            for domain, limit_hrs in TTL_LIMITS.items():
                if domain in ts_data:
                    dt_val = datetime.fromisoformat(str(ts_data[domain]).replace("Z", "+00:00"))
                    if dt_val.tzinfo is None:
                        dt_val = dt_val.replace(tzinfo=UTC)
                    age_hrs = (now - dt_val).total_seconds() / 3600.0
                    is_fresh = age_hrs <= limit_hrs
                    if not is_fresh:
                        stale_found = True
                        reasons.append(f"{domain} is {age_hrs:.1f}h old (TTL={limit_hrs:.1f}h)")
                    freshness_results[domain] = {
                        "age_hours": round(age_hrs, 2),
                        "limit_hours": limit_hrs,
                        "status": "FRESH" if is_fresh else "STALE",
                    }
        except Exception as e:
            stale_found = True
            reasons.append(f"Invalid timestamps JSON: {e}")

    # Session Timing & Killzones
    hour = now.hour
    minute = now.minute
    minute_of_day = hour * 60 + minute

    killzones: List[str] = []
    if 0 <= hour < 6:
        killzones.append("TOKYO_SESSION")
    if 7 <= hour < 10:
        killzones.append("LONDON_OPEN")
        if hour == 7 or (hour == 8 and minute <= 30):
            killzones.append("JUDAS_SWING_ALERT")
    if 12 <= hour < 16:
        killzones.append("LONDON_NY_OVERLAP")
    if 16 <= hour < 20:
        killzones.append("NY_AFTERNOON")

    rollover_blackout = 1315 <= minute_of_day <= 1335
    if rollover_blackout:
        reasons.append(f"Daily Rollover Blackout active at {now.strftime('%H:%M UTC')} (21:55 - 22:15 UTC)")

    event_blackout = False
    event_delta_mins: Optional[float] = None
    if event_time_utc_str and event_impact.upper() in ("HIGH", "TIER1", "CRITICAL"):
        try:
            ev_dt = datetime.fromisoformat(event_time_utc_str.replace("Z", "+00:00"))
            if ev_dt.tzinfo is None:
                ev_dt = ev_dt.replace(tzinfo=UTC)
            event_delta_mins = (ev_dt - now).total_seconds() / 60.0
            if -15.0 <= event_delta_mins <= 30.0:
                event_blackout = True
                reasons.append(f"High-impact event in progress (~{event_delta_mins:.0f}m away)")
        except Exception as e:
            reasons.append(f"Failed parsing event time: {e}")

    ttl_mult = 0.50 if stale_found else 1.00
    execution_permitted = not rollover_blackout and not event_blackout

    cot_code = COT_CONTRACT_CODES.get((symbol or "").upper(), "UNKNOWN")

    return {
        "timestamp_checked": now.isoformat(),
        "symbol": symbol.upper() if symbol else None,
        "cot_contract_code": cot_code,
        "stale_data_detected": stale_found,
        "ttl_multiplier": ttl_mult,
        "active_killzones": killzones,
        "overlap_bonus_eligible": "LONDON_NY_OVERLAP" in killzones,
        "judas_swing_active": "JUDAS_SWING_ALERT" in killzones,
        "rollover_blackout": rollover_blackout,
        "event_blackout": event_blackout,
        "event_delta_minutes": round(event_delta_mins, 1) if event_delta_mins is not None else None,
        "execution_permitted": execution_permitted,
        "rejection_reasons": reasons,
        "freshness_details": freshness_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monika Telemetry & Session Validator")
    parser.add_argument("--timestamps-json", type=str, default=None)
    parser.add_argument("--now-utc", type=str, default=None)
    parser.add_argument("--event-time-utc", type=str, default=None)
    parser.add_argument("--event-impact", type=str, default="HIGH")
    parser.add_argument("--symbol", type=str, default=None)

    args = parser.parse_args()
    out = validate_telemetry_bundle(
        timestamps_json=args.timestamps_json,
        now_utc_str=args.now_utc,
        event_time_utc_str=args.event_time_utc,
        event_impact=args.event_impact,
        symbol=args.symbol,
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
