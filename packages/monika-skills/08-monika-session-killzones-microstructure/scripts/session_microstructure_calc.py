#!/usr/bin/env python3
"""
Monika Session Timing & Orderbook Microstructure Calculator (session_microstructure_calc.py)

Zero-dependency Python Standard Library CLI for evaluating intraday session killzones,
Orderbook Imbalance (OBI), spread expansion ratio, and rollover blackout gates.
"""

from __future__ import annotations

import argparse
from datetime import datetime, UTC
import json
import sys
from typing import Any, Dict, List, Optional


def evaluate_microstructure(
    spread_current: float,
    spread_typical: float,
    bid_vol: float = 100.0,
    ask_vol: float = 100.0,
    now_utc_str: Optional[str] = None,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    reasons: List[str] = []
    if now_utc_str:
        try:
            now = datetime.fromisoformat(now_utc_str.replace("Z", "+00:00"))
        except Exception:
            reasons.append(f"Invalid timestamp format '{now_utc_str}', fell back to current UTC time")
            now = datetime.now(UTC)
    else:
        now = datetime.now(UTC)

    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    hour = now.hour
    minute = now.minute
    minute_of_day = hour * 60 + minute
    weekday = now.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday

    sym_upper = (symbol or "").strip().upper()
    is_crypto = any(k in sym_upper for k in ("BTC", "ETH", "SOL", "CRYPTO"))

    # Session Killzones
    active_sessions: List[str] = []
    if 0 <= hour < 6:
        active_sessions.append("TOKYO_SESSION")
    if 7 <= hour < 10:
        active_sessions.append("LONDON_OPEN")
        if hour == 7 or (hour == 8 and minute <= 30):
            active_sessions.append("JUDAS_SWING_ALERT")
    if 12 <= hour < 16:
        active_sessions.append("LONDON_NY_OVERLAP")
    if 16 <= hour < 20:
        active_sessions.append("NY_AFTERNOON")

    # Rollover Blackout: 21:55 - 22:15 UTC (1315 - 1335 minute of day)
    rollover_blackout = 1315 <= minute_of_day <= 1335

    # Weekend / Friday Cutoff: Friday after 18:00 UTC (Crypto 24/7 exempt)
    friday_cutoff = (weekday == 4 and hour >= 18) and not is_crypto
    weekend_closed = (weekday in (5, 6)) and not is_crypto

    # Orderbook Imbalance (OBI)
    b_vol = max(0.0, float(bid_vol))
    a_vol = max(0.0, float(ask_vol))
    tot_vol = b_vol + a_vol
    obi = round((b_vol - a_vol) / tot_vol, 3) if tot_vol > 0 else 0.0

    # Spread Spike Gate
    spread_ratio = round(spread_current / max(1e-7, spread_typical), 2)
    spread_breached = spread_ratio > 2.0

    if rollover_blackout:
        reasons.append(f"Rollover Blackout active ({now.strftime('%H:%M UTC')}). Spread widening danger.")
    if friday_cutoff:
        reasons.append("Friday post-18:00 UTC cutoff: New entries blocked due to weekend gap risk.")
    if weekend_closed:
        reasons.append("Market closed for weekend (Forex/Commodities).")
    if spread_breached:
        reasons.append(f"Current spread ({spread_current}) exceeds 2.0x typical ({spread_typical}).")

    permitted = not rollover_blackout and not friday_cutoff and not weekend_closed and not spread_breached

    return {
        "timestamp_utc": now.isoformat(),
        "weekday": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][weekday],
        "active_killzones": active_sessions,
        "is_judas_swing_window": "JUDAS_SWING_ALERT" in active_sessions,
        "is_overlap_session": "LONDON_NY_OVERLAP" in active_sessions,
        "is_crypto_24_7": is_crypto,
        "rollover_blackout_active": rollover_blackout,
        "friday_cutoff_active": friday_cutoff,
        "weekend_closed": weekend_closed,
        "orderbook_microstructure": {
            "bid_volume": bid_vol,
            "ask_volume": ask_vol,
            "orderbook_imbalance_obi": obi,
            "orderbook_state": "BULLISH_IMBALANCE"
            if obi >= 0.30
            else ("BEARISH_IMBALANCE" if obi <= -0.30 else "NEUTRAL_BALANCED"),
            "current_spread": spread_current,
            "typical_spread": spread_typical,
            "spread_ratio": spread_ratio,
            "spread_gate_breached": spread_breached,
        },
        "execution_permitted": permitted,
        "rejection_reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monika Session & Microstructure Calculator")
    parser.add_argument("--spread-current", type=float, required=True)
    parser.add_argument("--spread-typical", type=float, required=True)
    parser.add_argument("--bid-vol", type=float, default=100.0)
    parser.add_argument("--ask-vol", type=float, default=100.0)
    parser.add_argument("--now-utc", type=str, default=None)
    parser.add_argument("--symbol", type=str, default=None)

    args = parser.parse_args()
    out = evaluate_microstructure(
        spread_current=args.spread_current,
        spread_typical=args.spread_typical,
        bid_vol=args.bid_vol,
        ask_vol=args.ask_vol,
        now_utc_str=args.now_utc,
        symbol=args.symbol,
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
