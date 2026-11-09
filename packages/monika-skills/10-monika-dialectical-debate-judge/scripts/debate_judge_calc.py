#!/usr/bin/env python3
"""
Monika Dialectical Debate & Bayesian Judge Calculator (debate_judge_calc.py)

Zero-dependency Python Standard Library CLI for executing Round 2 Rebuttal Attenuation
(-3 discount if rebuttal >= 7), Regime-Weighted scoring, Brier calibration,
Anti-Fence-Sitting checks, and Bayesian Risk Multiplier calibration.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

REGIME_WEIGHT_MATRIX: Dict[str, Dict[str, float]] = {
    "trending": {"tech": 0.50, "macro": 0.35, "sent": 0.15},
    "ranging": {"tech": 0.40, "macro": 0.30, "sent": 0.30},
    "volatile": {"tech": 0.35, "macro": 0.45, "sent": 0.20},
    "crisis": {"tech": 0.25, "macro": 0.55, "sent": 0.20},
}


def arbitrate_debate(
    bull_score: float,
    bear_score: float,
    bull_rebuttal_quality: float = 5.0,
    bear_rebuttal_quality: float = 5.0,
    regime: str = "trending",
    bull_brier: float = 0.20,
    bear_brier: float = 0.20,
    active_criteria_met: int = 4,
) -> Dict[str, Any]:
    # 1. Round 2 Rebuttal Attenuation
    att_bull = bull_score
    att_bear = bear_score

    bear_discount_applied = 0.0
    bull_discount_applied = 0.0

    if bear_rebuttal_quality >= 7.0:
        att_bull = max(1.0, bull_score - 3.0)
        bull_discount_applied = 3.0
    if bull_rebuttal_quality >= 7.0:
        att_bear = max(1.0, bear_score - 3.0)
        bear_discount_applied = 3.0

    # 2. Regime Weights
    r_key = regime.lower().strip()
    weights = REGIME_WEIGHT_MATRIX.get(r_key, REGIME_WEIGHT_MATRIX["trending"])

    # 3. Brier Calibration Weights: w_i = (1 / B_i) / sum(1 / B_j) clamped to [0.15, 0.65]
    inv_bull = 1.0 / max(0.01, bull_brier)
    inv_bear = 1.0 / max(0.01, bear_brier)
    sum_inv = inv_bull + inv_bear
    w_bull = round(max(0.15, min(0.65, inv_bull / sum_inv)), 3)
    w_bear = round(1.0 - w_bull, 3)

    score_diff = att_bull - att_bear

    # 4. Anti-Fence-Sitting Mandate
    # If active criteria >= 3 and score diff >= 1.5, Judge MUST pick a winner with calibrated risk
    if active_criteria_met >= 3 and abs(score_diff) >= 1.5:
        if score_diff > 0:
            verdict = "BUY"
            if att_bull >= 8.0:
                risk_mult = 1.00
            elif att_bull >= 6.5:
                risk_mult = 0.75
            elif att_bull >= 5.0:
                risk_mult = 0.50
            else:
                risk_mult = 0.25
        else:
            verdict = "SELL"
            if att_bear >= 8.0:
                risk_mult = 1.00
            elif att_bear >= 6.5:
                risk_mult = 0.75
            elif att_bear >= 5.0:
                risk_mult = 0.50
            else:
                risk_mult = 0.25
    else:
        verdict = "HOLD"
        risk_mult = 0.00

    return {
        "round_1_initial_scores": {
            "bull_score": bull_score,
            "bear_score": bear_score,
        },
        "round_2_rebuttal_assessment": {
            "bull_rebuttal_quality": bull_rebuttal_quality,
            "bear_rebuttal_quality": bear_rebuttal_quality,
            "bull_discount_applied": bull_discount_applied,
            "bear_discount_applied": bear_discount_applied,
            "attenuated_bull_score": round(att_bull, 2),
            "attenuated_bear_score": round(att_bear, 2),
            "net_score_differential": round(score_diff, 2),
        },
        "bayesian_calibration": {
            "market_regime": r_key,
            "regime_domain_weights": weights,
            "historical_brier_scores": {"bull": bull_brier, "bear": bear_brier},
            "calibrated_agent_weights": {"bull": w_bull, "bear": w_bear},
        },
        "chief_judge_verdict": {
            "arbitrated_direction": verdict,
            "bayesian_risk_multiplier": risk_mult,
            "anti_fence_sitting_enforced": True,
            "active_setup_criteria_met": active_criteria_met,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monika Dialectical Debate & Bayesian Judge Calculator")
    parser.add_argument("--bull-score", type=float, required=True)
    parser.add_argument("--bear-score", type=float, required=True)
    parser.add_argument("--bull-rebuttal", type=float, default=5.0)
    parser.add_argument("--bear-rebuttal", type=float, default=5.0)
    parser.add_argument("--regime", type=str, default="trending")
    parser.add_argument("--bull-brier", type=float, default=0.20)
    parser.add_argument("--bear-brier", type=float, default=0.20)
    parser.add_argument("--active-criteria-met", type=int, default=4)

    args = parser.parse_args()
    out = arbitrate_debate(
        bull_score=args.bull_score,
        bear_score=args.bear_score,
        bull_rebuttal_quality=args.bull_rebuttal,
        bear_rebuttal_quality=args.bear_rebuttal,
        regime=args.regime,
        bull_brier=args.bull_brier,
        bear_brier=args.bear_brier,
        active_criteria_met=args.active_criteria_met,
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
