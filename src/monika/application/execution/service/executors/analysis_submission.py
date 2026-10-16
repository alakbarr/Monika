# ==============================================================================
# File: application/execution/service/executors/analysis_submission.py
# ==============================================================================

"""
Fase 2 Execution & Post-Trade Recording Mixin.
Acquires database transactional advisory lock, submits order to MT5/broker adapter,
records positions, trajectory logs, and emits notifications.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.execution.effect_gate import AbortRequested
from monika.application.execution.service.base import _ExecutionServiceMixinBase
from monika.domain.execution.order_creator import OrderCreator
from monika.domain.execution.sizing_calculator import SizingCalculator
from monika.domain.risk.position_sizing import PositionSizer
from monika.infrastructure.brokers.broker_adapter import MT5LiveAdapter
from monika.domain.market.instrument_identity import resolve_instrument_identity
from monika.infrastructure.database.models import (
    AssetAnalysis,
    Order,
    OrderEvent,
    OrderStatus,
    Position,
    SystemConfig,
    TechnicalIndicator,
    TradePlan,
    TradePlanLeg,
)
from monika.core.analytics.paper_tracker import PaperTracker

if TYPE_CHECKING:
    from monika.application.execution.service.executors.analysis_preflight import PreflightContext
    from monika.application.execution.service.order_executor import ExecutionResult

logger = logging.getLogger("TradingAgent.ExecutionService.OrderExecutor")


class AnalysisSubmissionMixin(_ExecutionServiceMixinBase):
    """Mixin providing broker order submission under transactional lock."""

    async def _submit_and_record_order(
        self,
        session: AsyncSession,
        analysis: AssetAnalysis,
        ctx: PreflightContext,
        **kwargs,
    ) -> ExecutionResult:
        """Executes order under transactional advisory lock and records post-trade audit trails."""
        from monika.application.execution.service.order_executor import (
            _EXECUTED_ANALYSIS_IDS,
            _EXECUTION_LOCK,
            AgentNotifier,
            ExecutionResult,
            _prune_executed_analysis_ids,
            safe_commit,
            transactional_advisory_lock,
        )

        start = ctx.start
        symbol = ctx.symbol
        decision = ctx.decision
        sizing = ctx.sizing
        verdict = ctx.verdict
        is_edge_signal = ctx.is_edge_signal
        current_price = ctx.current_price
        order_type = ctx.order_type
        entry_price = ctx.entry_price
        sl_price = ctx.sl_price
        tp_price = ctx.tp_price
        account_equity = ctx.account_equity
        is_post_release = ctx.is_post_release

        # Fase 2: Execution (dengan DB transactional advisory lock, singkat)
        async with transactional_advisory_lock(session, lock_key=f"exec_{symbol}") as is_locked:
            if not is_locked:
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=sizing,
                    risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ["advisory_lock_contention"],
                    risk_rejection_reasons=["Concurrent execution locked by another transaction/worker."],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=0,
                )
            # Re-check cache duplikat dan database karena mungkin ada yang mengeksekusi selama kita di Fase 1 (Validation)
            db_duplicate_pos = None
            if analysis.id:
                db_duplicate_pos = (
                    await session.execute(select(Position).where(Position.analysis_id == analysis.id).limit(1))
                ).scalar_one_or_none()

            if (analysis.id in _EXECUTED_ANALYSIS_IDS) or (db_duplicate_pos is not None):
                logger.warning(
                    f"Execution REJECTED post-lock for {symbol}: Position already executed "
                    f"while waiting for lock (analysis_id={analysis.id})."
                )
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=sizing,
                    risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ["duplicate_analysis_post_lock"],
                    risk_rejection_reasons=["Position was executed while waiting for lock."],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=0,
                )

            # Concurrency safety: Re-check portfolio limits under execution lock
            # immediately prior to MT5 order placement to prevent concurrent execution races.
            try:
                from sqlalchemy import func as _func
                from sqlalchemy import select as _select

                from monika.infrastructure.database.models import Position as _Position

                is_paper_mode = getattr(self, "dry_run", False) or bool(
                    self.settings.get("paper_trading", {}).get("enabled", True)
                )

                # Check for existing open position on the same symbol under the mutex
                symbol_open_exists = (
                    await session.execute(
                        _select(_Position.id).where(
                            _Position.symbol == symbol, _Position.status == "open", _Position.is_paper == is_paper_mode
                        )
                    )
                ).scalar_one_or_none()
                if symbol_open_exists:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    logger.warning(
                        f"[Pre-MT5 Re-check] BLOCKED {symbol}: Open position already exists for {symbol} "
                        f"(symbol race condition prevented, is_paper={is_paper_mode})."
                    )
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=analysis.id,
                        decision=decision,
                        sizing=sizing,
                        risk_approved=False,
                        risk_checks_passed=verdict.checks_passed,
                        risk_checks_failed=verdict.checks_failed + ["pre_mt5_symbol_recheck"],
                        risk_rejection_reasons=[f"Race condition guard: Open position already exists for {symbol}."],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=None,
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=elapsed,
                    )

                from monika.infrastructure.database.models import Order as _Order
                from monika.infrastructure.database.models import OrderStatus as _OrderStatus

                re_check_open_count = (
                    await session.execute(
                        _select(_func.count())
                        .select_from(_Position)
                        .where(_Position.status == "open", _Position.is_paper == is_paper_mode)
                    )
                ).scalar_one_or_none() or 0

                re_check_pending_orders = (
                    await session.execute(
                        _select(_func.count())
                        .select_from(_Order)
                        .where(
                            _Order.status.in_(
                                [
                                    _OrderStatus.SUBMITTED,
                                    _OrderStatus.INTENT_COMMITTED,
                                    _OrderStatus.ACCEPTED,
                                    _OrderStatus.PARTIALLY_FILLED,
                                ]
                            )
                        )
                    )
                ).scalar_one_or_none() or 0
                total_recheck_count = re_check_open_count + re_check_pending_orders

                max_concurrent = self.settings.get("trading", {}).get("risk", {}).get("max_concurrent_positions", 4)
                if total_recheck_count >= max_concurrent:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    logger.warning(
                        f"[Pre-MT5 Re-check] BLOCKED {symbol}: {total_recheck_count}/{max_concurrent} "
                        f"positions/orders already active (open={re_check_open_count}, pending={re_check_pending_orders}, race condition prevented)."
                    )
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=analysis.id,
                        decision=decision,
                        sizing=sizing,
                        risk_approved=False,
                        risk_checks_passed=verdict.checks_passed,
                        risk_checks_failed=verdict.checks_failed + ["pre_mt5_position_recheck"],
                        risk_rejection_reasons=[
                            f"Race condition guard: {re_check_open_count} positions open "
                            f"(limit={max_concurrent}). Position filled between risk check and execution."
                        ],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=None,
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=elapsed,
                    )
            except Exception as recheck_err:
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                logger.error(f"Pre-MT5 position re-check failed (Fail-Closed): {recheck_err}")
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=analysis.id,
                    decision=decision,
                    sizing=sizing,
                    risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ["pre_mt5_recheck_exception"],
                    risk_rejection_reasons=[f"Race condition guard query failed (Fail-Closed): {recheck_err}"],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=elapsed,
                )

            # Pilar 4: Evidence-First Pre-Trade Assertions
            verifier_enabled = (
                self.settings.get("trading", {}).get("risk", {}).get("confluence_verifier_enabled", False)
            )
            if verifier_enabled and hasattr(self, "evidence_verifier") and self.evidence_verifier:
                try:
                    key_evidence = []
                    raw_ev = getattr(analysis, "key_evidence", None)
                    if raw_ev:
                        if isinstance(raw_ev, list):
                            key_evidence = raw_ev
                        elif isinstance(raw_ev, str):
                            try:
                                key_evidence = json.loads(raw_ev)
                            except Exception:
                                key_evidence = [s.strip() for s in raw_ev.split("\n") if s.strip()]
                    if not key_evidence:
                        cf_raw = getattr(analysis, "confluence_factors_json", None) or getattr(
                            analysis, "confluence_factors", None
                        )
                        if cf_raw:
                            if isinstance(cf_raw, list):
                                key_evidence = cf_raw
                            elif isinstance(cf_raw, str):
                                try:
                                    key_evidence = json.loads(cf_raw)
                                except Exception:
                                    key_evidence = [s.strip() for s in cf_raw.split("\n") if s.strip()]
                    if not key_evidence:
                        rat = getattr(analysis, "rationale", "") or ""
                        key_evidence = [s.strip() for s in rat.split(".") if len(s.strip()) > 10][:3]

                    signal_dict = {
                        "symbol": symbol,
                        "decision": decision,
                        "entry_price": entry_price,
                        "stop_loss": sl_price,
                        "take_profit": tp_price,
                        "confidence": analysis.confidence,
                        "confluence_score": analysis.confluence_score,
                        "priced_in_score": analysis.priced_in_score,
                        "invalidation": getattr(analysis, "invalidation_condition", None)
                        or analysis.invalidation
                        or str(analysis.invalidation_price or ""),
                        "key_evidence": key_evidence,
                        "confluence_factors_json": key_evidence,
                        "rationale": getattr(analysis, "rationale", ""),
                        "decision_source": getattr(analysis, "decision_source", None),
                        "source_strategy_id": getattr(analysis, "source_strategy_id", None),
                    }
                    passed, assertions_failed = await self.evidence_verifier.pre_trade_assertions(
                        signal_dict, session=session
                    )
                    if not passed:
                        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                        logger.warning(f"Pre-trade assertions failed for {symbol}: {assertions_failed}")
                        return ExecutionResult(
                            symbol=symbol,
                            analysis_id=analysis.id,
                            decision=decision,
                            sizing=sizing,
                            risk_approved=False,
                            risk_checks_passed=verdict.checks_passed,
                            risk_checks_failed=verdict.checks_failed + ["evidence_first_assertions"],
                            risk_rejection_reasons=assertions_failed,
                            executed=False,
                            mt5_ticket=None,
                            executed_price=None,
                            executed_lots=None,
                            mt5_error=None,
                            position_id=None,
                            timestamp=start,
                            elapsed_ms=elapsed,
                        )
                except Exception as ev_err:
                    logger.debug(f"Pre-trade assertions non-fatal check error: {ev_err}")

            # Langkah 3: Eksekusi MT5 / Broker Adapter
            comment = f"AI#{analysis.id}"
            max_spread_mult = self.settings.get("execution", {}).get("max_spread_multiplier", {}).get(symbol, 10.0)

            # Order Lifecycle: PENDING_SUBMIT -> INTENT_COMMITTED -> SUBMITTED
            order = OrderCreator.create_order(
                symbol=symbol,
                order_type=order_type,
                direction=decision,
                requested_price=float(entry_price),
                requested_volume=float(sizing.recommended_lots),
                analysis_id=analysis.id,
            )
            order.replay_policy = "never"
            session.add(order)
            await self._transition_order_state(
                session, order, OrderStatus.PENDING_SUBMIT, reason="Analysis order initialized"
            )
            await self._transition_order_state(
                session,
                order,
                OrderStatus.INTENT_COMMITTED,
                reason="Order intent committed to database with replay_policy=never",
                details={
                    "analysis_id": analysis.id,
                    "adapter": type(self.broker_adapter).__name__,
                    "replay_policy": "never",
                },
            )
            await session.flush()
            await self._transition_order_state(
                session,
                order,
                OrderStatus.SUBMITTED,
                reason="Submitting analysis order to broker adapter",
                details={"analysis_id": analysis.id, "adapter": type(self.broker_adapter).__name__},
            )
            await session.flush()

            throttler = getattr(self, "rate_throttler", None)
            if throttler is not None:
                throttle_verdict = await throttler.wait_and_acquire(timeout=5.0)
                if not throttle_verdict.allowed:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    logger.warning(f"[RateThrottler] Analysis order throttled for {symbol}: {throttle_verdict.reason}")
                    await self._transition_order_state(
                        session,
                        order,
                        OrderStatus.REJECTED,
                        reason=f"Order rate throttled: {throttle_verdict.reason}",
                    )
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=analysis.id,
                        decision=decision,
                        sizing=sizing,
                        risk_approved=False,
                        risk_checks_passed=verdict.checks_passed,
                        risk_checks_failed=verdict.checks_failed + ["order_rate_throttled"],
                        risk_rejection_reasons=[
                            f"Order rate throttled: {throttle_verdict.reason}. Retry after {throttle_verdict.retry_after}s"
                        ],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=f"Throttled: {throttle_verdict.reason}",
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=elapsed,
                    )

            await _EXECUTION_LOCK.acquire()
            is_pending: bool = False
            mt5_result: dict[str, Any] = {}
            position_id: Optional[int] = None
            try:
                # R-1: Race condition pre-MT5 position re-check under global execution mutex
                try:
                    re_check_open_count = (
                        await session.execute(
                            select(func.count())
                            .select_from(Position)
                            .where(Position.status == "open", Position.is_paper == is_paper_mode)
                        )
                    ).scalar_one_or_none() or 0
                    re_check_pending_orders = (
                        await session.execute(
                            select(func.count())
                            .select_from(Order)
                            .where(
                                Order.id != order.id,
                                Order.status.in_(
                                    [
                                        OrderStatus.SUBMITTED,
                                        OrderStatus.INTENT_COMMITTED,
                                        OrderStatus.ACCEPTED,
                                        OrderStatus.PARTIALLY_FILLED,
                                    ]
                                ),
                            )
                        )
                    ).scalar_one_or_none() or 0
                    total_exposure_count = re_check_open_count + re_check_pending_orders
                    max_concurrent = self.settings.get("trading", {}).get("risk", {}).get("max_concurrent_positions", 5)
                    if total_exposure_count >= max_concurrent:
                        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                        logger.warning(
                            f"[Pre-MT5 Re-check] BLOCKED {symbol}: {total_exposure_count}/{max_concurrent} active positions/orders (open={re_check_open_count}, pending={re_check_pending_orders}, race condition prevented)."
                        )
                        await self._transition_order_state(
                            session,
                            order,
                            OrderStatus.REJECTED,
                            reason=f"Race condition guard: {total_exposure_count} active positions/orders (limit={max_concurrent})",
                        )
                        return ExecutionResult(
                            symbol=symbol,
                            analysis_id=analysis.id,
                            decision=decision,
                            sizing=sizing,
                            risk_approved=False,
                            risk_checks_passed=verdict.checks_passed,
                            risk_checks_failed=verdict.checks_failed + ["pre_mt5_position_recheck"],
                            risk_rejection_reasons=[
                                f"Race condition guard: {re_check_open_count} positions open (limit={max_concurrent}). Position filled between risk check and execution."
                            ],
                            executed=False,
                            mt5_ticket=None,
                            executed_price=None,
                            executed_lots=None,
                            mt5_error=None,
                            position_id=None,
                            timestamp=start,
                            elapsed_ms=elapsed,
                        )
                except Exception as recheck_err:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    logger.error(f"Pre-MT5 position re-check failed (Fail-Closed): {recheck_err}")
                    await self._transition_order_state(
                        session,
                        order,
                        OrderStatus.REJECTED,
                        reason=f"Race condition guard query failed (Fail-Closed): {recheck_err}",
                    )
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=analysis.id,
                        decision=decision,
                        sizing=sizing,
                        risk_approved=False,
                        risk_checks_passed=verdict.checks_passed,
                        risk_checks_failed=verdict.checks_failed + ["pre_mt5_recheck_exception"],
                        risk_rejection_reasons=[f"Position re-check query failed (Fail-Closed): {recheck_err}"],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=None,
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=elapsed,
                    )

                # Submit order to broker adapter under EffectGate admission
                try:
                    if self.broker_adapter is None:
                        raise RuntimeError("Broker adapter is not initialized")
                    if hasattr(self, "effect_gate") and self.effect_gate is not None:
                        mt5_result = await self.effect_gate.admit(
                            lambda: self.broker_adapter.submit_order(
                                order=order,
                                sl=sl_price,
                                tp=tp_price,
                                comment=comment,
                                max_spread_multiplier=max_spread_mult,
                            ),
                            context_name=f"order_{order.client_order_id}_{symbol}",
                        )
                    else:
                        mt5_result = await self.broker_adapter.submit_order(
                            order=order,
                            sl=sl_price,
                            tp=tp_price,
                            comment=comment,
                            max_spread_multiplier=max_spread_mult,
                        )
                except AbortRequested as abort_err:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    logger.warning(f"[EffectGate] Order blocked for {symbol}: {abort_err}")
                    await self._transition_order_state(
                        session,
                        order,
                        OrderStatus.ABORT_REQUESTED,
                        reason=f"Effect gate blocked execution: {abort_err}",
                    )
                    await session.flush()
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=analysis.id,
                        decision=decision,
                        sizing=sizing,
                        risk_approved=False,
                        risk_checks_passed=verdict.checks_passed,
                        risk_checks_failed=verdict.checks_failed + ["effect_gate_aborted"],
                        risk_rejection_reasons=[f"Effect gate blocked execution: {abort_err}"],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=str(abort_err),
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=elapsed,
                    )

                is_pending: bool = False
                if mt5_result.get("success"):
                    status_returned = mt5_result.get("status")
                    is_pending = status_returned in ("accepted", "pending") or (
                        (order.order_type or "").upper()
                        in ("LIMIT", "STOP", "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP")
                        and float(mt5_result.get("executed_volume", 0.0)) == 0.0
                    )
                    exec_vol = float(mt5_result.get("executed_volume", 0.0))
                    req_vol = float(order.requested_volume)

                    reported_slippage = mt5_result.get("slippage_pips")
                    exec_price = mt5_result.get("price")
                    if reported_slippage is not None:
                        slippage = float(reported_slippage)
                    elif exec_price is not None and entry_price:
                        from monika.domain.market.instrument_identity import resolve_instrument_identity

                        sym_id = resolve_instrument_identity(order.symbol or symbol)
                        slippage = SizingCalculator.compute_slippage_pips(
                            float(entry_price), float(exec_price), pip_size=sym_id.pip_size
                        )
                    else:
                        slippage = 0.0

                    if is_pending:
                        await self._transition_order_state(
                            session,
                            order,
                            OrderStatus.ACCEPTED,
                            reason=f"Broker accepted pending order: ticket={mt5_result.get('ticket')}",
                            ticket=mt5_result.get("ticket"),
                            executed_price=exec_price,
                            slippage_pips=slippage,
                            filled_volume=0.0,
                            details={"analysis_id": analysis.id, "order_type": order.order_type, "status": "accepted"},
                        )
                    elif 0.0 < exec_vol < req_vol:
                        await self._transition_order_state(
                            session,
                            order,
                            OrderStatus.PARTIALLY_FILLED,
                            reason=f"Partially filled {exec_vol}/{req_vol} lots at {exec_price}, ticket={mt5_result.get('ticket')}",
                            ticket=mt5_result.get("ticket"),
                            executed_price=exec_price,
                            slippage_pips=slippage,
                            filled_volume=exec_vol,
                            details={
                                "analysis_id": analysis.id,
                                "order_type": order.order_type,
                                "status": "partially_filled",
                                "filled_volume": exec_vol,
                            },
                        )
                    else:
                        await self._transition_order_state(
                            session,
                            order,
                            OrderStatus.FILLED,
                            reason=f"Filled at {exec_price}, ticket={mt5_result.get('ticket')}",
                            ticket=mt5_result.get("ticket"),
                            executed_price=exec_price,
                            slippage_pips=slippage,
                            filled_volume=exec_vol if exec_vol > 0 else req_vol,
                            details={"analysis_id": analysis.id, "order_type": order.order_type, "status": "filled"},
                        )
                else:
                    await self._transition_order_state(
                        session,
                        order,
                        OrderStatus.REJECTED,
                        reason=mt5_result.get("error") or "Broker order rejected",
                    )

                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000

                # Step 4: Persist position to database if order is directly filled (market order)
                position_id = None
                if mt5_result.get("success"):
                    # Update executed cache upon successful MT5 placement (Cache-Before-Commit pattern)
                    _EXECUTED_ANALYSIS_IDS[analysis.id] = time.time()

                    if not is_pending:
                        try:
                            position_id = await self._save_position(
                                session=session,
                                analysis=analysis,
                                sizing=sizing,
                                mt5_result=mt5_result,
                                order_id=order.id,
                            )
                            if position_id is None:
                                raise RuntimeError(
                                    f"Failed to persist position to DB for ticket {mt5_result.get('ticket')}"
                                )
                            await session.commit()
                        except Exception as db_err:
                            logger.critical(
                                f"DB save failed after MT5 order {mt5_result.get('ticket')}. CLOSING orphan position."
                            )
                            orphan_ticket = mt5_result.get("ticket")
                            try:
                                if not self.dry_run and orphan_ticket is not None:
                                    if hasattr(self, "broker_adapter") and self.broker_adapter:
                                        await self.broker_adapter.close_position(int(orphan_ticket))
                                    else:
                                        await self.mt5.close_position(int(orphan_ticket))
                            except Exception as close_err:
                                await AgentNotifier().send_critical(
                                    f"ORPHAN TRADE: ticket={orphan_ticket} {symbol}. DB and close both failed!"
                                )
                            raise

                        # Buka record paper trade untuk pelacakan (berlaku untuk dry-run & live)
                        try:
                            from monika.core.analytics.paper_tracker import PaperTracker

                            paper_tracker = PaperTracker(self.settings)
                            eff_risk_pct = sizing.risk_percent
                            await paper_tracker.open_paper_trade(session, analysis, risk_pct=eff_risk_pct)
                        except Exception as e:
                            logger.debug(f"Paper trade open failed (non-fatal): {e}")
                    else:
                        await session.commit()
            finally:
                _EXECUTION_LOCK.release()

                # Stateful Multi-Phase Trade Plan (Probe 30%, Runner 70%)
                try:
                    from monika.infrastructure.database.models import TechnicalIndicator, TradePlan, TradePlanLeg

                    total_lots = sizing.recommended_lots
                    if total_lots <= 0.01:
                        probe_lots = round(total_lots, 2)
                        runner_lots = 0.0
                    else:
                        probe_lots = round(max(0.01, round(total_lots * 0.30, 2)), 2)
                        runner_lots = round(max(0.0, round(total_lots - probe_lots, 2)), 2)

                    atr_val = None
                    atr_row = (
                        await session.execute(
                            select(TechnicalIndicator)
                            .where(
                                TechnicalIndicator.symbol == symbol,
                                TechnicalIndicator.timeframe == "H1",
                                TechnicalIndicator.indicator_name == "ATR_14",
                            )
                            .order_by(TechnicalIndicator.timestamp.desc())
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    if atr_row:
                        try:
                            atr_val = float(json.loads(atr_row.value_json))
                        except Exception:
                            pass

                    if not atr_val or atr_val <= 0:
                        atr_val = entry_price * 0.005

                    tp1_price = round(
                        entry_price + (1.0 * atr_val) if decision == "buy" else entry_price - (1.0 * atr_val), 5
                    )
                    tp2_price = tp_price or round(
                        entry_price + (2.0 * atr_val) if decision == "buy" else entry_price - (2.0 * atr_val), 5
                    )

                    plan_status = "PENDING_PROBE" if is_pending else "CONFIRMED_SCALE_IN"
                    leg_status = "pending" if is_pending else "filled"
                    leg_actual_entry = None if is_pending else entry_price
                    leg_filled_at = None if is_pending else datetime.now(timezone.utc)

                    trade_plan = TradePlan(
                        analysis_id=analysis.id,
                        symbol=symbol,
                        direction=decision,
                        status=plan_status,
                        entry_price=entry_price,
                        stop_loss=sl_price,
                        take_profit=tp_price,
                        take_profit_1=tp1_price,
                        take_profit_2=tp2_price,
                        total_volume=total_lots,
                        atr_at_creation=atr_val,
                        notes=f"Multi-phase trade plan: probe={probe_lots}L (30%), runner={runner_lots}L (70%), TP1={tp1_price}",
                    )
                    session.add(trade_plan)
                    await session.flush()

                    legs_to_add = []
                    probe_leg = TradePlanLeg(
                        plan_id=trade_plan.id,
                        leg_type="probe",
                        volume=probe_lots,
                        target_entry=entry_price,
                        actual_entry=leg_actual_entry,
                        stop_loss=sl_price,
                        take_profit=tp1_price,
                        ticket_id=mt5_result.get("ticket"),
                        position_id=position_id,
                        status=leg_status,
                        filled_at=leg_filled_at,
                    )
                    legs_to_add.append(probe_leg)

                    if runner_lots > 0:
                        runner_leg = TradePlanLeg(
                            plan_id=trade_plan.id,
                            leg_type="runner",
                            volume=runner_lots,
                            target_entry=entry_price,
                            actual_entry=leg_actual_entry,
                            stop_loss=sl_price,
                            take_profit=tp2_price,
                            ticket_id=mt5_result.get("ticket"),
                            position_id=position_id,
                            status=leg_status,
                            filled_at=leg_filled_at,
                        )
                        legs_to_add.append(runner_leg)

                    session.add_all(legs_to_add)
                    await session.commit()
                    logger.info(
                        f"[{symbol}] Created TradePlan #{trade_plan.id}: probe={probe_lots}L (30%), runner={runner_lots}L (70%)"
                    )
                except Exception as tp_err:
                    logger.debug(f"TradePlan creation non-fatal: {tp_err}")

                # Log AI Decision (Real Trade)
                try:
                    from monika.application.analysis.memory.decision_log import DecisionLogger

                    await DecisionLogger.log_decision(
                        session=session,
                        analysis_id=analysis.id,
                        symbol=symbol,
                        decision=decision,
                        confidence=analysis.confidence or 0.0,
                        confluence_score=analysis.confluence_score,
                        rationale=analysis.rationale or "",
                    )
                except Exception as e:
                    logger.debug(f"Failed to log AI decision: {e}")

                # Zero-Trust Verification & Trajectory Logging (Pilar 4 & Pilar 5)
                try:
                    if isinstance(self.broker_adapter, MT5LiveAdapter):
                        verif_res = await self.evidence_verifier.post_execution_reconciliation(
                            mt5_result, mt5_client=self.mt5, session=session
                        )
                        if verif_res and not verif_res.get("verified", True):
                            issues = verif_res.get("issues", [])
                            logger.error(f"[{symbol}] Zero-Trust verification flagged issues post-execution: {issues}")
                            try:
                                await AgentNotifier().send_warning(
                                    f"[PERINGATAN] <b>Execution Verification Flagged</b>\n"
                                    f"Symbol: {symbol} Ticket: {mt5_result.get('ticket')}\n"
                                    f"Issues: {'; '.join(issues)}"
                                )
                            except Exception:
                                pass

                    spec_out = {}
                    spec_biases = getattr(analysis, "specialist_biases_json", None)
                    if isinstance(spec_biases, str):
                        try:
                            spec_out = json.loads(spec_biases)
                        except Exception:
                            pass

                    fund_brief = {}
                    if getattr(analysis, "brief_id", None):
                        fund_brief = {"brief_id": analysis.brief_id}

                    deb_verdict = {}
                    if getattr(analysis, "debate_verdict", None):
                        deb_verdict = {
                            "verdict": analysis.debate_verdict,
                            "bull_thesis": getattr(analysis, "debate_bull_thesis", None),
                            "bear_dissent": getattr(analysis, "debate_bear_dissent", None),
                            "reason": getattr(analysis, "debate_reason", None),
                        }

                    self.trajectory_logger.log_trajectory(
                        symbol=symbol,
                        decision=decision,
                        ticket=mt5_result.get("ticket"),
                        fundamental_brief=fund_brief,
                        specialist_outputs=spec_out,
                        debate_verdict=deb_verdict,
                        risk_decision={
                            "approved": True,
                            "lots": sizing.recommended_lots,
                            "ticket": mt5_result.get("ticket"),
                        },
                        execution_details=mt5_result,
                    )
                except Exception as verif_err:
                    logger.debug(f"Verification/Trajectory logging non-fatal error: {verif_err}")

                # Update timestamp eksekusi sukses terakhir
                try:
                    exec_key = "last_successful_execution"
                    cfg = (
                        await session.execute(select(SystemConfig).where(SystemConfig.key == exec_key))
                    ).scalar_one_or_none()
                    exec_info = json.dumps(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "symbol": symbol,
                            "direction": decision,
                            "lots": sizing.recommended_lots,
                        }
                    )
                    if cfg:
                        cfg.value = exec_info
                    else:
                        session.add(SystemConfig(key=exec_key, value=exec_info))
                    await session.commit()
                except Exception as e:
                    logger.debug(f"Failed to update last_successful_execution (non-fatal): {e}")

        result = ExecutionResult(
            symbol=symbol,
            analysis_id=analysis.id,
            decision=decision,
            sizing=sizing,
            risk_approved=True,
            risk_checks_passed=verdict.checks_passed,
            risk_checks_failed=verdict.checks_failed,
            risk_rejection_reasons=[],
            executed=mt5_result.get("success", False),
            mt5_ticket=mt5_result.get("ticket"),
            executed_price=mt5_result.get("price"),
            executed_lots=sizing.recommended_lots if mt5_result.get("success") else None,
            mt5_error=mt5_result.get("error"),
            position_id=position_id,
            timestamp=start,
            elapsed_ms=elapsed,
        )

        await self._log_result(session, result, analysis.id)

        if result.executed:
            logger.info(f"TRADE PLACED: {result.summary()}")
            try:
                from monika.application.graph.nodes.risk.proposal_notifier import send_execution_notification

                await send_execution_notification(analysis, result)
            except Exception as e:
                logger.error(f"Failed to dispatch institutional execution card: {e}", exc_info=True)
                try:
                    notifier = AgentNotifier()
                    msg = (
                        f"<b>[AUTO-EXECUTION] {result.symbol} — {result.decision.upper()}</b>\n\n"
                        f"<b>Execution & Parameters:</b>\n"
                        f"• <b>Action:</b> {result.decision.upper()}\n"
                        f"• <b>Broker Status:</b> Filled on MT5 (Ticket: <code>{result.mt5_ticket}</code>)\n"
                        f"• <b>Volume:</b> {result.executed_lots} lots\n"
                        f"• <b>Entry:</b> <code>{result.executed_price}</code>\n\n"
                        f"<i>Use <code>/close {result.mt5_ticket}</code> to terminate this position early.</i>"
                    )
                    await notifier.send_info(msg)
                except Exception as fb_err:
                    logger.debug(f"Fallback notification failed: {fb_err}")
        else:
            logger.error(f"TRADE FAILED: {result.summary()}")
            try:
                notifier = AgentNotifier()
                await notifier.send_warning(f"<b>[TRADE FAILED]</b>\n{result.summary()}")
            except Exception as e:
                logger.error(f"Failed to notify trade failure: {e}")
        _prune_executed_analysis_ids()

        return result
