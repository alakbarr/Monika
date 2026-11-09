#!/usr/bin/env python3
"""
Monika Economic Nowcasting & Event Absorption Calculator (event_nowcast_calc.py)

Zero-dependency Python Standard Library CLI for evaluating economic indicator surprises
with revisions, computing the Canonical 4-Method Priced-In Score, and generating Event Anchor Ranges.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional


def evaluate_event_nowcast(
    actual: Optional[float] = None,
    consensus: Optional[float] = None,
    previous: Optional[float] = None,
    prior_revision: float = 0.0,
    priced_in_fedwatch: float = 5.0,
    priced_in_cot: float = 5.0,
    priced_in_exhaustion: float = 5.0,
    priced_in_historical: float = 5.0,
    event_high: Optional[float] = None,
    event_low: Optional[float] = None,
) -> Dict[str, Any]:
    net_surprise: Optional[float] = None
    pct_surprise: Optional[float] = None

    if actual is not None and consensus is not None:
        net_surprise = round((actual - consensus) + prior_revision, 3)
        if abs(consensus) > 1e-6:
            pct_surprise = round((net_surprise / abs(consensus)) * 100, 2)

    # 4-Method Priced-In Average
    scores = [priced_in_fedwatch, priced_in_cot, priced_in_exhaustion, priced_in_historical]
    priced_in_avg = round(sum(scores) / len(scores), 2)
    exhaustion_warning = priced_in_avg >= 8.0

    # Event Anchor Range
    anchor_range: Optional[Dict[str, float]] = None
    if event_high is not None and event_low is not None:
        rng = event_high - event_low
        anchor_range = {
            "event_high": event_high,
            "event_low": event_low,
            "event_midpoint": round(event_low + (rng * 0.5), 5),
            "range_size": round(rng, 5),
        }

    return {
        "event_data": {
            "actual": actual,
            "consensus": consensus,
            "previous": previous,
            "prior_revision": prior_revision,
            "net_surprise": net_surprise,
            "net_surprise_pct": pct_surprise,
        },
        "priced_in_assessment": {
            "fedwatch_score": priced_in_fedwatch,
            "cot_score": priced_in_cot,
            "price_exhaustion_score": priced_in_exhaustion,
            "historical_reaction_score": priced_in_historical,
            "composite_priced_in_score": priced_in_avg,
            "exhaustion_reversal_warning": exhaustion_warning,
        },
        "event_anchor_range": anchor_range,
        "execution_guidance": (
            "EXHAUSTION REVERSAL: Market has pre-priced the outcome (Score >= 8.0). Favor 'Sell-the-Fact' Turtle Soup sweeps over breakout continuation."
            if exhaustion_warning
            else "NORMAL STRUCTURAL ABSORPTION: Catalyst is unpriced. Trade in direction of Net Surprise after Phase 2 (15m-60m) anchor establishment."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monika Economic Nowcasting & Event Calculator")
    parser.add_argument("--actual", type=float, default=None)
    parser.add_argument("--consensus", type=float, default=None)
    parser.add_argument("--previous", type=float, default=None)
    parser.add_argument("--prior-revision", type=float, default=0.0)
    parser.add_argument("--priced-in-fedwatch", type=float, default=5.0)
    parser.add_argument("--priced-in-cot", type=float, default=5.0)
    parser.add_argument("--priced-in-exhaustion", type=float, default=5.0)
    parser.add_argument("--priced-in-historical", type=float, default=5.0)
    parser.add_argument("--event-high", type=float, default=None)
    parser.add_argument("--event-low", type=float, default=None)

    args = parser.parse_args()
    out = evaluate_event_nowcast(
        actual=args.actual,
        consensus=args.consensus,
        previous=args.previous,
        prior_revision=args.prior_revision,
        priced_in_fedwatch=args.priced_in_fedwatch,
        priced_in_cot=args.priced_in_cot,
        priced_in_exhaustion=args.priced_in_exhaustion,
        priced_in_historical=args.priced_in_historical,
        event_high=args.event_high,
        event_low=args.event_low,
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
