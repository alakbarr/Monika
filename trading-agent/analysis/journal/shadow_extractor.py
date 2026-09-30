# ==============================================================================
# File: analysis/journal/shadow_extractor.py
# Monika Unsupervised Shadow Strategy Rule Extractor
# ==============================================================================

"""
Unsupervised Shadow Strategy Rule Extractor.

Mines the human operator's historical trade journal to extract the subconscious
profitable trading edge, isolating systematic winning patterns from emotional noise:
1. Filters profitable trades (PnL > 0) with statistical minimum sample size.
2. Extracts temporal and execution feature vectors (hour, weekday, holding duration).
3. Derives 10th-90th percentile bounding hypercubes for entry windows and holding times.
4. Generates formal executable ShadowRule specifications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from analysis.journal.journal_parser import BrokerTrade

logger = logging.getLogger("TradingAgent.ShadowExtractor")


@dataclass(frozen=True, slots=True)
class ShadowRule:
    rule_id: str
    symbol: str
    action: str                       # 'buy' | 'sell' | 'both'
    allowed_hours: List[int]          # UTC hours (0-23)
    allowed_weekdays: List[int]       # 0=Monday .. 4=Friday
    min_holding_mins: float
    max_holding_mins: float
    expected_win_rate: float
    expected_rr: float
    sample_trades: int
    rule_description: str
    feature_quantiles: Dict[str, Any] = field(default_factory=dict)


class ShadowRuleExtractor:
    """Extracts explicit, falsifiable trading rules from winning trades."""

    @classmethod
    def extract_rules(
        cls,
        trades: List[BrokerTrade],
        min_cluster_trades: int = 5,
    ) -> List[ShadowRule]:
        if not trades:
            return []

        # 1. Group trades by symbol and direction
        groups: Dict[Tuple[str, str], List[BrokerTrade]] = {}
        for t in trades:
            key = (t.symbol.upper(), t.action.lower())
            groups.setdefault(key, []).append(t)

        extracted_rules: List[ShadowRule] = []

        for (sym, action), trade_subset in groups.items():
            winners = [t for t in trade_subset if t.pnl > 0]
            if len(winners) < min_cluster_trades:
                continue

            # Feature extraction
            hours = [t.open_time.hour for t in winners]
            weekdays = [t.open_time.weekday() for t in winners]
            hold_mins = [max(1.0, t.holding_seconds / 60.0) for t in winners]
            profits = [t.pnl for t in winners]
            losses = [abs(t.pnl) for t in trade_subset if t.pnl < 0]

            avg_win = float(np.mean(profits)) if profits else 1.0
            avg_loss = float(np.mean(losses)) if losses else 1.0
            est_rr = round(avg_win / max(avg_loss, 0.1), 2)
            win_rate = round(len(winners) / len(trade_subset), 3)

            # Quantile boundaries (p10 - p90)
            p10_hold = float(np.percentile(hold_mins, 10))
            p90_hold = float(np.percentile(hold_mins, 90))

            # Discovered active hours (hours containing winning trades)
            active_hours = sorted(list(set(hours)))
            active_weekdays = sorted(list(set(weekdays)))

            rule_id = f"shadow_{sym.lower()}_{action}_{len(extracted_rules) + 1}"
            desc = (
                f"Operator Edge for {sym} {action.upper()}: Optimal session hours {active_hours} UTC, "
                f"holding {p10_hold:.0f}-{p90_hold:.0f} mins. Historical WR: {win_rate*100:.1f}%, R:R: {est_rr:.2f}."
            )

            rule = ShadowRule(
                rule_id=rule_id,
                symbol=sym,
                action=action,
                allowed_hours=active_hours,
                allowed_weekdays=active_weekdays,
                min_holding_mins=round(p10_hold, 1),
                max_holding_mins=round(p90_hold, 1),
                expected_win_rate=win_rate,
                expected_rr=est_rr,
                sample_trades=len(winners),
                rule_description=desc,
                feature_quantiles={
                    "p10_holding_mins": p10_hold,
                    "p50_holding_mins": float(np.median(hold_mins)),
                    "p90_holding_mins": p90_hold,
                    "hour_distribution": {h: hours.count(h) for h in active_hours},
                },
            )
            extracted_rules.append(rule)

        return extracted_rules
