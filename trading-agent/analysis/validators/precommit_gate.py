"""
Deterministic Trade Pre-Commit Gate.

Executes last-mile assertions on trade decisions before routing to Risk Gate or MT5 execution:
1. Price Staleness Assertion: Entry price vs current market price / ATR buffer.
2. Crisis Regime Coherence: Prohibits low-confluence trades during extreme market stress (VIX > 35).
3. High-Impact Event Proximity: Prohibits entering market trades within 15 minutes of Tier-1 news.
4. Structural Geometry: Verifies SL/TP placement sides, non-zero risk, and minimum R:R ratio.
"""

import json
import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PriceOHLCV, EconomicCalendar, VIXData, AssetAnalysis
import utils.clock as clock

logger = logging.getLogger("TradingAgent.TradePreCommitGate")


class TradePreCommitGate:
    """
    Deterministic last-mile pre-commit assertions for trade decisions.
    """

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    async def verify_precommit(
        self,
        session: AsyncSession,
        decision_data: Dict[str, Any],
        symbol: str
    ) -> Tuple[bool, List[str]]:
        """
        Runs all pre-commit gate assertions.
        
        Returns:
            (passed, failure_reasons)
        """
        failures: List[str] = []
        sym = (symbol or decision_data.get("symbol") or "").strip().upper().replace("/", "")
        decision = str(decision_data.get("decision", "")).lower()

        # Only evaluate actionable buy/sell setups
        if decision not in ("buy", "sell"):
            return True, []

        # Resolve entry, sl, tp with support for nested entry_condition
        entry_cond = decision_data.get("entry_condition") or {}
        entry_val = (
            decision_data.get("entry_price")
            or decision_data.get("price")
            or (entry_cond.get("price") if isinstance(entry_cond, dict) else None)
        )
        entry = float(entry_val or 0.0)
        sl = float(decision_data.get("stop_loss") or decision_data.get("sl") or 0.0)
        tp = float(decision_data.get("take_profit") or decision_data.get("tp") or 0.0)

        # Fallback to database AssetAnalysis if levels are missing in decision_data
        analysis_id = decision_data.get("analysis_id")
        if (sl <= 0.0 or tp <= 0.0 or entry <= 0.0) and analysis_id:
            try:
                ana = await session.get(AssetAnalysis, analysis_id)
                if ana:
                    if sl <= 0.0 and ana.stop_loss is not None:
                        sl = float(ana.stop_loss)
                    if tp <= 0.0 and ana.take_profit is not None:
                        tp = float(ana.take_profit)
                    if entry <= 0.0:
                        if ana.entry_zone:
                            try:
                                ez = json.loads(ana.entry_zone) if isinstance(ana.entry_zone, str) else ana.entry_zone
                                if isinstance(ez, dict) and "price" in ez:
                                    entry = float(ez["price"])
                            except Exception:
                                pass
                        if entry <= 0.0 and ana.entry_price is not None:
                            entry = float(ana.entry_price)
                        if entry <= 0.0 and ana.price_at_analysis is not None:
                            entry = float(ana.price_at_analysis)
            except Exception as e:
                logger.debug(f"PreCommitGate DB fallback lookup failed for #{analysis_id}: {e}")

        # -------------------------------------------------------------
        # 1. Structural Geometry Assertion
        # -------------------------------------------------------------
        if sl <= 0.0 or tp <= 0.0:
            failures.append("STRUCTURAL: Stop loss and take profit must be strictly positive numeric values.")
        elif sl == tp:
            failures.append("STRUCTURAL: Stop loss and take profit cannot be identical.")
        else:
            if decision == "buy":
                if entry > 0.0 and sl >= entry:
                    failures.append(f"GEOMETRY: Buy SL ({sl}) must be strictly below entry ({entry}).")
                if entry > 0.0 and tp <= entry:
                    failures.append(f"GEOMETRY: Buy TP ({tp}) must be strictly above entry ({entry}).")
            elif decision == "sell":
                if entry > 0.0 and sl <= entry:
                    failures.append(f"GEOMETRY: Sell SL ({sl}) must be strictly above entry ({entry}).")
                if entry > 0.0 and tp >= entry:
                    failures.append(f"GEOMETRY: Sell TP ({tp}) must be strictly below entry ({entry}).")

        # -------------------------------------------------------------
        # 2. Price Staleness & Slippage Assertion
        # -------------------------------------------------------------
        if entry > 0.0:
            try:
                eval_time = decision_data.get("timestamp") or decision_data.get("now")
                query = select(PriceOHLCV).where(PriceOHLCV.symbol == sym)
                if eval_time:
                    query = query.where(PriceOHLCV.timestamp <= eval_time)
                latest_bar = (await session.execute(
                    query.order_by(desc(PriceOHLCV.timestamp)).limit(1)
                )).scalar_one_or_none()

                if latest_bar and latest_bar.close:
                    current_price = float(latest_bar.close)
                    price_diff = abs(current_price - entry)

                    # Estimate 1.5 ATR buffer if available
                    atr_est = float(decision_data.get("atr_14") or (entry * 0.015))
                    max_allowed_drift = max(atr_est * 1.5, entry * 0.02)

                    if price_diff > max_allowed_drift:
                        failures.append(
                            f"STALENESS: Entry {entry} drifted {price_diff:.5f} from live price {current_price} "
                            f"(max allowed drift: {max_allowed_drift:.5f})."
                        )
            except Exception as e:
                logger.debug(f"Pre-commit price staleness check error: {e}")

        # -------------------------------------------------------------
        # 2b. Ground-Truth Market Snapshot Validation (H-1)
        # -------------------------------------------------------------
        try:
            from analysis.validators.market_snapshot import VerifiedMarketSnapshot
            snap = await VerifiedMarketSnapshot().compute(sym, session, as_of=clock.now())
            if snap and snap.get("latest_close") is not None:
                plan = {
                    "direction": decision,
                    "entry_price": entry,
                    "stop_loss": sl,
                    "take_profit": tp,
                }
                snap_valid, snap_issues = VerifiedMarketSnapshot.validate_plan_against_snapshot(plan, snap)
                if not snap_valid:
                    for issue in snap_issues:
                        failures.append(f"SNAPSHOT_VALIDATION: {issue}")
        except Exception as snap_err:
            logger.debug(f"Pre-commit snapshot validation non-fatal error: {snap_err}")

        # -------------------------------------------------------------
        # 3. Crisis Regime Coherence Assertion
        # -------------------------------------------------------------
        try:
            latest_vix = (await session.execute(
                select(VIXData).order_by(desc(VIXData.date)).limit(1)
            )).scalar_one_or_none()

            if latest_vix and latest_vix.close:
                vix_val = float(latest_vix.close)
                confluence = int(decision_data.get("confluence_score") or 0)
                if vix_val >= 35.0 and confluence < 10:
                    failures.append(
                        f"REGIME COHERENCE: VIX is in extreme crisis ({vix_val:.1f} >= 35.0). "
                        f"Trades with confluence < 10 (got {confluence}) are prohibited during market panic."
                    )
        except Exception as e:
            logger.debug(f"Pre-commit VIX regime check error: {e}")

        # -------------------------------------------------------------
        # 4. High-Impact Event Proximity Assertion
        # -------------------------------------------------------------
        try:
            now = clock.now()
            window_start = now - timedelta(minutes=15)
            window_end = now + timedelta(minutes=15)

            events = (await session.execute(
                select(EconomicCalendar)
                .where(EconomicCalendar.impact.in_(["HIGH", "high", "High"]))
                .where(EconomicCalendar.event_time >= window_start)
                .where(EconomicCalendar.event_time <= window_end)
            )).scalars().all()

            if events:
                event_names = [e.event_name for e in events[:2]]
                failures.append(
                    f"CALENDAR PROXIMITY: High-impact economic release scheduled within 15 minutes: {event_names}. "
                    "Pre-commit blocked to avoid immediate news spread widening and slippage."
                )
        except Exception as e:
            logger.debug(f"Pre-commit calendar check error: {e}")

        passed = len(failures) == 0
        if not passed:
            logger.warning(f"[{sym}] TradePreCommitGate assertions failed: {failures}")
        else:
            logger.info(f"[{sym}] TradePreCommitGate passed all deterministic assertions.")

        return passed, failures
