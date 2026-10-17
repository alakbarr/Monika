# ==============================================================================
# File: application/execution/service/executors/preplanned_executor.py
# ==============================================================================

"""
Sub-second deterministic conditional trigger order execution (<100ms path).
Bypasses LLM re-analysis in the critical execution path.
"""

from __future__ import annotations

import asyncio
import logging
import math
import sys
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.execution.effect_gate import AbortRequested
from monika.core.validation.data_validator import is_spread_acceptable
from monika.application.execution.service.base import _ExecutionServiceMixinBase
from monika.domain.execution.order_creator import OrderCreator
from monika.domain.execution.sizing_calculator import SizingCalculator
from monika.domain.risk.position_sizing import PositionSizer, SizingResult, get_instrument_spec
from monika.infrastructure.brokers.broker_adapter import MT5LiveAdapter
from monika.domain.market.instrument_identity import resolve_instrument_identity
from monika.infrastructure.database.models import (
    AssetAnalysis,
    Order,
    OrderStatus,
    Position,
    SystemConfig,
)
from monika.infrastructure.database.event_store import TradingEventStore

if TYPE_CHECKING:
    from monika.application.execution.service.order_executor import ExecutionResult

logger = logging.getLogger("TradingAgent.ExecutionService.OrderExecutor")


