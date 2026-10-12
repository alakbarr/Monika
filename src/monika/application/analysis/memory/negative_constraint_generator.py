"""
File: analysis/memory/negative_constraint_generator.py
PR-13: Negative Constraint Generator for Monika.
Synthesizes actionable "DO NOT" rules from recent losing trades, reflections,
and active market regimes to prevent recurring decision traps in Stage 2.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.memory.failure_taxonomy import (
    FailureCategory,
    FailureClassifier,
    PREVENTATIVE_RULES,
    get_negative_constraints_for_regime,
)

logger = logging.getLogger("TradingAgent.Memory.NegativeConstraintGenerator")


class NegativeConstraintGenerator:
    """
    Auto-generates negative reasoning constraints ("do NOT" invariants)
    from empirical losses and reflections to protect LLM decision-making.
    """

    @classmethod
    async def generate_negative_constraints_from_losses(
        cls,
        session: Optional[AsyncSession],
        symbol: str,
        current_regime: Optional[str] = None,
        max_constraints: int = 3,
    ) -> List[str]:
        """
        Extracts recent losses and reflections for `symbol` (or cross-asset if symbol has no history),
        classifies their failure modes, and synthesizes negative constraints.
        Falls back to regime-specific rules if empirical loss history is scarce.
        """
        symbol_clean = (symbol or "").strip().upper()
        detected_categories: List[FailureCategory] = []

        if session is not None:
            try:
                from database.models import DecisionReflection, PaperTradeRecord

                # 1. Query recent losing reflections for symbol
                q_ref = (
                    select(DecisionReflection)
                    .where(DecisionReflection.symbol == symbol_clean)
                    .where((DecisionReflection.was_profitable == False) | (DecisionReflection.outcome_pnl_usd < 0))
                    .order_by(desc(DecisionReflection.id))
                    .limit(5)
                )
                res_ref = (await session.execute(q_ref)).scalars().all()

                for r in res_ref:
                    # Check lesson tags
                    raw_tags = getattr(r, "lesson_tags", None)
                    if raw_tags:
                        try:
                            parsed_tags = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
                            if isinstance(parsed_tags, list):
                                for t in parsed_tags:
                                    cat = FailureClassifier.classify_from_text(str(t))
                                    if cat != FailureCategory.UNKNOWN_FAILURE and cat not in detected_categories:
                                        detected_categories.append(cat)
                        except Exception:
                            cat = FailureClassifier.classify_from_text(str(raw_tags))
                            if cat != FailureCategory.UNKNOWN_FAILURE and cat not in detected_categories:
                                detected_categories.append(cat)

                    # Check text fields
                    for text_field in (r.next_trade_adjustment, r.specific_lesson, r.reflection_text, r.exit_reason):
                        if text_field:
                            cat = FailureClassifier.classify_from_text(str(text_field))
                            if cat != FailureCategory.UNKNOWN_FAILURE and cat not in detected_categories:
                                detected_categories.append(cat)

                # 2. Query recent closed paper trade losses for symbol
                q_trades = (
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.symbol == symbol_clean)
                    .where(PaperTradeRecord.status == "closed")
                    .where(PaperTradeRecord.pnl_pct < 0)
                    .order_by(desc(PaperTradeRecord.id))
                    .limit(5)
                )
                res_trades = (await session.execute(q_trades)).scalars().all()

                for t in res_trades:
                    telemetry = {
                        "pnl": t.pnl_pct or -0.01,
                        "duration_seconds": (t.holding_hours or 1.0) * 3600.0,
                        "exit_reason": t.exit_reason or "",
                    }
                    # If exit reason indicates stop loss
                    if "sl" in str(t.exit_reason or "").lower() or (t.holding_hours and t.holding_hours < 0.5):
                        cat = FailureCategory.SL_TOO_TIGHT
                    elif "timeout" in str(t.exit_reason or "").lower():
                        cat = FailureCategory.TIMING_LATE
                    else:
                        cat = FailureClassifier.classify_from_metrics(telemetry)

                    if cat != FailureCategory.UNKNOWN_FAILURE and cat not in detected_categories:
                        detected_categories.append(cat)

            except Exception as e:
                logger.debug(f"[{symbol_clean}] Error querying empirical losses: {e}")

        # 3. Format constraints from empirical failures
        constraints: List[str] = []
        for cat in detected_categories:
            rule = PREVENTATIVE_RULES.get(cat)
            if rule:
                tag = cat.value.upper()
                constraints.append(f"- [DO NOT][{tag}] For {symbol_clean}: {rule}")
            if len(constraints) >= max_constraints:
                break

        # 4. If fewer than max_constraints, supplement with regime-specific cautionary rules
        if len(constraints) < max_constraints and current_regime:
            regime_rules = get_negative_constraints_for_regime(
                symbol=symbol_clean,
                regime=current_regime,
                max_rules=max_constraints - len(constraints)
            )
            for r in regime_rules:
                if r not in constraints:
                    # Format uniformly with [DO NOT]
                    formatted = r if "[DO NOT]" in r else r.replace("- [", "- [DO NOT][")
                    constraints.append(formatted)
                if len(constraints) >= max_constraints:
                    break

        return constraints

    @classmethod
    def format_for_prompt(cls, constraints: List[str]) -> str:
        """Formats list of constraints into a structured prompt section."""
        if not constraints:
            return ""
        header = "NEGATIVE CONSTRAINTS (Learned Invariants from Past Failures):"
        return f"{header}\n" + "\n".join(constraints)
