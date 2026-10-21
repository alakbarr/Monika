# ==============================================================================
# File: application/execution/service/executors/analysis_preflight.py
# ==============================================================================

"""
Preflight validation pass for AssetAnalysis before entering execution mutex.
Evaluates ESTOP, data staleness, cache duplicates, risk limits, confluence, and adversarial checks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.execution.service.base import _ExecutionServiceMixinBase
from monika.core.config.risk_defaults import (
    DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE,
    DEFAULT_MIN_RR_RATIO,
    DEFAULT_MIN_VERIFIABLE_CONFLUENCE,
)
from monika.core.risk.quant_scorecard import (
    extract_quant_scorecard,
    is_quantitative_source,
    validate_quant_scorecard,
)
from monika.domain.execution.sizing_calculator import SizingCalculator
from monika.domain.risk.position_sizing import PositionSizer, SizingResult
from monika.infrastructure.brokers.broker_adapter import MT5LiveAdapter
from monika.infrastructure.database.models import (
    AssetAnalysis,
    Position,
    SystemConfig,
)

if TYPE_CHECKING:
    from monika.application.execution.service.order_executor import ExecutionResult

logger = logging.getLogger("TradingAgent.ExecutionService.OrderExecutor")


@dataclass
class PreflightContext:
    """Validated trade parameters ready for execution lock entry."""

    start: datetime
    symbol: str
    decision: str
    sizing: SizingResult
    verdict: Any
    is_edge_signal: bool
    current_price: float
    order_type: str
    entry_price: float
    sl_price: float
    tp_price: Optional[float]
    account_equity: Optional[float]
    is_post_release: bool


class AnalysisPreflightMixin(_ExecutionServiceMixinBase):
    """Mixin providing preflight validation checks prior to broker submission."""

    async def _validate_analysis_preflight(
        self,
        session: AsyncSession,
        analysis: AssetAnalysis,
        account_equity: Optional[float] = None,
        is_post_release: bool = False,
        **kwargs,
    ) -> Tuple[Optional[ExecutionResult], Optional[PreflightContext]]:
        """
        Runs Fase 1 validation pass.
        Returns (failure_result, None) if validation fails.
        Returns (None, PreflightContext) if valid and ready for execution.
        """
        from monika.application.execution.service.order_executor import (
            _EXECUTED_ANALYSIS_IDS,
            AgentNotifier,
            ExecutionResult,
            _prune_executed_analysis_ids,
            get_session,
            transactional_advisory_lock,
        )

        start = clock.now()
        symbol = analysis.symbol
        decision = analysis.decision

        logger.info(f"ExecutionService: processing {symbol} → {decision.upper()}")

        # Abaikan keputusan non-tradeable (avoid/wait)
        if decision not in ("buy", "sell"):
            logger.info(f"Decision '{decision}' for {symbol} — no execution needed")
            return ExecutionResult(
                symbol=symbol,
                analysis_id=analysis.id,
                decision=decision,
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["not_tradeable"],
                risk_rejection_reasons=[f"Decision is '{decision}' — no order placed"],
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error=None,
                position_id=None,
                timestamp=start,
                elapsed_ms=0,
            ), None

        # Check ESTOP (Emergency Stop Sentinel)
        from monika.application.agent.estop import get_estop_details, is_estop_active

        if is_estop_active():
            estop_info = get_estop_details() or {}
            reason = estop_info.get("reason", "ESTOP sentinel active")
            logger.critical(f"[ESTOP] Order execution blocked for {symbol}: {reason}")
            return ExecutionResult(
                symbol=symbol,
                analysis_id=analysis.id,
                decision=decision,
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["estop_active"],
                risk_rejection_reasons=[f"ESTOP is active: {reason}"],
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error="ESTOP_ACTIVE",
                position_id=None,
                timestamp=start,
                elapsed_ms=0,
            ), None

        # Check live execution requirements (Phase 0)
        if not self.dry_run:
            min_paper_trades = self.settings.get("trading", {}).get(
                "min_paper_trades_before_live",
                self.settings.get("execution", {}).get("min_paper_trades_before_live", 50),
            )
            # FIX 4.10: allow explicit force_live_override
            if self.settings.get("trading", {}).get("force_live_override", False) or self.settings.get(
                "execution", {}
            ).get("force_live_override", False):
                min_paper_trades = 0
            from monika.infrastructure.database.models import PaperTradeRecord

            try:
                # Use the existing session passed to the function
                raw_count = (await session.execute(select(func.count(PaperTradeRecord.id)))).scalar()
                try:
                    paper_trades_count = int(raw_count) if raw_count is not None else 0
                except TypeError, ValueError:
                    paper_trades_count = 0

                min_win_rate = float(
                    self.settings.get("trading", {}).get(
                        "graduation_min_win_rate",
                        self.settings.get("execution", {}).get("graduation_min_win_rate", 0.55),
                    )
                )
                raw_closed = (
                    await session.execute(
                        select(func.count(PaperTradeRecord.id)).where(PaperTradeRecord.status == "closed")
                    )
                ).scalar()
                try:
                    closed_count = int(raw_closed) if raw_closed is not None else 0
                except TypeError, ValueError:
                    closed_count = 0

                raw_win = (
                    await session.execute(
                        select(func.count(PaperTradeRecord.id)).where(
                            PaperTradeRecord.status == "closed", PaperTradeRecord.pnl_pct > 0
                        )
                    )
                ).scalar()
                try:
                    win_count = int(raw_win) if raw_win is not None else 0
                except TypeError, ValueError:
                    win_count = 0

                win_rate = (float(win_count) / float(closed_count)) if closed_count > 0 else 0.0

                if paper_trades_count < min_paper_trades:
                    logger.warning(
                        f"Execution REJECTED for {symbol}: Cannot execute live. "
                        f"Paper trades count ({paper_trades_count}) < min_paper_trades_before_live ({min_paper_trades})."
                    )
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=analysis.id,
                        decision=decision,
                        sizing=None,
                        risk_approved=False,
                        risk_checks_passed=[],
                        risk_checks_failed=["insufficient_paper_trades"],
                        risk_rejection_reasons=[
                            f"Cannot execute live: Need {min_paper_trades} paper trades, currently have {paper_trades_count}."
                        ],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=None,
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=0,
                    ), None
                elif min_paper_trades > 0 and (closed_count < min_paper_trades or win_rate < min_win_rate):
                    logger.warning(
                        f"Execution REJECTED for {symbol}: Cannot execute live. "
                        f"Paper closed trades ({closed_count}) or win rate ({win_rate:.1%}) below graduation threshold (min {min_win_rate:.1%})."
                    )
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=analysis.id,
                        decision=decision,
                        sizing=None,
                        risk_approved=False,
                        risk_checks_passed=[],
                        risk_checks_failed=["insufficient_paper_win_rate"],
                        risk_rejection_reasons=[
                            f"Cannot execute live: Paper win rate {win_rate:.1%} < {min_win_rate:.1%} required across at least {min_paper_trades} closed trades (currently {closed_count})."
                        ],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=None,
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=0,
                    ), None
            except Exception as pt_err:
                logger.error(f"Failed to check paper trades count: {pt_err}")
        # Cek umur analisis — tolak jika sudah terlalu lama (basi)
        max_execute_age_minutes = self.settings.get("execution", {}).get(
            "max_analysis_age_for_execute_minutes",
            20,  # 20 menit default — conservative
        )
        if analysis.generated_at:
            gen_at = analysis.generated_at
            if gen_at.tzinfo is None:
                gen_at = gen_at.replace(tzinfo=timezone.utc)
            # Re-check dengan waktu sekarang (setelah lock diperoleh)
            current_age_minutes = (start - gen_at).total_seconds() / 60.0

            if current_age_minutes > max_execute_age_minutes:
                logger.warning(
                    f"Execution REJECTED post-lock for {symbol}: analysis is "
                    f"{current_age_minutes:.1f}m old (limit={max_execute_age_minutes}m). "
                    f"Analysis became stale while waiting for execution lock."
                )
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=None,
                    risk_approved=False,
                    risk_checks_passed=[],
                    risk_checks_failed=["analysis_stale_post_lock"],
                    risk_rejection_reasons=[
                        f"Analysis became stale ({current_age_minutes:.1f}m) while waiting "
                        f"for execution lock (limit={max_execute_age_minutes}m)."
                    ],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=0,
                ), None

        # Check fundamental brief age — don't execute on outdated macro thesis
        if analysis.brief_id:
            try:
                from sqlalchemy import select as _sel

                from monika.infrastructure.database.models import FundamentalBrief

                async with get_session() as brief_session:
                    brief = await brief_session.get(FundamentalBrief, analysis.brief_id)
                    if brief and brief.generated_at:
                        gen_at = brief.generated_at
                        if gen_at.tzinfo is None:
                            gen_at = gen_at.replace(tzinfo=timezone.utc)
                        brief_age_hours = (start - gen_at).total_seconds() / 3600
                        max_brief_age = self.settings.get("data_quality", {}).get("max_brief_age_execution_hours", 12.0)
                        if brief_age_hours > max_brief_age:
                            logger.warning(
                                f"Execution REJECTED for {symbol}: fundamental brief is "
                                f"{brief_age_hours:.1f}h old (limit={max_brief_age}h). "
                                f"Macro thesis may be outdated. Re-run analysis cycle first."
                            )
                            return ExecutionResult(
                                symbol=symbol,
                                analysis_id=analysis.id,
                                decision=decision,
                                sizing=None,
                                risk_approved=False,
                                risk_checks_passed=[],
                                risk_checks_failed=["stale_fundamental_brief"],
                                risk_rejection_reasons=[
                                    f"Fundamental brief is {brief_age_hours:.1f}h old "
                                    f"(limit={max_brief_age}h). Run /run to refresh."
                                ],
                                executed=False,
                                mt5_ticket=None,
                                executed_price=None,
                                executed_lots=None,
                                mt5_error=None,
                                position_id=None,
                                timestamp=start,
                                elapsed_ms=0,
                            ), None

                        # Check jika ada high-impact event terjadi setelah brief dibuat
                        from monika.domain.market.currency_utils import get_symbol_currencies
                        from monika.infrastructure.database.models import EconomicCalendar

                        sym_currencies = get_symbol_currencies(symbol)
                        brief_created = (
                            brief.generated_at.replace(tzinfo=timezone.utc)
                            if brief.generated_at.tzinfo is None
                            else brief.generated_at
                        )
                        # Only block if the high-impact event occurred very recently (within 30 mins) post-brief
                        recent_threshold = max(brief_created, start - timedelta(minutes=30))
                        post_brief_events = (
                            await brief_session.execute(
                                _sel(EconomicCalendar)
                                .where(EconomicCalendar.event_time > recent_threshold)
                                .where(EconomicCalendar.event_time <= start)
                                .where(EconomicCalendar.impact.in_(["high", "High", "HIGH"]))
                                .where(EconomicCalendar.currency.in_(list(sym_currencies)))
                                .limit(1)
                            )
                        ).scalar_one_or_none()

                        if post_brief_events:
                            logger.warning(
                                f'Execution BLOCKED for {symbol}: Recent high-impact event "{post_brief_events.event_name}" '
                                f"occurred at {post_brief_events.event_time} (within 30m of execution). Brief may be stale for current conditions."
                            )
                            return ExecutionResult(
                                symbol=symbol,
                                analysis_id=analysis.id,
                                decision=decision,
                                sizing=None,
                                risk_approved=False,
                                risk_checks_passed=[],
                                risk_checks_failed=["stale_fundamental_brief_post_event"],
                                risk_rejection_reasons=[
                                    f"Post-brief high-impact event detected: {post_brief_events.event_name} "
                                    f"at {post_brief_events.event_time}. Re-run analysis cycle first."
                                ],
                                executed=False,
                                mt5_ticket=None,
                                executed_price=None,
                                executed_lots=None,
                                mt5_error=None,
                                position_id=None,
                                timestamp=start,
                                elapsed_ms=0,
                            ), None

                        try:
                            from monika.application.protocol.brief_contamination_guard import BriefContaminationGuard

                            is_stale_mag, stale_reason = await BriefContaminationGuard.check_magnitude_based_staleness(
                                brief_session, symbol, gen_at, self.settings
                            )
                            if is_stale_mag:
                                logger.warning(f"Execution BLOCKED for {symbol}: {stale_reason}")
                                return ExecutionResult(
                                    symbol=symbol,
                                    analysis_id=analysis.id,
                                    decision=decision,
                                    sizing=None,
                                    risk_approved=False,
                                    risk_checks_passed=[],
                                    risk_checks_failed=["magnitude_staleness"],
                                    risk_rejection_reasons=[stale_reason],
                                    executed=False,
                                    mt5_ticket=None,
                                    executed_price=None,
                                    executed_lots=None,
                                    mt5_error=None,
                                    position_id=None,
                                    timestamp=start,
                                    elapsed_ms=0,
                                ), None
                        except Exception as e:
                            logger.debug(f"Magnitude staleness check failed: {e}")

            except Exception as brief_err:
                logger.debug(f"Brief age check failed (non-fatal): {brief_err}")

        # Cegah eksekusi order duplikat (Phase 5)
        from monika.infrastructure.database.models import Position

        # Memory cache check to prevent race conditions
        _prune_executed_analysis_ids()
        if analysis.id in _EXECUTED_ANALYSIS_IDS:
            logger.warning(
                f"Execution REJECTED for {symbol}: Position already exists in memory cache for analysis_id {analysis.id} (duplicate_analysis_execution)"
            )
            return ExecutionResult(
                symbol=symbol,
                analysis_id=analysis.id,
                decision=decision,
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["duplicate_analysis_execution"],
                risk_rejection_reasons=[f"Position already exists for this analysis (id={analysis.id})."],
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error=None,
                position_id=None,
                timestamp=start,
                elapsed_ms=0,
            ), None

        is_duplicate = (
            await session.execute(select(Position).where(Position.analysis_id == analysis.id).limit(1))
        ).scalar_one_or_none()

        # Cache-Before-Commit pattern:
        # Update _EXECUTED_ANALYSIS_IDS if position already exists in DB (duplicate).
        # For new executions, cache is updated only after MT5 order placement succeeds.
        if is_duplicate:
            _EXECUTED_ANALYSIS_IDS[analysis.id] = time.time()
            logger.warning(
                f"Execution REJECTED for {symbol}: Position already exists in DB for analysis_id {analysis.id} (duplicate_analysis_execution)"
            )
            return ExecutionResult(
                symbol=symbol,
                analysis_id=analysis.id,
                decision=decision,
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["duplicate_analysis_execution"],
                risk_rejection_reasons=[f"Position already exists for this analysis (id={analysis.id})."],
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error=None,
                position_id=None,
                timestamp=start,
                elapsed_ms=0,
            ), None

        # NOTE: _EXECUTED_ANALYSIS_IDS[analysis.id] TIDAK di-set di sini.
        # Validasi Koneksi MT5 (Task 1.4)
        if not self.dry_run and isinstance(self.broker_adapter, MT5LiveAdapter):
            is_connected = await self.mt5.ensure_connected()
            if not is_connected:
                logger.error(f"Execution ABORTED for {symbol}: MT5 is not connected.")
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=None,
                    risk_approved=False,
                    risk_checks_passed=[],
                    risk_checks_failed=["mt5_disconnected"],
                    risk_rejection_reasons=["MT5 connection is dead. Cannot place order safely."],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error="MT5 Disconnected",
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=elapsed,
                ), None

        # Check if post-release exemption applies
        if not is_post_release and analysis:
            txt = (
                str(getattr(analysis, "execution_notes", "") or "")
                + " "
                + str(getattr(analysis, "catalyst", "") or "")
                + " "
                + str(getattr(analysis, "reasoning", "") or "")
            ).lower()
            if "post-release" in txt or "post_release" in txt:
                is_post_release = True

        # News Blackout Check
        from monika.domain.market.currency_utils import get_symbol_currencies
        from monika.infrastructure.database.models import EconomicCalendar

        news_window_minutes = self.settings.get("trading", {}).get("risk", {}).get("news_window_minutes", 30)
        blackout_window = timedelta(minutes=news_window_minutes)
        sym_currencies = get_symbol_currencies(symbol)

        upcoming = (
            (
                await session.execute(
                    select(EconomicCalendar)
                    .where(EconomicCalendar.event_time >= start - blackout_window)
                    .where(EconomicCalendar.event_time <= start + blackout_window)
                    .where(EconomicCalendar.impact.in_(["high", "High", "HIGH"]))
                    .where(EconomicCalendar.currency.in_(list(sym_currencies)))
                )
            )
            .scalars()
            .all()
        )

        if upcoming and not is_post_release:
            logger.warning(
                f"Execution REJECTED for {symbol}: News blackout circuit breaker triggered by {upcoming[0].event_name}"
            )
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol,
                analysis_id=analysis.id,
                decision=decision,
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["news_blackout"],
                risk_rejection_reasons=[f"Trading blocked: Near high-impact news ({upcoming[0].event_name})"],
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error=None,
                position_id=None,
                timestamp=start,
                elapsed_ms=elapsed,
            ), None
        elif upcoming and is_post_release:
            logger.info(
                f"Execution ALLOWED for {symbol}: Post-release analysis exempt from news blackout ({upcoming[0].event_name})."
            )
        # Priced-in score gating is centralized upstream in risk_gate.py

        # Parsing kondisi entry
        entry_cond: dict[str, Any] = {}
        if analysis.entry_zone:
            if isinstance(analysis.entry_zone, dict):
                entry_cond = analysis.entry_zone
            elif isinstance(analysis.entry_zone, str):
                try:
                    parsed = json.loads(analysis.entry_zone)
                    if isinstance(parsed, dict):
                        entry_cond = parsed
                except Exception as e:
                    logger.debug(f"Failed to parse entry_zone JSON: {e}")
                    entry_cond = {}

        max_price_staleness = self.settings.get("execution", {}).get("max_price_staleness_seconds", 120)
        entry_price_raw, is_stale, age_seconds = await self._get_current_price(symbol, decision)

        if symbol == "USDJPY" and not is_stale:
            PositionSizer.update_usdjpy_cache(entry_price_raw)

        if is_stale and age_seconds > max_price_staleness:
            logger.error(
                f"Execution ABORTED for {symbol}: price data is {age_seconds:.0f}s old "
                f"(limit={max_price_staleness}s). MT5 must be connected for safe execution."
            )
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol,
                analysis_id=analysis.id,
                decision=decision,
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["stale_price_data"],
                risk_rejection_reasons=[f"Price data {age_seconds:.0f}s old — MT5 connection required for execution"],
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error=None,
                position_id=None,
                timestamp=start,
                elapsed_ms=elapsed,
            ), None

        if not self.dry_run:
            try:
                from monika.core.validation.data_validator import is_spread_acceptable

                if hasattr(self, "broker_adapter") and self.broker_adapter is not None:
                    tick = await self.broker_adapter.get_tick(symbol)
                else:
                    tick = await self.mt5.get_current_price(symbol)
                if tick is None or float(tick.get("bid", 0.0) or 0.0) <= 0 or float(tick.get("ask", 0.0) or 0.0) <= 0:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=analysis.id,
                        decision=decision,
                        sizing=None,
                        risk_approved=False,
                        risk_checks_passed=[],
                        risk_checks_failed=["spread_check_unavailable"],
                        risk_rejection_reasons=["Cannot verify spread: price data unavailable or non-positive."],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=None,
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=elapsed,
                    ), None
                if tick and not is_spread_acceptable(symbol, tick["bid"], tick["ask"]):
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=analysis.id,
                        decision=decision,
                        sizing=None,
                        risk_approved=False,
                        risk_checks_passed=[],
                        risk_checks_failed=["spread_too_high"],
                        risk_rejection_reasons=["Spread circuit breaker triggered. Spread too wide."],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=None,
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=elapsed,
                    ), None
            except Exception as e:
                logger.debug(f"Spread check failed (non-fatal): {e}")

        try:
            raw_spec = entry_cond.get("price")
            specified_price = float(raw_spec) if raw_spec is not None else None
        except ValueError, TypeError:
            specified_price = None

        entry_price = specified_price if specified_price is not None else entry_price_raw
        current_price = float(entry_price_raw) if entry_price_raw is not None else float(entry_price or 0.0)
        order_type = entry_cond.get("order_type") or entry_cond.get("type", "market")

        MAX_DEVIATION = {
            "XAUUSD": 0.5,
            "EURUSD": 0.2,
            "GBPUSD": 0.2,
            "USDJPY": 0.2,
            "AUDUSD": 0.2,
            "XTIUSD": 0.7,
            "BTCUSD": 1.0,
            "XBRUSD": 0.7,
        }

        if specified_price is not None and entry_price_raw:
            current_price = float(entry_price_raw)
            threshold = MAX_DEVIATION.get(symbol, 0.5)

            if order_type == "limit":
                # Validasi pergeseran harga pasar sejak analisis dibuat (Market Drift), BUKAN jarak limit ke harga pasar
                analyzed_market_price = float(getattr(analysis, "price_at_analysis", current_price) or current_price)
                is_drift_valid, market_drift_pct = SizingCalculator.validate_price_drift(
                    current_market_price=current_price,
                    reference_price=analyzed_market_price,
                    max_drift_pct=threshold * 2,
                )
                if not is_drift_valid:
                    logger.warning(
                        f"Skipping {symbol} execution: Market price drifted {market_drift_pct:.2f}% "
                        f"since analysis (Analyzed Market: {analyzed_market_price}, Current: {current_price})"
                    )
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=analysis.id,
                        decision=decision,
                        sizing=None,
                        risk_approved=False,
                        risk_checks_passed=[],
                        risk_checks_failed=["stale_entry_price"],
                        risk_rejection_reasons=[
                            f"Market moved {market_drift_pct:.2f}% from analysis price (threshold {threshold * 2}%)"
                        ],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=None,
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=elapsed,
                    ), None
            elif order_type == "market":
                is_drift_valid, price_diff_pct = SizingCalculator.validate_price_drift(
                    current_market_price=current_price,
                    reference_price=specified_price,
                    max_drift_pct=threshold,
                )
                if not is_drift_valid:
                    logger.warning(
                        f"Skipping {symbol} execution: Market price deviated {price_diff_pct:.2f}% "
                        f"from analysis price {specified_price} (Current: {current_price}). Too much slippage risk."
                    )
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=analysis.id,
                        decision=decision,
                        sizing=None,
                        risk_approved=False,
                        risk_checks_passed=[],
                        risk_checks_failed=["stale_entry_price"],
                        risk_rejection_reasons=[
                            f"Market price deviated {price_diff_pct:.2f}% (threshold {threshold}%)"
                        ],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=None,
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=elapsed,
                    ), None

        # Ambil live equity
        if account_equity is None:
            account_equity = await self._get_equity()
        if account_equity is None or account_equity <= 0:
            if not self.dry_run:
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                logger.error(
                    f"Live execution ABORTED for {symbol}: broker account equity unavailable ({account_equity})"
                )
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=None,
                    risk_approved=False,
                    risk_checks_passed=[],
                    risk_checks_failed=["live_equity_unavailable"],
                    risk_rejection_reasons=["Live trading requires verified broker account equity (> 0)"],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error="LIVE_EQUITY_UNAVAILABLE",
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=elapsed,
                ), None
            account_equity = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))

        # Ambil level VIX terbaru untuk risiko dinamis
        vix_level = 18.0
        try:
            from monika.infrastructure.database.models import VIXData

            vix_row = (
                await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))
            ).scalar_one_or_none()
            if vix_row:
                vix_level = vix_row.close
        except Exception as e:
            logger.debug(f"Failed to fetch VIX for sizing: {e}")

        # Ambil scaling risiko dinamis
        risk_cfg = self.settings.get("trading", {}).get("risk", {})
        base_risk_pct = risk_cfg.get("risk_percent_per_trade", 1.5)
        risk_percent_override = await self._get_dynamic_risk_percent(session, symbol, base_risk_pct)

        # NEW: fold analysis.risk_multiplier into risk_pct BEFORE sizing (defensive clamp 0.0-2.0, floor 0.30 if > 0)
        analysis_risk_multiplier = getattr(analysis, "risk_multiplier", None)
        if analysis_risk_multiplier is not None:
            try:
                clamped_mult = max(0.0, min(2.0, float(analysis_risk_multiplier)))
                if 0.0 < clamped_mult < 0.30:
                    clamped_mult = 0.30
            except TypeError, ValueError:
                clamped_mult = 1.0
            if clamped_mult != float(analysis_risk_multiplier):
                logger.warning(
                    f"[{symbol}] risk_multiplier {analysis_risk_multiplier} adjusted/clamped to {clamped_mult}"
                )
            risk_percent_override = risk_percent_override * clamped_mult

        tp_price = float(analysis.take_profit) if analysis.take_profit is not None else None
        sl_price = float(analysis.stop_loss) if analysis.stop_loss is not None else 0.0

        # (TP distance sanity checks are now centralized in tool_executor.py during generation)

        # Langkah 1: Position sizing under advisory lock
        async with transactional_advisory_lock(session, lock_key=f"sizing_{symbol}") as is_locked:
            if not is_locked:
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=None,
                    risk_approved=False,
                    risk_checks_passed=[],
                    risk_checks_failed=["advisory_lock_contention"],
                    risk_rejection_reasons=["Concurrent execution locked by another transaction/worker."],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=0,
                ), None
            sizing = await self.sizer.calculate_with_session(
                session=session,
                symbol=symbol,
                direction=decision,
                entry_price=entry_price,
                stop_loss=sl_price,
                take_profit=tp_price,
                account_equity=account_equity,
                risk_percent_override=risk_percent_override,
                vix_level=vix_level,
            )

            # 4. Validasi Risk (Risk Gate)
            # ---------------------------------------------------------
            verdict = await self.gate.check(
                session=session,
                symbol=symbol,
                direction=decision,
                sizing=sizing,
                account_equity=account_equity,
                analysis=analysis,
            )

            if not verdict.approved:
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                result = ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=sizing,
                    risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed,
                    risk_rejection_reasons=verdict.rejection_reasons,
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=elapsed,
                )
                await self._log_result(session, result, analysis.id)
                logger.warning(f"Execution blocked: {result.summary()}")
                return result, None

        decision_source = str(getattr(analysis, "decision_source", "") or "")
        is_edge_signal = is_quantitative_source(decision_source)

        if verdict.approved and analysis.decision in ("buy", "sell") and is_edge_signal:
            trading_cfg = self.settings.get("trading", {}) if isinstance(self.settings, dict) else {}
            risk_cfg = trading_cfg.get("risk", {}) if isinstance(trading_cfg, dict) else {}
            min_confidence = float(trading_cfg.get("auto_execute_min_confidence", DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE))
            min_rr_ratio = float(risk_cfg.get("min_rr_ratio", DEFAULT_MIN_RR_RATIO))
            confidence = analysis.confidence or 0.0
            if confidence < min_confidence:
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=sizing,
                    risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ["edge_signal_low_confidence"],
                    risk_rejection_reasons=[
                        f"Edge signal confidence {analysis.confidence} < {min_confidence:.2f} minimum"
                    ],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=elapsed,
                ), None

            scorecard = extract_quant_scorecard(analysis)
            scorecard_ok, scorecard_reason = validate_quant_scorecard(
                scorecard,
                min_confidence=min_confidence,
                min_rr_ratio=min_rr_ratio,
            )
            if not scorecard_ok:
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=sizing,
                    risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ["edge_signal_quant_scorecard"],
                    risk_rejection_reasons=[scorecard_reason],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=elapsed,
                ), None

        if verdict.approved and analysis.decision in ("buy", "sell") and not is_edge_signal:
            # --- MINIMUM VERIFIABLE CONFLUENCE GATE ---
            min_verifiable = (
                self.settings.get("trading", {})
                .get("risk", {})
                .get("min_verifiable_confluence", DEFAULT_MIN_VERIFIABLE_CONFLUENCE)
            )
            if (analysis.confluence_score or 0) < min_verifiable:
                logger.warning(
                    f"Execution BLOCKED for {symbol}: confluence score {analysis.confluence_score} < min_verifiable ({min_verifiable})"
                )
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=sizing,
                    risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ["insufficient_confluence"],
                    risk_rejection_reasons=[
                        f"Confluence score {analysis.confluence_score} < minimum required {min_verifiable}"
                    ],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=elapsed,
                ), None

            if self.settings.get("trading", {}).get("risk", {}).get("confluence_verifier_enabled", True):
                try:
                    from monika.application.analysis.validators.confluence_verifier import verify_confluence

                    verification = await verify_confluence(session, analysis, self.settings)
                    if not verification["verified"]:
                        logger.warning(
                            f"Confluence verification FAILED for {symbol}: {verification['blocking_issues']}"
                        )

                        # Block execution jika ada blocking issues
                        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                        return ExecutionResult(
                            symbol=symbol,
                            analysis_id=analysis.id,
                            decision=decision,
                            sizing=sizing,
                            risk_approved=False,
                            risk_checks_passed=verdict.checks_passed,
                            risk_checks_failed=verdict.checks_failed + ["confluence_verification"],
                            risk_rejection_reasons=[
                                f"Confluence verification: {issue}" for issue in verification["blocking_issues"]
                            ],
                            executed=False,
                            mt5_ticket=None,
                            executed_price=None,
                            executed_lots=None,
                            mt5_error=None,
                            position_id=None,
                            timestamp=start,
                            elapsed_ms=elapsed,
                        ), None
                    else:
                        score_val = (
                            verification.get("claude_score")
                            or verification.get("ai_score")
                            or verification.get("score")
                        )
                        logger.info(
                            f"Confluence verified for {symbol}: "
                            f"computed={verification['computed_score']}, "
                            f"ai={score_val}"
                        )
                except Exception as e:
                    logger.warning(f"Confluence verification error (non-fatal, proceeding): {e}")

        # Task 2.1: Adversarial Validation Pass (Pre-Execution) - Reuse cached check if already run
        if (
            verdict.approved
            and analysis.decision in ("buy", "sell")
            and not is_edge_signal
            and self.settings.get("adversarial_check", {}).get("enabled", True)
        ):
            cached_adv = (
                await session.execute(
                    select(SystemConfig).where(SystemConfig.key == f"adversarial_outcome_{analysis.id}")
                )
            ).scalar_one_or_none()
            adv = None
            if cached_adv and cached_adv.value:
                try:
                    adv = json.loads(cached_adv.value)
                except Exception:
                    pass
            if not adv:
                from monika.application.analysis.validators.adversarial_check import run_adversarial_check

                adv = await run_adversarial_check(session, analysis, self.settings)
            if adv.get("hard_block"):
                logger.warning(f"[{symbol}] HARD BLOCKED by adversarial check: {adv.get('hard_block_reason')}")
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=sizing,
                    risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ["adversarial_hard_block"],
                    risk_rejection_reasons=[adv.get("hard_block_reason", "")],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=elapsed,
                ), None
            if adv.get("recommend_block") and adv.get("overall_quality") == "low":
                logger.warning(
                    f"[{symbol}] Adversarial check recommends block: {adv.get('block_reason')}. Failing closed -> blocking trade."
                )
                try:
                    await AgentNotifier().send_warning(
                        f"[PERINGATAN] Adversarial Check Blocked Trade — {symbol}\n{adv.get('strongest_counter_argument', '')[:200]}"
                    )
                except Exception:
                    pass
                elapsed = int((clock.now() - start).total_seconds() * 1000)
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=sizing,
                    risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ["adversarial_recommend_block"],
                    risk_rejection_reasons=[
                        adv.get("block_reason", "Adversarial check recommended block with low quality")
                    ],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=elapsed,
                ), None

        ctx = PreflightContext(
            start=start,
            symbol=symbol,
            decision=decision,
            sizing=sizing,
            verdict=verdict,
            is_edge_signal=is_edge_signal,
            current_price=current_price,
            order_type=order_type,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            account_equity=account_equity,
            is_post_release=is_post_release,
        )
        return None, ctx