class PreplannedOrderMixin(_ExecutionServiceMixinBase):
    """Mixin providing fast preplanned and conditional trigger order execution."""

    async def execute_preplanned_order(
        self,
        session: AsyncSession,
        symbol: str,
        order_plan: dict,
        trigger_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        account_equity: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Sub-second deterministic conditional trigger order execution (<100ms path).
        Bypasses LLM re-analysis in the critical execution path:
        1. Fast slippage validation against live tick / trigger target.
        2. Fast deterministic RiskGate evaluation (daily drawdown, max positions, spread).
        3. Immediate execution via transactional advisory lock to MT5.
        """
        from monika.application.execution.service.order_executor import (
            _EXECUTED_ANALYSIS_IDS,
            AgentNotifier,
            ExecutionResult,
            safe_commit,
            transactional_advisory_lock,
        )

        start = clock.now()
        eff_analysis_id = analysis_id or (order_plan.get("analysis_id") if isinstance(order_plan, dict) else None)

        # 0. Malformed input validation
        try:
            if not isinstance(order_plan, dict):
                raise ValueError("order_plan must be a dictionary")
            decision = (
                str(order_plan.get("direction") or order_plan.get("decision") or order_plan.get("action") or "")
                .lower()
                .strip()
            )
            target_price = float(
                order_plan.get("entry_price") or order_plan.get("target_price") or order_plan.get("price") or 0.0
            )
            sl_price = float(order_plan.get("stop_loss") or order_plan.get("sl") or 0.0)
            tp_raw = (
                order_plan.get("take_profit") if order_plan.get("take_profit") is not None else order_plan.get("tp")
            )
            tp_price = float(tp_raw) if tp_raw is not None else None
            specified_lots = float(
                order_plan.get("lot_size") or order_plan.get("recommended_lots") or order_plan.get("lots") or 0.0
            )
            order_type = str(order_plan.get("order_type") or order_plan.get("type") or "market").lower()
        except (ValueError, TypeError) as parse_err:
            elapsed = (clock.now() - start).total_seconds() * 1000
            logger.error(f"[PreplannedExecution] Malformed order_plan for {symbol}: {parse_err}")
            return ExecutionResult(
                symbol=symbol,
                analysis_id=eff_analysis_id,
                decision="unknown",
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["malformed_order_plan"],
                risk_rejection_reasons=[f"Malformed order_plan parameters: {parse_err}"],
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error=None,
                position_id=None,
                timestamp=start,
                elapsed_ms=elapsed,
            )

        logger.info(
            f"[PreplannedExecution] Fired trigger #{trigger_id} for {symbol} → {decision.upper()} @ {target_price}"
        )

        if decision not in ("buy", "sell"):
            elapsed = (clock.now() - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol,
                analysis_id=eff_analysis_id,
                decision=decision,
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["not_tradeable"],
                risk_rejection_reasons=[f"Decision '{decision}' is non-tradeable in preplanned order."],
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error=None,
                position_id=None,
                timestamp=start,
                elapsed_ms=elapsed,
            )

        # Mandatory Stop Loss Sanity Check
        if sl_price <= 0:
            elapsed = (clock.now() - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol,
                analysis_id=eff_analysis_id,
                decision=decision,
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["invalid_stop_loss"],
                risk_rejection_reasons=["Stop loss must be strictly positive (> 0) for preplanned order execution."],
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error=None,
                position_id=None,
                timestamp=start,
                elapsed_ms=elapsed,
            )

        # 1. Live price and slippage validation
        entry_price_raw, is_stale, age_seconds = await self._get_current_price(symbol, decision)
        max_price_staleness = self.settings.get("execution", {}).get("max_price_staleness_seconds", 120)
        if is_stale and age_seconds > max_price_staleness:
            elapsed = (clock.now() - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol,
                analysis_id=eff_analysis_id,
                decision=decision,
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["stale_price_data"],
                risk_rejection_reasons=[f"Price data is {age_seconds:.0f}s old (limit={max_price_staleness}s)"],
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error=None,
                position_id=None,
                timestamp=start,
                elapsed_ms=elapsed,
            )

        current_price = float(entry_price_raw) if entry_price_raw else target_price

        # Direction-aware stop loss validation against current execution price
        if decision == "buy" and sl_price >= current_price:
            elapsed = (clock.now() - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol,
                analysis_id=eff_analysis_id,
                decision=decision,
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["invalid_stop_loss"],
                risk_rejection_reasons=[
                    f"For BUY: stop_loss ({sl_price}) must be below current entry price ({current_price})"
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
        elif decision == "sell" and sl_price <= current_price:
            elapsed = (clock.now() - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol,
                analysis_id=eff_analysis_id,
                decision=decision,
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["invalid_stop_loss"],
                risk_rejection_reasons=[
                    f"For SELL: stop_loss ({sl_price}) must be above current entry price ({current_price})"
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

        if target_price > 0 and current_price > 0:
            # Percentage slippage check
            slippage_threshold = float(
                order_plan.get("max_slippage_pct")
                or self.settings.get("execution", {}).get("max_trigger_slippage_pct", 0.5)
            )
            slippage_pct = (abs(current_price - target_price) / target_price) * 100.0
            if slippage_pct > slippage_threshold:
                elapsed = (clock.now() - start).total_seconds() * 1000
                logger.warning(
                    f"[PreplannedExecution] {symbol} slippage {slippage_pct:.2f}% exceeds threshold {slippage_threshold}%"
                )
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=eff_analysis_id,
                    decision=decision,
                    sizing=None,
                    risk_approved=False,
                    risk_checks_passed=[],
                    risk_checks_failed=["slippage_exceeded"],
                    risk_rejection_reasons=[f"Trigger slippage {slippage_pct:.2f}% > threshold {slippage_threshold}%"],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=elapsed,
                )

            # Pips slippage check
            max_slippage_pips = order_plan.get("max_slippage_pips") or self.settings.get("execution", {}).get(
                "max_trigger_slippage_pips"
            )
            if max_slippage_pips is not None:
                max_slip_pips_val = float(max_slippage_pips)
                from monika.domain.market.instrument_identity import resolve_instrument_identity

                pip_size = resolve_instrument_identity(symbol).pip_size or 0.0001
                actual_slippage_pips = abs(current_price - target_price) / pip_size
                if actual_slippage_pips > max_slip_pips_val:
                    elapsed = (clock.now() - start).total_seconds() * 1000
                    logger.warning(
                        f"[PreplannedExecution] {symbol} slippage {actual_slippage_pips:.1f} pips exceeds limit {max_slip_pips_val} pips"
                    )
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=eff_analysis_id,
                        decision=decision,
                        sizing=None,
                        risk_approved=False,
                        risk_checks_passed=[],
                        risk_checks_failed=["slippage_exceeded"],
                        risk_rejection_reasons=[
                            f"Trigger slippage {actual_slippage_pips:.1f} pips > threshold {max_slip_pips_val} pips"
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

        if not self.dry_run:
            try:
                from monika.core.validation.data_validator import is_spread_acceptable

                if hasattr(self, "broker_adapter") and self.broker_adapter is not None:
                    tick = await self.broker_adapter.get_tick(symbol)
                else:
                    tick = await self.mt5.get_current_price(symbol)
                if tick and not is_spread_acceptable(symbol, tick.get("bid", 0.0), tick.get("ask", 0.0)):
                    elapsed = (clock.now() - start).total_seconds() * 1000
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=eff_analysis_id,
                        decision=decision,
                        sizing=None,
                        risk_approved=False,
                        risk_checks_passed=[],
                        risk_checks_failed=["spread_too_high"],
                        risk_rejection_reasons=["Spread too wide at trigger execution."],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=None,
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=elapsed,
                    )
            except Exception as spread_err:
                logger.debug(f"[PreplannedExecution] Spread check non-fatal: {spread_err}")

        # 2. Equity & Deterministic Sizing
        if account_equity is None:
            account_equity = await self._get_equity()
        if account_equity is None or account_equity <= 0:
            account_equity = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))

        sizing = await self.sizer.calculate_with_session(
            session=session,
            symbol=symbol,
            direction=decision,
            entry_price=current_price,
            stop_loss=sl_price,
            take_profit=tp_price,
            account_equity=account_equity,
        )

        if not sizing or not sizing.is_valid:
            elapsed = (clock.now() - start).total_seconds() * 1000
            reasons = sizing.rejection_reasons if sizing else ["Position sizing calculation failed"]
            return ExecutionResult(
                symbol=symbol,
                analysis_id=eff_analysis_id,
                decision=decision,
                sizing=sizing,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["sizing_invalid"],
                risk_rejection_reasons=reasons,
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error=None,
                position_id=None,
                timestamp=start,
                elapsed_ms=elapsed,
            )

        if specified_lots > 0:
            # Preplanned lot size provided in order_plan: clamp to broker bounds AND fortress safety cap
            spec = getattr(sizing, "_instrument_spec", None)
            try:
                max_limit = float(getattr(spec, "max_lot", 100.0))
            except TypeError, ValueError:
                max_limit = 100.0
            try:
                min_limit = float(getattr(spec, "min_lot", 0.01))
            except TypeError, ValueError:
                min_limit = 0.01
            # Preplanned lot size provided in order_plan: clamp to broker bounds
            safe_lots = round(max(min_limit, min(specified_lots, max_limit)), 2)
            sizing.recommended_lots = safe_lots
            sizing.raw_lots = specified_lots
            # Recalculate actual dollar risk based on revised lot size
            try:
                sl_dist = float(sizing.sl_distance_pips)
                pip_val = float(sizing.pip_value_per_lot)
                if sl_dist > 0 and pip_val > 0:
                    sizing.risk_amount_usd = round(sl_dist * pip_val * safe_lots, 4)
                    if account_equity and account_equity > 0:
                        sizing.risk_percent = round((sizing.risk_amount_usd / account_equity) * 100.0, 4)
            except TypeError, ValueError:
                pass

        # 3. Deterministic RiskGate Evaluation
        analysis_obj = None
        if eff_analysis_id:
            try:
                res_obj = await session.get(AssetAnalysis, eff_analysis_id)
                if isinstance(res_obj, AssetAnalysis):
                    analysis_obj = res_obj
            except Exception:
                analysis_obj = None

        priced_in_val = order_plan.get("priced_in_score")
        eff_priced_in = int(priced_in_val) if priced_in_val is not None else 5

        analysis_for_gate = analysis_obj or AssetAnalysis(
            id=eff_analysis_id,
            symbol=symbol,
            decision=decision,
            stop_loss=sl_price,
            take_profit=tp_price,
            confidence=float(order_plan.get("confidence", 0.85)),
            confluence_score=int(order_plan.get("confluence_score", 8)),
            priced_in_score=eff_priced_in,
        )

        verdict = await self.gate.check(
            session=session,
            symbol=symbol,
            direction=decision,
            sizing=sizing,
            account_equity=account_equity,
            analysis=analysis_for_gate,
            pair_group_id=order_plan.get("pair_group_id"),
        )

        if not verdict.approved:
            elapsed = (clock.now() - start).total_seconds() * 1000
            res = ExecutionResult(
                symbol=symbol,
                analysis_id=eff_analysis_id,
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
            await self._log_result(session, res, eff_analysis_id)
            return res

        # 4. Immediate execution via transactional advisory lock
        async with transactional_advisory_lock(session, lock_key=f"exec_{symbol}") as is_locked:
            if not is_locked:
                elapsed = (clock.now() - start).total_seconds() * 1000
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=eff_analysis_id,
                    decision=decision,
                    sizing=sizing,
                    risk_approved=True,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=["advisory_lock_contention"],
                    risk_rejection_reasons=["Concurrent execution locked by another transaction/worker."],
                    executed=False,
                    mt5_ticket=None,
                    executed_price=None,
                    executed_lots=None,
                    mt5_error=None,
                    position_id=None,
                    timestamp=start,
                    elapsed_ms=elapsed,
                )

            re_check_open_count = await self._count_open_positions(session)
            max_concurrent = self.settings.get("trading", {}).get("risk", {}).get("max_concurrent_positions", 5)
            if re_check_open_count >= max_concurrent:
                elapsed = (clock.now() - start).total_seconds() * 1000
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=eff_analysis_id,
                    decision=decision,
                    sizing=sizing,
                    risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=["max_concurrent_positions_reached"],
                    risk_rejection_reasons=[
                        f"Max concurrent positions reached ({re_check_open_count}/{max_concurrent})"
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

            comment = f"TRIG#{trigger_id}" if trigger_id else f"PLAN#{eff_analysis_id or 'SUB'}"
            max_spread_mult = self.settings.get("execution", {}).get("max_spread_multiplier", {}).get(symbol, 10.0)

            planned_price = (
                target_price
                if (
                    target_price > 0
                    and order_type in ("limit", "stop", "buy_limit", "sell_limit", "buy_stop", "sell_stop")
                )
                else (target_price if target_price > 0 else current_price)
            )
            # Order Lifecycle: PENDING_SUBMIT -> INTENT_COMMITTED -> SUBMITTED
            order = OrderCreator.create_order(
                symbol=symbol,
                order_type=order_type,
                direction=decision,
                requested_price=float(planned_price),
                requested_volume=float(sizing.recommended_lots),
                analysis_id=eff_analysis_id if (eff_analysis_id and analysis_obj is not None) else None,
            )
            order.replay_policy = "never"
            session.add(order)
            await self._transition_order_state(
                session, order, OrderStatus.PENDING_SUBMIT, reason="Preplanned order initialized"
            )
            await self._transition_order_state(
                session,
                order,
                OrderStatus.INTENT_COMMITTED,
                reason="Preplanned order intent committed with replay_policy=never",
                details={"trigger_id": trigger_id, "replay_policy": "never"},
            )
            await session.flush()
            await self._transition_order_state(
                session,
                order,
                OrderStatus.SUBMITTED,
                reason="Submitting preplanned order to broker adapter",
                details={"trigger_id": trigger_id, "adapter": type(self.broker_adapter).__name__},
            )
            await session.flush()

            try:
                from monika.infrastructure.database.event_store import TradingEventStore

                await TradingEventStore.emit(
                    session=session,
                    event_type="order.intent",
                    payload={
                        "order_id": order.id,
                        "symbol": order.symbol,
                        "direction": order.direction,
                        "volume": order.requested_volume,
                        "sl": sl_price,
                        "tp": tp_price,
                        "replay_policy": "never",
                    },
                    correlation_id=order.id,
                    actor="order_executor",
                )
            except Exception as e:
                logger.debug(f"Event store emit order.intent failed: {e}")

            throttler = getattr(self, "rate_throttler", None)
            if throttler is not None:
                throttle_verdict = await throttler.wait_and_acquire(timeout=5.0)
                if not throttle_verdict.allowed:
                    elapsed = (clock.now() - start).total_seconds() * 1000
                    logger.warning(
                        f"[RateThrottler] Preplanned order throttled for {symbol}: {throttle_verdict.reason}"
                    )
                    await self._transition_order_state(
                        session,
                        order,
                        OrderStatus.REJECTED,
                        reason=f"Order rate throttled: {throttle_verdict.reason}",
                    )
                    return ExecutionResult(
                        symbol=symbol,
                        analysis_id=eff_analysis_id,
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
                        context_name=f"preplanned_order_{order.client_order_id}_{symbol}",
                    )
                else:
                    mt5_result = await self.broker_adapter.submit_order(
                        order=order,
                        sl=sl_price,
                        tp=tp_price,
                        comment=comment,
                        max_spread_multiplier=max_spread_mult,
                    )

                # Self-Healing Execution: Attempt autonomous micro-repair on broker rejection
                if not mt5_result.get("success"):
                    try:
                        from monika.application.execution.service.self_healing_executor import MT5SelfHealingExecutor

                        healer = MT5SelfHealingExecutor(
                            broker_adapter=self.broker_adapter,
                            mt5_client=getattr(self.broker_adapter, "mt5_client", None),
                        )
                        mt5_result = await healer.heal_and_reexecute(
                            order=order,
                            mt5_result=mt5_result,
                            sl=sl_price,
                            tp=tp_price,
                            comment=comment,
                            max_spread_multiplier=max_spread_mult,
                            atr=getattr(sizing, "atr", None),
                            decision=decision,
                        )
                    except Exception as heal_err:
                        logger.error(f"[OrderExecutor] SelfHealingExecutor error: {heal_err}")
            except AbortRequested as abort_err:
                elapsed = (clock.now() - start).total_seconds() * 1000
                logger.warning(f"[EffectGate] Preplanned order blocked for {symbol}: {abort_err}")
                await self._transition_order_state(
                    session,
                    order,
                    OrderStatus.ABORT_REQUESTED,
                    reason=f"Effect gate blocked execution: {abort_err}",
                )
                await session.flush()
                return ExecutionResult(
                    symbol=symbol,
                    analysis_id=eff_analysis_id,
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
                elif exec_price is not None and planned_price:
                    slippage = SizingCalculator.compute_slippage_pips(float(planned_price), float(exec_price))
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
                        details={"trigger_id": trigger_id, "order_type": order.order_type, "status": "accepted"},
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
                            "trigger_id": trigger_id,
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
                        details={"trigger_id": trigger_id, "order_type": order.order_type, "status": "filled"},
                    )
            else:
                await self._transition_order_state(
                    session,
                    order,
                    OrderStatus.REJECTED,
                    reason=mt5_result.get("error") or "Broker order rejected",
                )

            elapsed = (clock.now() - start).total_seconds() * 1000
            position_id = None
            if mt5_result.get("success"):
                if not is_pending:
                    if eff_analysis_id and analysis_obj is not None:
                        _EXECUTED_ANALYSIS_IDS[eff_analysis_id] = time.time()
                        position_id = await self._save_position(
                            session=session,
                            analysis=analysis_obj,
                            sizing=sizing,
                            mt5_result=mt5_result,
                            order_id=order.id,
                        )
                    else:
                        # Save Position safely without invalid FK if analysis_obj is not persisted in DB
                        pos = Position(
                            order_id=order.id,
                            analysis_id=None,
                            mt5_ticket=mt5_result.get("ticket"),
                            symbol=symbol,
                            direction=decision,
                            volume=sizing.recommended_lots,
                            entry_price=mt5_result.get("price") or current_price,
                            sl=sl_price,
                            tp=tp_price,
                            opened_at=datetime.now(timezone.utc),
                            status="open",
                            is_paper=self.dry_run,
                        )
                        session.add(pos)
                        await session.flush()
                        position_id = pos.id
                    await session.commit()
                else:
                    await session.commit()

            exec_res = ExecutionResult(
                symbol=symbol,
                analysis_id=eff_analysis_id,
                decision=decision,
                sizing=sizing,
                risk_approved=verdict.approved,
                risk_checks_passed=verdict.checks_passed,
                risk_checks_failed=verdict.checks_failed,
                risk_rejection_reasons=verdict.rejection_reasons,
                executed=bool(mt5_result.get("success")),
                mt5_ticket=mt5_result.get("ticket"),
                executed_price=mt5_result.get("price"),
                executed_lots=sizing.recommended_lots,
                mt5_error=mt5_result.get("error"),
                position_id=position_id,
                timestamp=start,
                elapsed_ms=elapsed,
            )
            await self._log_result(session, exec_res, eff_analysis_id)
            return exec_res
