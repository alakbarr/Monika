"""
Decision Quality Evaluation & Shadow Replay Harness.
Evaluates LLM trading decisions, WAIT-regret dynamics, and Brier calibration against clean canonical price series.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class EvaluationOutcome:
    symbol: str
    decision: str  # 'buy' | 'sell' | 'wait' | 'avoid'
    decision_time: datetime
    confidence: float
    actual_outcome: float  # 1.0 for success / preservation, 0.0 for loss / missed move
    brier_score: float  # (confidence - actual_outcome) ** 2
    is_actionable: bool
    is_wait: bool
    win: bool = False
    loss: bool = False
    timeout: bool = False
    capital_preserved: bool = False
    missed_opportunity: bool = False
    r_multiple: float = 0.0
    rationale: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityMetrics:
    total_decisions: int = 0
    actionable_count: int = 0
    wait_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    timeout_count: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    mean_brier_score: float = 0.0
    capital_preserved_count: int = 0
    missed_opportunity_count: int = 0
    wait_preservation_rate: float = 0.0
    wait_regret_rate: float = 0.0
    mean_r_multiple: float = 0.0


class DecisionQualityEvaluator:
    """Evaluates individual decisions and batch histories against forward canonical bars."""

    def __init__(self, horizon_bars: int = 24, atr_regret_multiple: float = 1.5):
        self.horizon_bars = horizon_bars
        self.atr_regret_multiple = atr_regret_multiple

    def evaluate_decision(
        self,
        symbol: str,
        decision: str,
        decision_time: datetime,
        confidence: float,
        forward_bars: pd.DataFrame,
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        atr: Optional[float] = None,
    ) -> EvaluationOutcome:
        """Evaluate a single decision against subsequent forward bars."""
        norm_decision = decision.lower()
        is_actionable = norm_decision in ("buy", "sell")
        is_wait = norm_decision in ("wait", "avoid", "neutral")

        if forward_bars.empty:
            return EvaluationOutcome(
                symbol=symbol,
                decision=norm_decision,
                decision_time=decision_time,
                confidence=confidence,
                actual_outcome=0.5,
                brier_score=round((confidence - 0.5) ** 2, 4),
                is_actionable=is_actionable,
                is_wait=is_wait,
                rationale="Empty forward bars",
            )

        # Slice forward bars up to horizon
        horizon_df = forward_bars.iloc[: self.horizon_bars]

        # Calculate local ATR if not provided
        if atr is None or atr <= 0:
            if len(horizon_df) >= 2:
                tr = horizon_df["high"].combine(horizon_df["close"].shift(1), max).combine(horizon_df["low"], min)
                atr = float((horizon_df["high"] - horizon_df["low"]).mean())
            else:
                atr = float(horizon_df["close"].iloc[0] * 0.005)

        if is_actionable:
            return self._evaluate_actionable(
                symbol=symbol,
                decision=norm_decision,
                decision_time=decision_time,
                confidence=confidence,
                horizon_df=horizon_df,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                atr=atr,
            )
        else:
            return self._evaluate_wait_regret(
                symbol=symbol,
                decision=norm_decision,
                decision_time=decision_time,
                confidence=confidence,
                horizon_df=horizon_df,
                entry_price=entry_price,
                atr=atr,
            )

    def _evaluate_actionable(
        self,
        symbol: str,
        decision: str,
        decision_time: datetime,
        confidence: float,
        horizon_df: pd.DataFrame,
        entry_price: Optional[float],
        stop_loss: Optional[float],
        take_profit: Optional[float],
        atr: float,
    ) -> EvaluationOutcome:
        base_entry = entry_price or float(str(horizon_df["open"].iloc[0]))
        # Default brackets if unspecified
        if stop_loss is None or take_profit is None:
            if decision == "buy":
                sl = base_entry - (1.5 * atr)
                tp = base_entry + (2.0 * atr)
            else:
                sl = base_entry + (1.5 * atr)
                tp = base_entry - (2.0 * atr)
        else:
            sl = stop_loss
            tp = take_profit

        risk_dist = abs(base_entry - sl) or (atr * 1.5)

        for _, row in horizon_df.iterrows():
            h = float(str(row["high"]))
            l = float(str(row["low"]))

            if decision == "buy":
                # Check SL hit first (conservative intra-bar execution)
                if l <= sl:
                    return EvaluationOutcome(
                        symbol=symbol,
                        decision=decision,
                        decision_time=decision_time,
                        confidence=confidence,
                        actual_outcome=0.0,
                        brier_score=round((confidence - 0.0) ** 2, 4),
                        is_actionable=True,
                        is_wait=False,
                        win=False,
                        loss=True,
                        r_multiple=-1.0,
                        rationale=f"Stop loss hit at {sl:.5f}",
                    )
                if h >= tp:
                    reward_dist = abs(tp - base_entry)
                    r_mult = round(reward_dist / risk_dist, 2) if risk_dist > 0 else 1.5
                    return EvaluationOutcome(
                        symbol=symbol,
                        decision=decision,
                        decision_time=decision_time,
                        confidence=confidence,
                        actual_outcome=1.0,
                        brier_score=round((confidence - 1.0) ** 2, 4),
                        is_actionable=True,
                        is_wait=False,
                        win=True,
                        loss=False,
                        r_multiple=r_mult,
                        rationale=f"Take profit hit at {tp:.5f}",
                    )
            else:  # sell
                if h >= sl:
                    return EvaluationOutcome(
                        symbol=symbol,
                        decision=decision,
                        decision_time=decision_time,
                        confidence=confidence,
                        actual_outcome=0.0,
                        brier_score=round((confidence - 0.0) ** 2, 4),
                        is_actionable=True,
                        is_wait=False,
                        win=False,
                        loss=True,
                        r_multiple=-1.0,
                        rationale=f"Stop loss hit at {sl:.5f}",
                    )
                if l <= tp:
                    reward_dist = abs(base_entry - tp)
                    r_mult = round(reward_dist / risk_dist, 2) if risk_dist > 0 else 1.5
                    return EvaluationOutcome(
                        symbol=symbol,
                        decision=decision,
                        decision_time=decision_time,
                        confidence=confidence,
                        actual_outcome=1.0,
                        brier_score=round((confidence - 1.0) ** 2, 4),
                        is_actionable=True,
                        is_wait=False,
                        win=True,
                        loss=False,
                        r_multiple=r_mult,
                        rationale=f"Take profit hit at {tp:.5f}",
                    )

        # Timeout exit at close of horizon
        final_close = float(str(horizon_df["close"].iloc[-1]))
        if decision == "buy":
            pnl = final_close - base_entry
        else:
            pnl = base_entry - final_close

        r_mult = round(pnl / risk_dist, 2) if risk_dist > 0 else 0.0
        actual = 1.0 if r_mult > 0 else 0.0
        return EvaluationOutcome(
            symbol=symbol,
            decision=decision,
            decision_time=decision_time,
            confidence=confidence,
            actual_outcome=actual,
            brier_score=round((confidence - actual) ** 2, 4),
            is_actionable=True,
            is_wait=False,
            win=(r_mult > 0),
            loss=(r_mult < 0),
            timeout=True,
            r_multiple=r_mult,
            rationale=f"Horizon timeout exit at {final_close:.5f} (R={r_mult:+.2f})",
        )

    def _evaluate_wait_regret(
        self,
        symbol: str,
        decision: str,
        decision_time: datetime,
        confidence: float,
        horizon_df: pd.DataFrame,
        entry_price: Optional[float],
        atr: float,
    ) -> EvaluationOutcome:
        """Evaluate WAIT decision: did the market chop/reverse (good wait) or trend cleanly (missed opportunity)?"""
        start_px = entry_price or float(str(horizon_df["open"].iloc[0]))
        max_high = float(str(horizon_df["high"].max()))
        min_low = float(str(horizon_df["low"].min()))

        up_move = max_high - start_px
        down_move = start_px - min_low
        regret_threshold = atr * self.atr_regret_multiple

        # Did price make a decisive, un-retraced breakout in either direction?
        clean_bull_trend = (up_move >= regret_threshold) and (down_move < (atr * 0.75))
        clean_bear_trend = (down_move >= regret_threshold) and (up_move < (atr * 0.75))

        if clean_bull_trend or clean_bear_trend:
            # Missed opportunity: disciplined WAIT cost a clean trend move
            move_dist = up_move if clean_bull_trend else down_move
            return EvaluationOutcome(
                symbol=symbol,
                decision=decision,
                decision_time=decision_time,
                confidence=confidence,
                actual_outcome=0.0,  # 0.0 because waiting incurred opportunity cost
                brier_score=round((confidence - 0.0) ** 2, 4),
                is_actionable=False,
                is_wait=True,
                missed_opportunity=True,
                capital_preserved=False,
                r_multiple=-round(move_dist / atr, 2),
                rationale=f"Clean breakout missed ({move_dist / atr:.1f}x ATR move without deep pullback)",
            )
        else:
            # Capital preserved: market chopped, whipsawed, or reversed
            return EvaluationOutcome(
                symbol=symbol,
                decision=decision,
                decision_time=decision_time,
                confidence=confidence,
                actual_outcome=1.0,  # 1.0 because waiting protected capital
                brier_score=round((confidence - 1.0) ** 2, 4),
                is_actionable=False,
                is_wait=True,
                missed_opportunity=False,
                capital_preserved=True,
                r_multiple=0.0,
                rationale="Capital preserved in choppy/non-trending market",
            )

    def calculate_aggregate_metrics(self, outcomes: List[EvaluationOutcome]) -> QualityMetrics:
        """Compute summary statistics across all evaluated outcomes."""
        if not outcomes:
            return QualityMetrics()

        total = len(outcomes)
        actionables = [o for o in outcomes if o.is_actionable]
        waits = [o for o in outcomes if o.is_wait]

        wins = [o for o in actionables if o.win]
        losses = [o for o in actionables if o.loss]
        timeouts = [o for o in actionables if o.timeout]

        gross_gain = sum(o.r_multiple for o in wins if o.r_multiple > 0)
        gross_loss = abs(sum(o.r_multiple for o in losses if o.r_multiple < 0))
        pf = (gross_gain / gross_loss) if gross_loss > 0 else (99.0 if gross_gain > 0 else 0.0)

        wr = (len(wins) / len(actionables)) if actionables else 0.0
        mean_brier = sum(o.brier_score for o in outcomes) / total
        mean_r = (sum(o.r_multiple for o in actionables) / len(actionables)) if actionables else 0.0

        preserved = [w for w in waits if w.capital_preserved]
        regrets = [w for w in waits if w.missed_opportunity]

        pres_rate = (len(preserved) / len(waits)) if waits else 0.0
        regret_rate = (len(regrets) / len(waits)) if waits else 0.0

        return QualityMetrics(
            total_decisions=total,
            actionable_count=len(actionables),
            wait_count=len(waits),
            win_count=len(wins),
            loss_count=len(losses),
            timeout_count=len(timeouts),
            win_rate=round(wr, 4),
            profit_factor=round(pf, 2),
            mean_brier_score=round(mean_brier, 4),
            capital_preserved_count=len(preserved),
            missed_opportunity_count=len(regrets),
            wait_preservation_rate=round(pres_rate, 4),
            wait_regret_rate=round(regret_rate, 4),
            mean_r_multiple=round(mean_r, 2),
        )
