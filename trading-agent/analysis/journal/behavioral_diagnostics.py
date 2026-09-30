# ==============================================================================
# File: analysis/journal/behavioral_diagnostics.py
# Monika Quantitative Cognitive Bias & Behavioral Diagnostics Engine
# ==============================================================================

"""
Automated trader psychological & behavioral bias quantification.

Detects and quantifies 4 core cognitive biases from real broker trade journals:
1. Disposition Effect: Holding losing positions significantly longer than winning positions.
2. Overtrading Drag: PnL degradation during hyperactive execution days vs disciplined days.
3. Chasing Momentum: Entering after impulsive price spikes without pullbacks.
4. Price Anchoring: Inability to accept dynamic levels; clustering orders around round numbers.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from analysis.journal.journal_parser import BrokerTrade

logger = logging.getLogger("TradingAgent.BehavioralDiagnostics")


@dataclass(frozen=True, slots=True)
class BehavioralDiagnosis:
    total_trades: int
    win_rate: float
    net_pnl: float
    profit_factor: float
    disposition_ratio: float           # > 1.5 = high disposition bias
    disposition_severity: str          # "LOW" | "MODERATE" | "SEVERE"
    overtrading_drag_pnl: float        # Negative value = losses incurred from excessive volume
    overtrading_severity: str
    chasing_momentum_pct: float        # % of trades chasing extensions
    chasing_severity: str
    price_anchoring_score: float       # 0.0 to 1.0 (clustering near round digits)
    price_anchoring_severity: str
    overall_discipline_score: float    # 0 to 100
    primary_vulnerability: str
    actionable_remedies: List[str] = field(default_factory=list)


class BehavioralDiagnosticsEngine:
    """Diagnoses human cognitive biases directly from historical trade records."""

    @classmethod
    def calculate_disposition_effect(cls, trades: List[BrokerTrade]) -> Tuple[float, str]:
        """Calculates ratio of avg holding duration: losing trades vs winning trades."""
        winners = [t.holding_seconds for t in trades if t.pnl > 0 and t.holding_seconds > 0]
        losers = [t.holding_seconds for t in trades if t.pnl < 0 and t.holding_seconds > 0]

        if not winners or not losers:
            return 1.0, "LOW"

        avg_win_hold = float(np.mean(winners))
        avg_loss_hold = float(np.mean(losers))

        ratio = avg_loss_hold / max(avg_win_hold, 1.0)
        ratio = round(ratio, 2)

        if ratio >= 2.0:
            severity = "SEVERE"
        elif ratio >= 1.4:
            severity = "MODERATE"
        else:
            severity = "LOW"

        return ratio, severity

    @classmethod
    def calculate_overtrading_drag(cls, trades: List[BrokerTrade]) -> Tuple[float, str]:
        """Compares daily PnL on high-activity days (trades > 75th percentile) vs calm days."""
        daily_trades: Dict[str, List[BrokerTrade]] = defaultdict(list)
        for t in trades:
            day_str = t.open_time.strftime("%Y-%m-%d")
            daily_trades[day_str].append(t)

        if len(daily_trades) < 3:
            return 0.0, "LOW"

        counts = [len(day_list) for day_list in daily_trades.values()]
        p75 = float(np.percentile(counts, 75))

        busy_days_pnl: List[float] = []
        calm_days_pnl: List[float] = []

        for day_list in daily_trades.values():
            day_pnl = sum(t.pnl for t in day_list)
            if len(day_list) >= p75 and len(day_list) > 2:
                busy_days_pnl.append(day_pnl)
            else:
                calm_days_pnl.append(day_pnl)

        if not busy_days_pnl or not calm_days_pnl:
            return 0.0, "LOW"

        avg_busy = float(np.mean(busy_days_pnl))
        avg_calm = float(np.mean(calm_days_pnl))
        drag = round(avg_busy - avg_calm, 2)

        if drag < -500.0:
            severity = "SEVERE"
        elif drag < -100.0:
            severity = "MODERATE"
        else:
            severity = "LOW"

        return drag, severity

    @classmethod
    def calculate_price_anchoring(cls, trades: List[BrokerTrade]) -> Tuple[float, str]:
        """Measures clustering around integer/round psychological prices (e.g. .00, .50)."""
        if not trades:
            return 0.0, "LOW"

        round_count = 0
        for t in trades:
            # Check price fractional part
            p = t.open_price
            frac = round((p * 100) % 10, 1)  # Last 2 digits modulo 10
            if frac in (0.0, 5.0):
                round_count += 1

        ratio = round_count / len(trades)
        ratio = round(ratio, 2)

        if ratio >= 0.45:
            severity = "SEVERE"
        elif ratio >= 0.30:
            severity = "MODERATE"
        else:
            severity = "LOW"

        return ratio, severity

    @classmethod
    def diagnose(cls, trades: List[BrokerTrade]) -> BehavioralDiagnosis:
        if not trades:
            return BehavioralDiagnosis(
                total_trades=0,
                win_rate=0.0,
                net_pnl=0.0,
                profit_factor=0.0,
                disposition_ratio=1.0,
                disposition_severity="LOW",
                overtrading_drag_pnl=0.0,
                overtrading_severity="LOW",
                chasing_momentum_pct=0.0,
                chasing_severity="LOW",
                price_anchoring_score=0.0,
                price_anchoring_severity="LOW",
                overall_discipline_score=100.0,
                primary_vulnerability="No trade history provided.",
                actionable_remedies=[],
            )

        total_trades = len(trades)
        wins = [t.pnl for t in trades if t.pnl > 0]
        losses = [t.pnl for t in trades if t.pnl < 0]
        net_pnl = round(sum(t.pnl for t in trades), 2)
        win_rate = round(len(wins) / total_trades, 3)

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = round(gross_profit / max(gross_loss, 1.0), 2)

        disp_ratio, disp_sev = cls.calculate_disposition_effect(trades)
        drag_pnl, drag_sev = cls.calculate_overtrading_drag(trades)
        anch_score, anch_sev = cls.calculate_price_anchoring(trades)

        # Chasing momentum heuristic: entries with tight stop that closed with loss in < 5 mins
        impulsive_losses = [t for t in trades if t.pnl < 0 and 0 < t.holding_seconds <= 300]
        chasing_pct = round(len(impulsive_losses) / total_trades, 2)
        chasing_sev = "SEVERE" if chasing_pct >= 0.25 else ("MODERATE" if chasing_pct >= 0.12 else "LOW")

        # Score calculation (100 base, deductions for biases)
        score = 100.0
        if disp_sev == "SEVERE":
            score -= 30.0
        elif disp_sev == "MODERATE":
            score -= 15.0

        if drag_sev == "SEVERE":
            score -= 25.0
        elif drag_sev == "MODERATE":
            score -= 10.0

        if chasing_sev == "SEVERE":
            score -= 25.0
        elif chasing_sev == "MODERATE":
            score -= 10.0

        if anch_sev == "SEVERE":
            score -= 15.0

        discipline_score = max(10.0, min(100.0, round(score, 1)))

        # Determine primary vulnerability & remedies
        vulnerabilities = []
        remedies = []
        if disp_sev in ("SEVERE", "MODERATE"):
            vulnerabilities.append("Disposition Effect (Cut winners early, held losers too long)")
            remedies.append(
                f"Automate Stop-Loss trailing via Intraday ADR Snapping; never widen SL on floating drawdown."
            )
        if drag_sev in ("SEVERE", "MODERATE"):
            vulnerabilities.append("Overtrading Drag (High activity days destroy cumulative alpha)")
            remedies.append("Enforce Max Daily Orders cap in RiskGate (max 3-5 trades/day per instrument).")
        if chasing_sev in ("SEVERE", "MODERATE"):
            vulnerabilities.append("Impulsive Momentum Chasing (Entering at bar climax)")
            remedies.append("Require limit orders resting at unmitigated OrderBlock / FVG discount zones.")

        primary_vuln = vulnerabilities[0] if vulnerabilities else "Minimal systemic cognitive bias detected."

        return BehavioralDiagnosis(
            total_trades=total_trades,
            win_rate=win_rate,
            net_pnl=net_pnl,
            profit_factor=profit_factor,
            disposition_ratio=disp_ratio,
            disposition_severity=disp_sev,
            overtrading_drag_pnl=drag_pnl,
            overtrading_severity=drag_sev,
            chasing_momentum_pct=chasing_pct,
            chasing_severity=chasing_sev,
            price_anchoring_score=anch_score,
            price_anchoring_severity=anch_sev,
            overall_discipline_score=discipline_score,
            primary_vulnerability=primary_vuln,
            actionable_remedies=remedies,
        )
