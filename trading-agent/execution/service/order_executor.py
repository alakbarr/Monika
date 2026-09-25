# ==============================================================================
# File: execution/service/order_executor.py
# ==============================================================================

import asyncio
import json
import logging
import math
import uuid
import time
import sys
import inspect
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from unittest.mock import MagicMock

from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
import utils.clock as clock

import database.db as _db_mod
from database.safe_ops import safe_commit
from database.models import (
    AssetAnalysis, Position, OrderLog, ActivityLog, RiskState, SystemConfig,
    Order, OrderStatus, OrderEvent, PaperTradeRecord
)
from execution.mt5_client import MT5Client
from execution.broker_adapter import BrokerAdapter, MT5LiveAdapter
from execution.service.order_creator import OrderCreator
from execution.service.sizing_calculator import SizingCalculator
from risk.position_sizing import PositionSizer, SizingResult, get_instrument_spec
from risk.risk_gate import RiskGate
from utils.infra.notifier import AgentNotifier
from execution.effect_gate import EffectGate, AbortRequested

def get_session(*args, **kwargs):
    es = sys.modules.get("execution.execution_service")
    if es and hasattr(es, "get_session"):
        return es.get_session(*args, **kwargs)
    return _db_mod.get_session(*args, **kwargs)

def transactional_advisory_lock(*args, **kwargs):
    es = sys.modules.get("execution.execution_service")
    if es and hasattr(es, "transactional_advisory_lock"):
        return es.transactional_advisory_lock(*args, **kwargs)
    return _db_mod.transactional_advisory_lock(*args, **kwargs)


@dataclass
class ExecutionResult:
    """Hasil lengkap dari percobaan eksekusi, mulai dari sizing hingga MT5."""
    symbol: str
    analysis_id: Optional[int]
    decision: str                     # buy | sell | avoid | wait

    # Sizing
    sizing: Optional[SizingResult]

    # Risk gate
    risk_approved: bool
    risk_checks_passed: list[str]
    risk_checks_failed: list[str]
    risk_rejection_reasons: list[str]

    # MT5 execution
    executed: bool
    mt5_ticket: Optional[int]
    executed_price: Optional[float]
    executed_lots: Optional[float]
    mt5_error: Optional[str]

    # DB
    position_id: Optional[int]

    # Metadata
    timestamp: datetime
    elapsed_ms: float

    def summary(self) -> str:
        if not self.risk_approved:
            return (
                f"BLOCKED [{self.symbol}] {self.decision.upper()} — "
                f"RiskGate: {'; '.join(self.risk_rejection_reasons)}"
            )
        if self.executed:
            return (
                f"EXECUTED [{self.symbol}] {self.decision.upper()} "
                f"{self.executed_lots}lots @ {self.executed_price} | "
                f"ticket={self.mt5_ticket}"
            )
        return (
            f"FAILED [{self.symbol}] {self.decision.upper()} — "
            f"MT5: {self.mt5_error}"
        )



_EXECUTED_ANALYSIS_IDS = {}
_LAST_CLEANUP_TIME = time.time()
_EXECUTION_LOCK = asyncio.Lock()


def _prune_executed_analysis_ids(ttl_seconds: float = 86400.0) -> None:
    """
    Prune entries in _EXECUTED_ANALYSIS_IDS older than ttl_seconds (default 24h / 86,400s)
    to prevent memory leak over weeks of 24/7 uptime (M-8).
    Mutates dictionary in-place to preserve reference identity across imports.
    """
    global _LAST_CLEANUP_TIME
    now = time.time()
    if (now - _LAST_CLEANUP_TIME) >= 60.0 or len(_EXECUTED_ANALYSIS_IDS) > 200:
        expired = []
        for aid, ts in list(_EXECUTED_ANALYSIS_IDS.items()):
            if not isinstance(ts, (int, float)) or isinstance(ts, bool) or (now - ts) >= ttl_seconds:
                expired.append(aid)
        for aid in expired:
            _EXECUTED_ANALYSIS_IDS.pop(aid, None)
        _LAST_CLEANUP_TIME = now


from execution.service.base import _ExecutionServiceMixinBase

logger = logging.getLogger("TradingAgent.ExecutionService.OrderExecutor")

class OrderExecutorMixin(_ExecutionServiceMixinBase):
    """Mixin untuk alur eksekusi order (analisis tunggal, berpasangan, preplanned)."""

    async def _transition_order_state(
        self,
        session: AsyncSession,
        order: Order,
        new_status: OrderStatus,
        reason: Optional[str] = None,
        details: Optional[dict] = None,
        executed_price: Optional[float] = None,
        ticket: Optional[int] = None,
        slippage_pips: Optional[float] = None,
        filled_volume: Optional[float] = None,
    ) -> None:
        """
        Record order state transition in DB (Order + OrderEvent audit trail)
        and broadcast OrderStateChangedEvent on EventBus via OrderStateMachine.
        """
        from execution.service.state_machine import OrderStateMachine
        await OrderStateMachine.transition_order_state(
            session=session,
            order=order,
            new_status=new_status,
            reason=reason,
            details=details,
            executed_price=executed_price,
            ticket=ticket,
            slippage_pips=slippage_pips,
            filled_volume=filled_volume,
        )

    async def _restore_executed_ids_from_db(self):
        """Load recently executed analysis IDs from DB to prevent duplicate execution after restart."""
        from execution.service.reconciliation import ReconciliationHelper
        async with get_session() as session:
            await ReconciliationHelper.restore_executed_ids_from_db(session, _EXECUTED_ANALYSIS_IDS)



    async def execute_analysis(
        self,
        session: AsyncSession,
        analysis: AssetAnalysis,
        account_equity: Optional[float] = None,
        is_post_release: bool = False,
        **kwargs
    ) -> ExecutionResult:
        """Memproses satu AssetAnalysis melalui pipeline eksekusi lengkap."""
        # F-1: Execution lock dipisah menjadi Fase 2 (Validation berjalan paralel)
        return await self._execute_analysis_internal(
            session, analysis, account_equity, is_post_release=is_post_release, **kwargs
        )

    async def execute_proposal(
        self,
        session: AsyncSession,
        proposal: Any,
        account_equity: Optional[float] = None,
    ) -> ExecutionResult:
        """
        PR-14: Financial Fortress entrypoint executing an immutable TradeProposal.
        First validates the proposal via FortressAdmissionValidator and RiskGate.evaluate_proposal.
        If admitted and approved, executes order.
        """
        start = clock.now()
        from risk.trade_proposal import FortressAdmissionValidator
        admitted, rejections = FortressAdmissionValidator.validate_proposal(proposal)
        if not admitted:
            elapsed = (clock.now() - start).total_seconds() * 1000
            logger.warning(f"[{proposal.symbol}] execute_proposal rejected by Fortress: {rejections}")
            return ExecutionResult(
                symbol=proposal.symbol,
                analysis_id=proposal.metadata.get("analysis_id"),
                decision=proposal.direction.lower(),
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["fortress_admission"],
                risk_rejection_reasons=rejections,
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error="Fortress admission rejection",
                position_id=None,
                timestamp=start,
                elapsed_ms=elapsed,
            )

        # PR-15: Acquire idempotency lock to prevent duplicate order placement
        from execution.idempotency_guard import get_idempotency_guard
        guard = getattr(self, "idempotency_guard", None) or get_idempotency_guard()
        idem_key = guard.generate_key(
            symbol=proposal.symbol,
            direction=proposal.direction,
            entry_price=proposal.entry_price,
            analysis_id=proposal.metadata.get("analysis_id"),
            proposal_id=getattr(proposal, "proposal_id", None),
        )
        lock_acquired, reject_msg = await guard.acquire_lock(
            key=idem_key,
            symbol=proposal.symbol,
            direction=proposal.direction,
        )
        if not lock_acquired:
            elapsed = (clock.now() - start).total_seconds() * 1000
            logger.warning(f"[{proposal.symbol}] Duplicate order blocked by IdempotencyGuard: {reject_msg}")
            return ExecutionResult(
                symbol=proposal.symbol,
                analysis_id=proposal.metadata.get("analysis_id"),
                decision=proposal.direction.lower(),
                sizing=None,
                risk_approved=False,
                risk_checks_passed=[],
                risk_checks_failed=["idempotency_blocked"],
                risk_rejection_reasons=[reject_msg or "Duplicate order blocked"],
                executed=False,
                mt5_ticket=None,
                executed_price=None,
                executed_lots=None,
                mt5_error="Duplicate order blocked by IdempotencyGuard",
                position_id=None,
                timestamp=start,
                elapsed_ms=elapsed,
            )

        order_plan = {
            "symbol": proposal.symbol,
            "decision": proposal.direction.lower(),
            "entry_price": proposal.entry_price,
            "stop_loss": proposal.stop_loss,
            "take_profit": proposal.take_profit,
            "lot_size": proposal.lot_size,
            "confluence_score": int(proposal.confluence_score),
            "analysis_id": proposal.metadata.get("analysis_id"),
            "pair_group_id": proposal.metadata.get("pair_group_id"),
        }

        # Pre-order waterfall hook
        try:
            from harness.engine import get_plugin_engine
            engine = get_plugin_engine()
            if engine:
                allowed, plan_or_reason = await engine.emit_waterfall(
                    "pre_order",
                    order_plan,
                    proposal=proposal,
                    symbol=proposal.symbol,
                )
                if not allowed:
                    elapsed = (clock.now() - start).total_seconds() * 1000
                    logger.warning(f"[{proposal.symbol}] Pre-order vetoed by plugin hook: {plan_or_reason}")
                    return ExecutionResult(
                        symbol=proposal.symbol,
                        analysis_id=proposal.metadata.get("analysis_id"),
                        decision=proposal.direction.lower(),
                        sizing=None,
                        risk_approved=False,
                        risk_checks_passed=[],
                        risk_checks_failed=["plugin_hook_veto"],
                        risk_rejection_reasons=[str(plan_or_reason)],
                        executed=False,
                        mt5_ticket=None,
                        executed_price=None,
                        executed_lots=None,
                        mt5_error=f"Plugin hook veto: {plan_or_reason}",
                        position_id=None,
                        timestamp=start,
                        elapsed_ms=elapsed,
                    )
                if isinstance(plan_or_reason, dict):
                    order_plan = plan_or_reason
        except Exception as hook_err:
            logger.debug(f"[OrderExecutor] pre_order hook notice: {hook_err}")

        res = await self.execute_preplanned_order(
            session=session,
            symbol=proposal.symbol,
            order_plan=order_plan,
            analysis_id=proposal.metadata.get("analysis_id"),
            account_equity=account_equity or proposal.account_equity,
        )

        # Post-order hook
        try:
            from harness.engine import get_plugin_engine
            engine = get_plugin_engine()
            if engine:
                await engine.emit_hook("post_order", result=res, order_plan=order_plan, proposal=proposal)
        except Exception as hook_err:
            logger.debug(f"[OrderExecutor] post_order hook notice: {hook_err}")

        if res.executed and res.mt5_ticket:
            await guard.mark_completed(idem_key, ticket=res.mt5_ticket)
        elif not res.risk_approved:
            await guard.release_lock(idem_key)
        else:
            await guard.mark_failed(idem_key, error=res.mt5_error or "Order execution failed")

        return res

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
        start = clock.now()
        eff_analysis_id = analysis_id or (order_plan.get("analysis_id") if isinstance(order_plan, dict) else None)

        # 0. Malformed input validation
        try:
            if not isinstance(order_plan, dict):
                raise ValueError("order_plan must be a dictionary")
            decision = str(order_plan.get("direction") or order_plan.get("decision") or order_plan.get("action") or "").lower().strip()
            target_price = float(order_plan.get("entry_price") or order_plan.get("target_price") or order_plan.get("price") or 0.0)
            sl_price = float(order_plan.get("stop_loss") or order_plan.get("sl") or 0.0)
            tp_raw = order_plan.get("take_profit") if order_plan.get("take_profit") is not None else order_plan.get("tp")
            tp_price = float(tp_raw) if tp_raw is not None else None
            specified_lots = float(order_plan.get("lot_size") or order_plan.get("recommended_lots") or order_plan.get("lots") or 0.0)
            order_type = str(order_plan.get("order_type") or order_plan.get("type") or "market").lower()
        except (ValueError, TypeError) as parse_err:
            elapsed = (clock.now() - start).total_seconds() * 1000
            logger.error(f"[PreplannedExecution] Malformed order_plan for {symbol}: {parse_err}")
            return ExecutionResult(
                symbol=symbol, analysis_id=eff_analysis_id, decision="unknown",
                sizing=None, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['malformed_order_plan'],
                risk_rejection_reasons=[f"Malformed order_plan parameters: {parse_err}"],
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=elapsed,
            )

        logger.info(f"[PreplannedExecution] Fired trigger #{trigger_id} for {symbol} → {decision.upper()} @ {target_price}")

        if decision not in ('buy', 'sell'):
            elapsed = (clock.now() - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                sizing=None, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['not_tradeable'],
                risk_rejection_reasons=[f"Decision '{decision}' is non-tradeable in preplanned order."],
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=elapsed,
            )

        # Mandatory Stop Loss Sanity Check
        if sl_price <= 0:
            elapsed = (clock.now() - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                sizing=None, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['invalid_stop_loss'],
                risk_rejection_reasons=["Stop loss must be strictly positive (> 0) for preplanned order execution."],
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=elapsed,
            )

        # 1. Live price and slippage validation
        entry_price_raw, is_stale, age_seconds = await self._get_current_price(symbol, decision)
        max_price_staleness = self.settings.get("execution", {}).get("max_price_staleness_seconds", 120)
        if is_stale and age_seconds > max_price_staleness:
            elapsed = (clock.now() - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                sizing=None, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['stale_price_data'],
                risk_rejection_reasons=[f"Price data is {age_seconds:.0f}s old (limit={max_price_staleness}s)"],
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=elapsed,
            )

        current_price = float(entry_price_raw) if entry_price_raw else target_price

        # Direction-aware stop loss validation against current execution price
        if decision == "buy" and sl_price >= current_price:
            elapsed = (clock.now() - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                sizing=None, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['invalid_stop_loss'],
                risk_rejection_reasons=[f"For BUY: stop_loss ({sl_price}) must be below current entry price ({current_price})"],
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=elapsed,
            )
        elif decision == "sell" and sl_price <= current_price:
            elapsed = (clock.now() - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                sizing=None, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['invalid_stop_loss'],
                risk_rejection_reasons=[f"For SELL: stop_loss ({sl_price}) must be above current entry price ({current_price})"],
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=elapsed,
            )

        if target_price > 0 and current_price > 0:
            # Percentage slippage check
            slippage_threshold = float(order_plan.get("max_slippage_pct") or self.settings.get("execution", {}).get("max_trigger_slippage_pct", 0.5))
            slippage_pct = (abs(current_price - target_price) / target_price) * 100.0
            if slippage_pct > slippage_threshold:
                elapsed = (clock.now() - start).total_seconds() * 1000
                logger.warning(f"[PreplannedExecution] {symbol} slippage {slippage_pct:.2f}% exceeds threshold {slippage_threshold}%")
                return ExecutionResult(
                    symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                    sizing=None, risk_approved=False,
                    risk_checks_passed=[], risk_checks_failed=['slippage_exceeded'],
                    risk_rejection_reasons=[f"Trigger slippage {slippage_pct:.2f}% > threshold {slippage_threshold}%"],
                    executed=False, mt5_ticket=None, executed_price=None,
                    executed_lots=None, mt5_error=None, position_id=None,
                    timestamp=start, elapsed_ms=elapsed,
                )

            # Pips slippage check
            max_slippage_pips = order_plan.get("max_slippage_pips") or self.settings.get("execution", {}).get("max_trigger_slippage_pips")
            if max_slippage_pips is not None:
                max_slip_pips_val = float(max_slippage_pips)
                from utils.market.instrument_identity import resolve_instrument_identity
                pip_size = resolve_instrument_identity(symbol).pip_size or 0.0001
                actual_slippage_pips = abs(current_price - target_price) / pip_size
                if actual_slippage_pips > max_slip_pips_val:
                    elapsed = (clock.now() - start).total_seconds() * 1000
                    logger.warning(f"[PreplannedExecution] {symbol} slippage {actual_slippage_pips:.1f} pips exceeds limit {max_slip_pips_val} pips")
                    return ExecutionResult(
                        symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                        sizing=None, risk_approved=False,
                        risk_checks_passed=[], risk_checks_failed=['slippage_exceeded'],
                        risk_rejection_reasons=[f"Trigger slippage {actual_slippage_pips:.1f} pips > threshold {max_slip_pips_val} pips"],
                        executed=False, mt5_ticket=None, executed_price=None,
                        executed_lots=None, mt5_error=None, position_id=None,
                        timestamp=start, elapsed_ms=elapsed,
                    )

        if not self.dry_run:
            try:
                from utils.validation.data_validator import is_spread_acceptable
                if hasattr(self, 'broker_adapter') and self.broker_adapter is not None:
                    tick = await self.broker_adapter.get_tick(symbol)
                else:
                    tick = await self.mt5.get_current_price(symbol)
                if tick and not is_spread_acceptable(symbol, tick.get('bid', 0.0), tick.get('ask', 0.0)):
                    elapsed = (clock.now() - start).total_seconds() * 1000
                    return ExecutionResult(
                        symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                        sizing=None, risk_approved=False,
                        risk_checks_passed=[], risk_checks_failed=['spread_too_high'],
                        risk_rejection_reasons=["Spread too wide at trigger execution."],
                        executed=False, mt5_ticket=None, executed_price=None,
                        executed_lots=None, mt5_error=None, position_id=None,
                        timestamp=start, elapsed_ms=elapsed,
                    )
            except Exception as spread_err:
                logger.debug(f"[PreplannedExecution] Spread check non-fatal: {spread_err}")

        # 2. Equity & Deterministic Sizing
        if account_equity is None:
            account_equity = await self._get_equity()
        if account_equity is None or account_equity <= 0:
            account_equity = float(self.settings.get('paper_trading', {}).get('initial_balance', 10000.0))

        sizing = await self.sizer.calculate_with_session(
            session=session,
            symbol=symbol,
            direction=decision,
            entry_price=current_price,
            stop_loss=sl_price,
            take_profit=tp_price,
            account_equity=account_equity
        )

        if not sizing or not sizing.is_valid:
            elapsed = (clock.now() - start).total_seconds() * 1000
            reasons = sizing.rejection_reasons if sizing else ["Position sizing calculation failed"]
            return ExecutionResult(
                symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                sizing=sizing, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['sizing_invalid'],
                risk_rejection_reasons=reasons,
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=elapsed,
            )

        if specified_lots > 0:
            # Preplanned lot size provided in order_plan, clamp to broker bounds
            spec = getattr(sizing, "_instrument_spec", None)
            try:
                max_limit = float(getattr(spec, "max_lot", 100.0))
            except (TypeError, ValueError):
                max_limit = 100.0
            try:
                min_limit = float(getattr(spec, "min_lot", 0.01))
            except (TypeError, ValueError):
                min_limit = 0.01
            sizing.recommended_lots = round(max(min_limit, min(specified_lots, max_limit)), 2)
            sizing.raw_lots = specified_lots

        # 3. Deterministic RiskGate Evaluation
        analysis_obj = None
        if eff_analysis_id:
            try:
                res_obj = await session.get(AssetAnalysis, eff_analysis_id)
                if isinstance(res_obj, AssetAnalysis):
                    analysis_obj = res_obj
            except Exception:
                analysis_obj = None

        analysis_for_gate = analysis_obj or AssetAnalysis(
            id=eff_analysis_id,
            symbol=symbol,
            decision=decision,
            stop_loss=sl_price,
            take_profit=tp_price,
            confidence=float(order_plan.get("confidence", 0.85)),
            confluence_score=int(order_plan.get("confluence_score", 8)),
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
                symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                sizing=sizing, risk_approved=False,
                risk_checks_passed=verdict.checks_passed,
                risk_checks_failed=verdict.checks_failed,
                risk_rejection_reasons=verdict.rejection_reasons,
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=elapsed,
            )
            await self._log_result(session, res, eff_analysis_id)
            return res

        # 4. Immediate execution via transactional advisory lock
        async with transactional_advisory_lock(session, lock_key=f"exec_{symbol}") as is_locked:
            if not is_locked:
                elapsed = (clock.now() - start).total_seconds() * 1000
                return ExecutionResult(
                    symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                    sizing=sizing, risk_approved=True,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=['advisory_lock_contention'],
                    risk_rejection_reasons=['Concurrent execution locked by another transaction/worker.'],
                    executed=False, mt5_ticket=None, executed_price=None,
                    executed_lots=None, mt5_error=None, position_id=None,
                    timestamp=start, elapsed_ms=elapsed,
                )

            re_check_open_count = await self._count_open_positions(session)
            max_concurrent = self.settings.get('trading', {}).get('risk', {}).get('max_concurrent_positions', 5)
            if re_check_open_count >= max_concurrent:
                elapsed = (clock.now() - start).total_seconds() * 1000
                return ExecutionResult(
                    symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                    sizing=sizing, risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=['max_concurrent_positions_reached'],
                    risk_rejection_reasons=[f"Max concurrent positions reached ({re_check_open_count}/{max_concurrent})"],
                    executed=False, mt5_ticket=None, executed_price=None,
                    executed_lots=None, mt5_error=None, position_id=None,
                    timestamp=start, elapsed_ms=elapsed,
                )

            comment = f"TRIG#{trigger_id}" if trigger_id else f"PLAN#{eff_analysis_id or 'SUB'}"
            max_spread_mult = self.settings.get("execution", {}).get("max_spread_multiplier", {}).get(symbol, 10.0)

            planned_price = target_price if (target_price > 0 and order_type in ("limit", "stop", "buy_limit", "sell_limit", "buy_stop", "sell_stop")) else (target_price if target_price > 0 else current_price)
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
                session, order, OrderStatus.PENDING_SUBMIT,
                reason="Preplanned order initialized"
            )
            await self._transition_order_state(
                session, order, OrderStatus.INTENT_COMMITTED,
                reason="Preplanned order intent committed with replay_policy=never",
                details={"trigger_id": trigger_id, "replay_policy": "never"}
            )
            await session.flush()
            await self._transition_order_state(
                session, order, OrderStatus.SUBMITTED,
                reason="Submitting preplanned order to broker adapter",
                details={"trigger_id": trigger_id, "adapter": type(self.broker_adapter).__name__}
            )
            await session.flush()

            try:
                from database.event_store import TradingEventStore
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
                    logger.warning(f"[RateThrottler] Preplanned order throttled for {symbol}: {throttle_verdict.reason}")
                    await self._transition_order_state(
                        session, order, OrderStatus.REJECTED,
                        reason=f"Order rate throttled: {throttle_verdict.reason}",
                    )
                    return ExecutionResult(
                        symbol=symbol, analysis_id=eff_analysis_id, decision=decision,
                        sizing=sizing, risk_approved=False,
                        risk_checks_passed=verdict.checks_passed,
                        risk_checks_failed=verdict.checks_failed + ['order_rate_throttled'],
                        risk_rejection_reasons=[f"Order rate throttled: {throttle_verdict.reason}. Retry after {throttle_verdict.retry_after}s"],
                        executed=False, mt5_ticket=None, executed_price=None,
                        executed_lots=None, mt5_error=f"Throttled: {throttle_verdict.reason}",
                        position_id=None, timestamp=start, elapsed_ms=elapsed,
                    )

            try:
                if hasattr(self, "effect_gate") and self.effect_gate is not None:
                    mt5_result = await self.effect_gate.admit(
                        lambda: self.broker_adapter.submit_order(
                            order=order,
                            sl=sl_price,
                            tp=tp_price,
                            comment=comment,
                            max_spread_multiplier=max_spread_mult,
                        ),
                        context_name=f"preplanned_order_{order.client_order_id}_{symbol}"
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
                if not mt5_result.get('success'):
                    try:
                        from execution.service.self_healing_executor import MT5SelfHealingExecutor
                        healer = MT5SelfHealingExecutor(
                            broker_adapter=self.broker_adapter,
                            mt5_client=getattr(self.broker_adapter, "mt5_client", None)
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
                    session, order, OrderStatus.ABORT_REQUESTED,
                    reason=f"Effect gate blocked execution: {abort_err}",
                )
                await session.flush()
                return ExecutionResult(
                    symbol=symbol, analysis_id=eff_analysis_id, decision=decision, sizing=sizing, risk_approved=False,
                    risk_checks_passed=verdict.checks_passed, risk_checks_failed=verdict.checks_failed + ['effect_gate_aborted'],
                    risk_rejection_reasons=[f"Effect gate blocked execution: {abort_err}"],
                    executed=False, mt5_ticket=None, executed_price=None, executed_lots=None, mt5_error=str(abort_err),
                    position_id=None, timestamp=start, elapsed_ms=elapsed
                )

            is_pending: bool = False
            if mt5_result.get('success'):
                status_returned = mt5_result.get('status')
                is_pending = (
                    status_returned in ('accepted', 'pending')
                    or (
                        (order.order_type or "").upper() in ("LIMIT", "STOP", "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP")
                        and float(mt5_result.get('executed_volume', 0.0)) == 0.0
                    )
                )
                exec_vol = float(mt5_result.get('executed_volume', 0.0))
                req_vol = float(order.requested_volume)

                reported_slippage = mt5_result.get('slippage_pips')
                exec_price = mt5_result.get('price')
                if reported_slippage is not None:
                    slippage = float(reported_slippage)
                elif exec_price is not None and planned_price:
                    slippage = SizingCalculator.compute_slippage_pips(float(planned_price), float(exec_price))
                else:
                    slippage = 0.0

                if is_pending:
                    await self._transition_order_state(
                        session, order, OrderStatus.ACCEPTED,
                        reason=f"Broker accepted pending order: ticket={mt5_result.get('ticket')}",
                        ticket=mt5_result.get('ticket'),
                        executed_price=exec_price,
                        slippage_pips=slippage,
                        filled_volume=0.0,
                        details={"trigger_id": trigger_id, "order_type": order.order_type, "status": "accepted"}
                    )
                elif 0.0 < exec_vol < req_vol:
                    await self._transition_order_state(
                        session, order, OrderStatus.PARTIALLY_FILLED,
                        reason=f"Partially filled {exec_vol}/{req_vol} lots at {exec_price}, ticket={mt5_result.get('ticket')}",
                        ticket=mt5_result.get('ticket'),
                        executed_price=exec_price,
                        slippage_pips=slippage,
                        filled_volume=exec_vol,
                        details={"trigger_id": trigger_id, "order_type": order.order_type, "status": "partially_filled", "filled_volume": exec_vol}
                    )
                else:
                    await self._transition_order_state(
                        session, order, OrderStatus.FILLED,
                        reason=f"Filled at {exec_price}, ticket={mt5_result.get('ticket')}",
                        ticket=mt5_result.get('ticket'),
                        executed_price=exec_price,
                        slippage_pips=slippage,
                        filled_volume=exec_vol if exec_vol > 0 else req_vol,
                        details={"trigger_id": trigger_id, "order_type": order.order_type, "status": "filled"}
                    )
            else:
                await self._transition_order_state(
                    session, order, OrderStatus.REJECTED,
                    reason=mt5_result.get('error') or "Broker order rejected",
                )

            elapsed = (clock.now() - start).total_seconds() * 1000
            position_id = None
            if mt5_result.get('success'):
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
                            mt5_ticket=mt5_result.get('ticket'),
                            symbol=symbol,
                            direction=decision,
                            volume=sizing.recommended_lots,
                            entry_price=mt5_result.get('price') or current_price,
                            sl=sl_price,
                            tp=tp_price,
                            opened_at=datetime.now(timezone.utc),
                            status='open',
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


    async def execute_paired_analyses(
        self,
        session: AsyncSession,
        primary: AssetAnalysis,
        hedge: AssetAnalysis,
        pair_group_id: str,
        account_equity: Optional[float] = None,
    ) -> dict:
        """Execute a paired stat-arb trade. Both legs must fill or neither does."""
        logger.info(f"Paired execution: {primary.symbol} {primary.decision} + "
                    f"{hedge.symbol} {hedge.decision} [group={pair_group_id[:8]}]")

        # Phase 1: Size with notional-weighted lots for proper spread hedge
        # Step 1: Size primary leg at full risk (the "anchor" leg)
        fallback_equity = float(self.settings.get('paper_trading', {}).get('initial_balance', 10000.0))
        equity = account_equity if account_equity is not None else (await self._get_equity() or fallback_equity)
        spread_risk = (self.settings.get('trading', {}).get('risk', {})
                       .get('risk_percent_per_trade', 1.0))
        pair_lock_key = f"pair_{primary.symbol}_{hedge.symbol}"
        async with transactional_advisory_lock(session, lock_key=pair_lock_key) as is_locked:
            if not is_locked:
                return {"success": False, "reason": "Concurrent execution locked by another process/worker."}

            # Parse and validate primary entry zone price
            try:
                if isinstance(primary.entry_zone, dict):
                    p_ez = primary.entry_zone
                else:
                    p_ez = json.loads(primary.entry_zone) if primary.entry_zone else {}
                p_price = float(p_ez.get('price', 0))
                if p_price <= 0:
                    raise ValueError(f"Invalid primary entry price: {p_price}")
            except Exception as e:
                logger.warning(f"Failed to parse primary entry_zone: {e}")
                return {"success": False, "reason": f"Invalid primary entry_zone: {e}"}

            p_sl = float(primary.stop_loss) if primary.stop_loss is not None else 0.0
            p_tp = float(primary.take_profit) if primary.take_profit is not None else None

            sizing_primary = await self.sizer.calculate_with_session(
                session, primary.symbol, primary.decision,
                p_price, p_sl, p_tp,
                equity, risk_percent_override=spread_risk,
            )

            if not sizing_primary.is_valid:
                return {"success": False, "reason": f"Primary sizing failed: {sizing_primary.rejection_reasons}"}

            # Step 2: Calculate notional-weighted hedge lots
            # Goal: equal USD notional on both legs for market-neutral spread
            primary_info = await self.mt5.get_symbol_info(primary.symbol)
            hedge_info = await self.mt5.get_symbol_info(hedge.symbol)

            if not primary_info or not hedge_info:
                return {"success": False, "reason": "Symbol info unavailable for notional weighting"}

            primary_contract = primary_info.get('contract_size') or primary_info.get('trade_contract_size', 100)
            hedge_contract = hedge_info.get('contract_size') or hedge_info.get('trade_contract_size', 100)
            primary_notional = p_price * primary_contract
            
            try:
                if isinstance(hedge.entry_zone, dict):
                    h_ez = hedge.entry_zone
                else:
                    h_ez = json.loads(hedge.entry_zone) if hedge.entry_zone else {}
                h_price = float(h_ez.get('price', 0))
                if h_price <= 0:
                    raise ValueError(f"Invalid hedge entry price: {h_price}")
            except Exception as e:
                logger.warning(f"Failed to parse hedge entry_zone: {e}")
                return {"success": False, "reason": f"Invalid hedge entry_zone: {e}"}

            hedge_notional = h_price * hedge_contract

            if hedge_notional <= 0:
                return {"success": False, "reason": "Hedge notional is zero"}

            raw_hedge_lots = sizing_primary.recommended_lots * (primary_notional / hedge_notional)

            # Round to lot_step and clamp to [volume_min, volume_max]
            lot_step = max(float(hedge_info.get('volume_step') or 0.01), 0.001)
            vol_min = max(float(hedge_info.get('volume_min') or 0.01), 0.001)
            vol_max = max(float(hedge_info.get('volume_max') or 100.0), vol_min)
            hedge_lots = max(vol_min, min(vol_max,
                             round(round(raw_hedge_lots / lot_step) * lot_step, 2)))

            h_sl = float(hedge.stop_loss) if hedge.stop_loss is not None else 0.0
            h_tp = float(hedge.take_profit) if hedge.take_profit is not None else None

            # Build a SizingResult for the hedge leg
            sizing_hedge = await self.sizer.calculate_with_session(
                session, hedge.symbol, hedge.decision,
                h_price, h_sl, h_tp,
                equity, risk_percent_override=spread_risk,
            )
            
            if not sizing_hedge.is_valid:
                return {"success": False, "reason": f"Hedge sizing failed: {sizing_hedge.rejection_reasons}"}

            # Apply notional-weighted lots to hedge sizing
            sizing_hedge.recommended_lots = hedge_lots

            # Validate both legs through RiskGate (C-1)
            verdict_primary = await self.gate.check(
                session=session,
                symbol=primary.symbol,
                direction=primary.decision,
                sizing=sizing_primary,
                account_equity=equity,
                analysis=primary,
                pair_group_id=pair_group_id,
            )
            if not verdict_primary.approved:
                return {"success": False, "reason": f"Primary leg risk gate rejected: {verdict_primary.rejection_reasons}"}

            verdict_hedge = await self.gate.check(
                session=session,
                symbol=hedge.symbol,
                direction=hedge.decision,
                sizing=sizing_hedge,
                account_equity=equity,
                analysis=hedge,
                pair_group_id=pair_group_id,
            )
            if not verdict_hedge.approved:
                return {"success": False, "reason": f"Hedge leg risk gate rejected: {verdict_hedge.rejection_reasons}"}

            logger.info(f"Notional weighting: {primary.symbol}={sizing_primary.recommended_lots} lots "
                        f"({primary_contract} contract), {hedge.symbol}={hedge_lots} lots "
                        f"({hedge_contract} contract), ratio={primary_notional/hedge_notional:.3f}")

            # Check max_concurrent_positions (pair counts as 2)
            open_count = await self._count_open_positions(session)
            max_pos = self.settings.get('trading', {}).get('risk', {}).get('max_concurrent_positions', 5)
            if open_count + 2 > max_pos:
                return {"success": False, "reason": f"Max positions ({max_pos}) would be exceeded: {open_count}+2"}

            # Execute primary leg
            adapter = getattr(self, "broker_adapter", None)
            effect_gate = getattr(self, "effect_gate", None)

            order_primary = OrderCreator.create_order(
                symbol=primary.symbol,
                order_type="market",
                direction=primary.decision,
                requested_price=p_price,
                requested_volume=sizing_primary.recommended_lots,
                analysis_id=primary.id,
            )
            order_primary.replay_policy = "never"
            session.add(order_primary)
            await self._transition_order_state(
                session, order_primary, OrderStatus.PENDING_SUBMIT,
                reason="Paired LEG1 order initialized"
            )
            await self._transition_order_state(
                session, order_primary, OrderStatus.INTENT_COMMITTED,
                reason="Paired LEG1 order intent committed",
                details={"pair_group_id": pair_group_id, "leg": 1}
            )
            await session.flush()
            await self._transition_order_state(
                session, order_primary, OrderStatus.SUBMITTED,
                reason="Submitting paired LEG1 order to broker adapter",
                details={"pair_group_id": pair_group_id, "leg": 1}
            )
            await session.flush()

            if hasattr(self, "rate_throttler") and self.rate_throttler:
                await self.rate_throttler.wait_and_acquire()

            try:
                if adapter is not None:
                    if effect_gate is not None:
                        result_primary = await effect_gate.admit(
                            lambda: adapter.submit_order(
                                order=order_primary,
                                sl=primary.stop_loss,
                                tp=primary.take_profit,
                                comment=f"PAIR:{pair_group_id[:8]}:LEG1",
                            ),
                            context_name=f"pair_l1_{order_primary.client_order_id}_{primary.symbol}"
                        )
                    else:
                        result_primary = await adapter.submit_order(
                            order=order_primary,
                            sl=primary.stop_loss,
                            tp=primary.take_profit,
                            comment=f"PAIR:{pair_group_id[:8]}:LEG1",
                        )
                else:
                    if self.dry_run:
                        import random
                        import hashlib
                        collision_seed_p = f"{primary.symbol}_{datetime.now(timezone.utc).isoformat()}_{random.randint(10000, 99999)}_LEG1"
                        dry_ticket_p = int(hashlib.md5(collision_seed_p.encode()).hexdigest(), 16) % 9000000 + 1000000
                        logger.info(f'DRY RUN: Would execute paired LEG1 {primary.decision.upper()} {sizing_primary.recommended_lots} lots for {primary.symbol} (mock ticket: {dry_ticket_p})')
                        result_primary = {'success': True, 'ticket': dry_ticket_p, 'price': p_price, 'error': None}
                    else:
                        result_primary = await self.mt5.place_order(
                            primary.symbol, primary.decision, sizing_primary.recommended_lots,
                            None, primary.stop_loss, primary.take_profit,
                            comment=f"PAIR:{pair_group_id[:8]}:LEG1",
                        )
            except AbortRequested as abort_err:
                logger.warning(f"[EffectGate] Paired LEG1 blocked for {primary.symbol}: {abort_err}")
                await self._transition_order_state(
                    session, order_primary, OrderStatus.ABORT_REQUESTED,
                    reason=f"Effect gate blocked execution: {abort_err}",
                )
                result_primary = {'success': False, 'error': str(abort_err)}

            if not result_primary.get('success'):
                await self._transition_order_state(
                    session, order_primary, OrderStatus.REJECTED,
                    reason=f"Primary leg failed: {result_primary.get('error')}",
                )
                primary.execution_status = 'failed'
                primary.execution_notes = f"Primary leg failed: {result_primary.get('error')}"
                await session.commit()
                return {"success": False, "reason": primary.execution_notes}
            else:
                await self._transition_order_state(
                    session, order_primary, OrderStatus.FILLED,
                    reason="Primary leg filled successfully",
                    ticket=result_primary.get('ticket'),
                    executed_price=result_primary.get('price'),
                    filled_volume=sizing_primary.recommended_lots,
                )

            # Execute hedge leg
            order_hedge = OrderCreator.create_order(
                symbol=hedge.symbol,
                order_type="market",
                direction=hedge.decision,
                requested_price=h_price,
                requested_volume=sizing_hedge.recommended_lots,
                analysis_id=hedge.id,
            )
            order_hedge.replay_policy = "never"
            session.add(order_hedge)
            await self._transition_order_state(
                session, order_hedge, OrderStatus.PENDING_SUBMIT,
                reason="Paired LEG2 order initialized"
            )
            await self._transition_order_state(
                session, order_hedge, OrderStatus.INTENT_COMMITTED,
                reason="Paired LEG2 order intent committed",
                details={"pair_group_id": pair_group_id, "leg": 2}
            )
            await session.flush()
            await self._transition_order_state(
                session, order_hedge, OrderStatus.SUBMITTED,
                reason="Submitting paired LEG2 order to broker adapter",
                details={"pair_group_id": pair_group_id, "leg": 2}
            )
            await session.flush()

            if hasattr(self, "rate_throttler") and self.rate_throttler:
                await self.rate_throttler.wait_and_acquire()

            try:
                if adapter is not None:
                    if effect_gate is not None:
                        result_hedge = await effect_gate.admit(
                            lambda: adapter.submit_order(
                                order=order_hedge,
                                sl=hedge.stop_loss,
                                tp=hedge.take_profit,
                                comment=f"PAIR:{pair_group_id[:8]}:LEG2",
                            ),
                            context_name=f"pair_l2_{order_hedge.client_order_id}_{hedge.symbol}"
                        )
                    else:
                        result_hedge = await adapter.submit_order(
                            order=order_hedge,
                            sl=hedge.stop_loss,
                            tp=hedge.take_profit,
                            comment=f"PAIR:{pair_group_id[:8]}:LEG2",
                        )
                else:
                    if self.dry_run:
                        import random
                        import hashlib
                        collision_seed_h = f"{hedge.symbol}_{datetime.now(timezone.utc).isoformat()}_{random.randint(10000, 99999)}_LEG2"
                        dry_ticket_h = int(hashlib.md5(collision_seed_h.encode()).hexdigest(), 16) % 9000000 + 1000000
                        logger.info(f'DRY RUN: Would execute paired LEG2 {hedge.decision.upper()} {sizing_hedge.recommended_lots} lots for {hedge.symbol} (mock ticket: {dry_ticket_h})')
                        result_hedge = {'success': True, 'ticket': dry_ticket_h, 'price': h_price, 'error': None}
                    else:
                        result_hedge = await self.mt5.place_order(
                            hedge.symbol, hedge.decision, sizing_hedge.recommended_lots,
                            None, hedge.stop_loss, hedge.take_profit,
                            comment=f"PAIR:{pair_group_id[:8]}:LEG2",
                        )
            except AbortRequested as abort_err:
                logger.warning(f"[EffectGate] Paired LEG2 blocked for {hedge.symbol}: {abort_err}")
                await self._transition_order_state(
                    session, order_hedge, OrderStatus.ABORT_REQUESTED,
                    reason=f"Effect gate blocked execution: {abort_err}",
                )
                result_hedge = {'success': False, 'error': str(abort_err)}

            if not result_hedge.get('success'):
                await self._transition_order_state(
                    session, order_hedge, OrderStatus.REJECTED,
                    reason=f"Hedge leg failed: {result_hedge.get('error')}",
                )
                # CRITICAL: Rollback primary leg immediately (C-2)
                logger.error(f"Hedge leg failed! Rolling back primary: "
                            f"ticket={result_primary.get('ticket')}")
                if adapter is not None:
                    close_result = await adapter.close_position(result_primary['ticket'])
                elif self.dry_run:
                    close_result = {'success': True, 'error': None}
                else:
                    close_result = await self.mt5.close_position(result_primary['ticket'])
                if not close_result or not close_result.get('success'):
                    err_msg = close_result.get('error') if close_result else 'No response from MT5'
                    logger.critical(f"EMERGENCY: Could not close orphan primary leg {primary.symbol} ticket={result_primary['ticket']}! Error: {err_msg}")
                    try:
                        await AgentNotifier().send_critical(f"🚨 ORPHAN TRADE EMERGENCY: {primary.symbol} ticket={result_primary['ticket']} close failed ({err_msg})!")
                    except Exception as notif_err:
                        logger.error(f"Failed to send orphan trade emergency alert: {notif_err}")
                    primary.execution_status = 'orphan_emergency'
                    primary.execution_notes = f"Hedge failed ({result_hedge.get('error')}). Primary rollback FAILED: {err_msg}"
                    
                    # Persist to Position table so PositionGuardian can retry closing once MT5 reconnects
                    try:
                        await self._save_position(
                            session=session,
                            analysis=primary,
                            sizing=sizing_primary,
                            mt5_result=result_primary,
                            pair_group_id=pair_group_id,
                            auto_commit=False,
                        )
                        primary_pos = (await session.execute(
                            select(Position).where(Position.mt5_ticket == result_primary['ticket'])
                        )).scalar_one_or_none()
                        if primary_pos:
                            primary_pos.status = 'orphan_pending_close'
                    except Exception as save_orphan_err:
                        logger.error(f"Failed to persist orphan record: {save_orphan_err}")
                else:
                    primary.execution_status = 'rolled_back'
                    primary.execution_notes = (
                        f"Hedge leg failed ({result_hedge.get('error')}). "
                        f"Primary rolled back successfully."
                    )
                hedge.execution_status = 'failed'
                hedge.execution_notes = f"Hedge failed: {result_hedge.get('error')}"
                await session.commit()
                return {"success": False, "reason": "Hedge leg failed, rollback processed"}
            else:
                await self._transition_order_state(
                    session, order_hedge, OrderStatus.FILLED,
                    reason="Hedge leg filled successfully",
                    ticket=result_hedge.get('ticket'),
                    executed_price=result_hedge.get('price'),
                    filled_volume=sizing_hedge.recommended_lots,
                )

            # Mark executed analysis IDs in dedup cache
            _EXECUTED_ANALYSIS_IDS[primary.id] = time.time()
            _EXECUTED_ANALYSIS_IDS[hedge.id] = time.time()

            # Phase 3: Save both positions with pair_group_id inside lock to prevent race conditions
            try:
                await self._save_position(session, primary, sizing_primary,
                                           result_primary, pair_group_id=pair_group_id, auto_commit=False)
                await self._save_position(session, hedge, sizing_hedge,
                                           result_hedge, pair_group_id=pair_group_id, auto_commit=False)
                await session.commit()
            except Exception as db_err:
                logger.critical(f"DB save failed after paired MT5 orders {result_primary.get('ticket')}/{result_hedge.get('ticket')}: {db_err}. CLOSING orphan paired positions.")
                if not self.dry_run:
                    for t in (result_primary.get('ticket'), result_hedge.get('ticket')):
                        if t:
                            try:
                                await self.mt5.close_position(t)
                            except Exception as close_err:
                                await AgentNotifier().send_critical(f"ORPHAN PAIRED TRADE: ticket={t}. DB commit and close both failed: {close_err}")
                raise

        logger.info(f"✅ Paired trade executed: {primary.symbol}+{hedge.symbol} "
                   f"[group={pair_group_id[:8]}]")
        return {"success": True, "tickets": [result_primary['ticket'], result_hedge['ticket']]}


    async def execute_tranche_order(
        self,
        session: AsyncSession,
        analysis: AssetAnalysis,
        tranche_ratios: Tuple[float, float] = (0.5, 0.5),
        account_equity: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Execute an AssetAnalysis as a multi-leg tranche order (SOTA scale-out):
        - Leg 1: e.g. 50% lot targeting TP1 (partial scale-out profit locking).
        - Leg 2: e.g. 50% lot runner targeting TP2 or trailing ATR stop.
        Both positions are tagged with pair_group_id 'tranche_<uuid>' so
        PositionGuardian automatically moves Leg 2 SL to Breakeven when Leg 1 hits TP.
        """
        start = clock.now()
        symbol = analysis.symbol
        decision = (analysis.decision or "").lower()

        if decision not in ('buy', 'sell'):
            return {"success": False, "reason": f"Decision '{decision}' is not tradeable"}

        # Calculate sizing
        entry_price = float(getattr(analysis, 'current_price', None) or analysis.entry_price or getattr(analysis, 'price_at_analysis', None) or 0.0)
        sl_price = float(analysis.stop_loss or 0.0)
        tp_price = float(analysis.take_profit or 0.0)

        if account_equity is None and self.dry_run:
            account_equity = float(self.settings.get('paper_trading', {}).get('initial_balance', 10000.0))

        sizing = await self.sizer.calculate_with_session(
            session=session,
            symbol=symbol,
            direction=decision,
            entry_price=entry_price,
            stop_loss=sl_price,
            take_profit=tp_price,
            account_equity=account_equity,
        )

        if not sizing or not sizing.is_valid:
            reasons = sizing.rejection_reasons if sizing else ["Position sizing calculation failed"]
            return {"success": False, "reason": f"Sizing rejected: {reasons}"}

        total_lots = float(sizing.recommended_lots)
        ratio_1, ratio_2 = tranche_ratios
        spec = get_instrument_spec(symbol, getattr(self, "mt5_client", None))
        lot_step = float(getattr(spec, "lot_step", 0.01) or 0.01)
        min_lot = float(getattr(spec, "min_lot", 0.01) or 0.01)

        lots_1 = PositionSizer._round_lots(total_lots * ratio_1, lot_step)
        lots_2 = PositionSizer._round_lots(total_lots - lots_1, lot_step)

        # Ensure minimum lot per tranche
        if lots_1 < min_lot or lots_2 < min_lot:
            logger.info(f"Total lots {total_lots} too small for tranche split ({lots_1}/{lots_2}) with min_lot {min_lot}. Falling back to single order.")
            single_res = await self._execute_analysis_internal(session, analysis, account_equity)
            return {"success": single_res.executed, "single_execution": True, "result": single_res}

        group_id = uuid.uuid4().hex[:12]
        tranche_group_id = f"tranche_{group_id}"

        # Check RiskGate (with tranche pair_group_id for multi-leg duplicate bypass)
        verdict = await self.gate.check(
            session=session,
            symbol=symbol,
            direction=decision,
            sizing=sizing,
            account_equity=account_equity,
            analysis=analysis,
            pair_group_id=tranche_group_id,
        )
        if not verdict.approved:
            return {"success": False, "reason": f"Risk gate rejected: {verdict.rejection_reasons}"}

        # Calculate Leg 2 TP (TP2 runner target: 1.5x R or custom tp_2)
        tp_2 = getattr(analysis, 'take_profit_2', None)
        if not tp_2:
            r_dist = abs(tp_price - entry_price)
            if decision == 'buy':
                tp_2 = round(entry_price + (r_dist * 1.5), 5)
            else:
                tp_2 = round(entry_price - (r_dist * 1.5), 5)

        max_spread_mult = self.settings.get("execution", {}).get("max_spread_multiplier", {}).get(symbol, 10.0)

        async def _submit_tranche_leg(leg_num: int, lots: float, tp: Optional[float], comment_tag: str) -> Tuple[Optional[Order], dict]:
            order = OrderCreator.create_order(
                symbol=symbol,
                order_type="MARKET",
                direction=decision,
                requested_price=float(entry_price),
                requested_volume=float(lots),
                analysis_id=analysis.id,
            )
            order.replay_policy = "never"
            session.add(order)
            await self._transition_order_state(
                session, order, OrderStatus.PENDING_SUBMIT,
                reason=f"Tranche leg {leg_num} initialized"
            )
            await self._transition_order_state(
                session, order, OrderStatus.INTENT_COMMITTED,
                reason=f"Order intent committed for tranche leg {leg_num}",
                details={"analysis_id": analysis.id, "group_id": tranche_group_id}
            )
            await session.flush()
            await self._transition_order_state(
                session, order, OrderStatus.SUBMITTED,
                reason=f"Submitting tranche leg {leg_num} to broker adapter",
                details={"analysis_id": analysis.id, "group_id": tranche_group_id}
            )
            await session.flush()

            if hasattr(self, "rate_throttler") and self.rate_throttler:
                await self.rate_throttler.wait_and_acquire()

            adapter = getattr(self, "broker_adapter", None)
            effect_gate = getattr(self, "effect_gate", None)

            try:
                if adapter is not None:
                    if effect_gate is not None:
                        res = await effect_gate.admit(
                            lambda: adapter.submit_order(
                                order=order,
                                sl=sl_price,
                                tp=tp,
                                comment=f"TRANCHE:{group_id[:6]}:{comment_tag}",
                                max_spread_multiplier=max_spread_mult,
                            ),
                            context_name=f"tranche_l{leg_num}_{order.client_order_id}_{symbol}"
                        )
                    else:
                        res = await adapter.submit_order(
                            order=order,
                            sl=sl_price,
                            tp=tp,
                            comment=f"TRANCHE:{group_id[:6]}:{comment_tag}",
                            max_spread_multiplier=max_spread_mult,
                        )
                else:
                    if self.dry_run:
                        import random, hashlib
                        t = int(hashlib.md5(f"{symbol}_{start.isoformat()}_{random.randint(10000, 99999)}_{comment_tag}".encode()).hexdigest(), 16) % 9000000 + 1000000
                        res = {'success': True, 'ticket': t, 'price': entry_price, 'error': None}
                    else:
                        res = await self.mt5.place_order(
                            symbol, decision, lots, None, sl_price, tp,
                            comment=f"TRANCHE:{group_id[:6]}:{comment_tag}",
                        )
            except Exception as submit_err:
                logger.error(f"Tranche leg {leg_num} submission failed: {submit_err}")
                res = {'success': False, 'error': str(submit_err)}

            if inspect.isawaitable(res):
                res = await res

            if res.get('success'):
                await self._transition_order_state(
                    session, order, OrderStatus.FILLED,
                    reason=f"Tranche leg {leg_num} filled",
                    ticket=res.get('ticket'),
                    executed_price=res.get('price') or entry_price,
                    filled_volume=lots,
                )
            else:
                await self._transition_order_state(
                    session, order, OrderStatus.REJECTED,
                    reason=f"Tranche leg {leg_num} failed: {res.get('error')}"
                )
            return order, res

        # Place Leg 1
        order_leg1, res_leg1 = await _submit_tranche_leg(1, lots_1, tp_price, "L1")
        if not res_leg1.get('success'):
            await session.commit()
            return {"success": False, "reason": f"Leg 1 order failed: {res_leg1.get('error')}"}

        # Place Leg 2
        order_leg2, res_leg2 = await _submit_tranche_leg(2, lots_2, tp_2, "L2")
        if not res_leg2.get('success'):
            logger.error(f"Leg 2 order failed ({res_leg2.get('error')}). Rolling back Leg 1 ticket {res_leg1.get('ticket')}")

            rollback_ok = False
            close_err = None
            if self.dry_run:
                rollback_ok = True
            elif res_leg1.get('ticket'):
                try:
                    adapter = getattr(self, "broker_adapter", None)
                    if adapter and hasattr(adapter, "close_position"):
                        close_res = await adapter.close_position(res_leg1['ticket'])
                    elif self.mt5:
                        close_res = await self.mt5.close_position(res_leg1['ticket'])
                    else:
                        close_res = {'success': False, 'error': 'No broker adapter or MT5 client available'}
                    rollback_ok = bool(close_res and close_res.get('success'))
                    if not rollback_ok:
                        close_err = close_res.get('error') if close_res else "Close position failed"
                except Exception as ex:
                    close_err = str(ex)
                    rollback_ok = False

            if not rollback_ok:
                err_msg = close_err or "Unknown error closing Leg 1"
                logger.critical(f"EMERGENCY: Could not close orphan Leg 1 {symbol} ticket={res_leg1.get('ticket')}! Error: {err_msg}")
                try:
                    await AgentNotifier().send_critical(f"🚨 ORPHAN TRANCHE EMERGENCY: {symbol} ticket={res_leg1.get('ticket')} rollback failed ({err_msg})!")
                except Exception as notif_err:
                    logger.error(f"Failed to send orphan alert: {notif_err}")

                analysis.execution_status = 'orphan_emergency'
                analysis.execution_notes = f"Leg 2 failed ({res_leg2.get('error')}). Leg 1 rollback FAILED: {err_msg}"

                from copy import copy
                sizing_1 = copy(sizing)
                sizing_1.recommended_lots = lots_1
                try:
                    await self._save_position(
                        session=session,
                        analysis=analysis,
                        sizing=sizing_1,
                        mt5_result=res_leg1,
                        pair_group_id=tranche_group_id,
                        auto_commit=False,
                        order_id=order_leg1.id if order_leg1 else None,
                    )
                    pos = (await session.execute(
                        select(Position).where(Position.mt5_ticket == res_leg1['ticket'])
                    )).scalar_one_or_none()
                    if pos:
                        pos.status = 'orphan_pending_close'
                    await session.commit()
                except Exception as save_orphan_err:
                    logger.error(f"Failed to persist orphan record: {save_orphan_err}")

                return {"success": False, "reason": f"Leg 2 order failed and Leg 1 rollback failed: {err_msg}"}
            else:
                analysis.execution_status = 'rolled_back'
                analysis.execution_notes = f"Leg 2 order failed ({res_leg2.get('error')}). Leg 1 rolled back successfully."
                await session.commit()
                return {"success": False, "reason": f"Leg 2 order failed: {res_leg2.get('error')}"}

        # Save both positions to DB with pair_group_id safely wrapped
        try:
            from copy import copy
            sizing_1 = copy(sizing)
            sizing_1.recommended_lots = lots_1
            sizing_2 = copy(sizing)
            sizing_2.recommended_lots = lots_2

            await self._save_position(
                session=session,
                analysis=analysis,
                sizing=sizing_1,
                mt5_result=res_leg1,
                pair_group_id=tranche_group_id,
                auto_commit=False,
                order_id=order_leg1.id if order_leg1 else None,
            )

            analysis_leg2 = copy(analysis)
            analysis_leg2.take_profit = tp_2

            await self._save_position(
                session=session,
                analysis=analysis_leg2,
                sizing=sizing_2,
                mt5_result=res_leg2,
                pair_group_id=tranche_group_id,
                auto_commit=False,
                order_id=order_leg2.id if order_leg2 else None,
            )

            await session.commit()
        except Exception as db_save_err:
            logger.critical(f"Failed to persist tranche positions to DB: {db_save_err}", exc_info=True)
            await session.rollback()
            return {"success": False, "reason": f"Database save failed: {db_save_err}"}

        _EXECUTED_ANALYSIS_IDS[analysis.id] = time.time()

        logger.info(
            f"✅ Multi-leg Tranche executed: {symbol} {decision.upper()} "
            f"L1={lots_1}L @ TP {tp_price}, L2={lots_2}L @ TP {tp_2} "
            f"[group={tranche_group_id}]"
        )

        return {
            "success": True,
            "tranche_group_id": tranche_group_id,
            "tickets": [res_leg1.get('ticket'), res_leg2.get('ticket')],
            "lots": [lots_1, lots_2],
            "tps": [tp_price, tp_2],
        }


    async def _execute_analysis_internal(
        self,
        session: AsyncSession,
        analysis: AssetAnalysis,
        account_equity: Optional[float] = None,
        is_post_release: bool = False,
        **kwargs
    ) -> ExecutionResult:
        start = clock.now()
        symbol = analysis.symbol
        decision = analysis.decision

        logger.info(f"ExecutionService: processing {symbol} → {decision.upper()}")
        
        # Abaikan keputusan non-tradeable (avoid/wait)
        if decision not in ('buy', 'sell'):
            logger.info(f"Decision '{decision}' for {symbol} — no execution needed")
            return ExecutionResult(
                symbol=symbol, analysis_id=analysis.id, decision=decision,
                sizing=None, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['not_tradeable'],
                risk_rejection_reasons=[f"Decision is '{decision}' — no order placed"],
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=0,
            )

        # Check live execution requirements (Phase 0)
        if not self.dry_run:
            min_paper_trades = self.settings.get('trading', {}).get(
                'min_paper_trades_before_live',
                self.settings.get('execution', {}).get('min_paper_trades_before_live', 50)
            )
            # FIX 4.10: allow explicit force_live_override
            if self.settings.get('trading', {}).get('force_live_override', False) or \
               self.settings.get('execution', {}).get('force_live_override', False):
                min_paper_trades = 0
            from database.models import PaperTradeRecord
            try:
                # Use the existing session passed to the function
                raw_count = (await session.execute(select(func.count(PaperTradeRecord.id)))).scalar()
                try:
                    paper_trades_count = int(raw_count) if raw_count is not None else 0
                except (TypeError, ValueError):
                    paper_trades_count = 0
                if paper_trades_count < min_paper_trades:
                    logger.warning(
                        f"Execution REJECTED for {symbol}: Cannot execute live. "
                        f"Paper trades count ({paper_trades_count}) < min_paper_trades_before_live ({min_paper_trades})."
                    )
                    return ExecutionResult(
                        symbol=symbol, analysis_id=analysis.id, decision=decision,
                        sizing=None, risk_approved=False,
                        risk_checks_passed=[], risk_checks_failed=['insufficient_paper_trades'],
                        risk_rejection_reasons=[
                            f"Cannot execute live: Need {min_paper_trades} paper trades, currently have {paper_trades_count}."
                        ],
                        executed=False, mt5_ticket=None, executed_price=None,
                        executed_lots=None, mt5_error=None, position_id=None,
                        timestamp=start, elapsed_ms=0,
                    )
            except Exception as pt_err:
                logger.error(f"Failed to check paper trades count: {pt_err}")
        # Cek umur analisis — tolak jika sudah terlalu lama (basi)
        max_execute_age_minutes = self.settings.get('execution', {}).get(
            'max_analysis_age_for_execute_minutes', 
            20  # 20 menit default — conservative
        )
        if analysis.generated_at:
            gen_at = analysis.generated_at
            if gen_at.tzinfo is None:
                gen_at = gen_at.replace(tzinfo=timezone.utc)
            # Re-check dengan waktu sekarang (setelah lock diperoleh)
            current_age_minutes = (start - gen_at).total_seconds() / 60.0
            
            if current_age_minutes > max_execute_age_minutes:
                logger.warning(
                    f'Execution REJECTED post-lock for {symbol}: analysis is '
                    f'{current_age_minutes:.1f}m old (limit={max_execute_age_minutes}m). '
                    f'Analysis became stale while waiting for execution lock.'
                )
                return ExecutionResult(
                    symbol=symbol, analysis_id=analysis.id, decision=decision,
                    sizing=None, risk_approved=False,
                    risk_checks_passed=[], risk_checks_failed=['analysis_stale_post_lock'],
                    risk_rejection_reasons=[
                        f'Analysis became stale ({current_age_minutes:.1f}m) while waiting '
                        f'for execution lock (limit={max_execute_age_minutes}m).'
                    ],
                    executed=False, mt5_ticket=None, executed_price=None,
                    executed_lots=None, mt5_error=None, position_id=None,
                    timestamp=start, elapsed_ms=0,
                )

        # Check fundamental brief age — don't execute on outdated macro thesis
        if analysis.brief_id:
            try:
                from database.models import FundamentalBrief
                from sqlalchemy import select as _sel
                async with get_session() as brief_session:
                    brief = await brief_session.get(FundamentalBrief, analysis.brief_id)
                    if brief and brief.generated_at:
                        gen_at = brief.generated_at
                        if gen_at.tzinfo is None:
                            gen_at = gen_at.replace(tzinfo=timezone.utc)
                        brief_age_hours = (start - gen_at).total_seconds() / 3600
                        max_brief_age = self.settings.get("data_quality", {}).get(
                            "max_brief_age_execution_hours", 12.0
                        )
                        if brief_age_hours > max_brief_age:
                            logger.warning(
                                f"Execution REJECTED for {symbol}: fundamental brief is "
                                f"{brief_age_hours:.1f}h old (limit={max_brief_age}h). "
                                f"Macro thesis may be outdated. Re-run analysis cycle first."
                            )
                            return ExecutionResult(
                                symbol=symbol, analysis_id=analysis.id, decision=decision,
                                sizing=None, risk_approved=False,
                                risk_checks_passed=[], risk_checks_failed=['stale_fundamental_brief'],
                                risk_rejection_reasons=[
                                    f"Fundamental brief is {brief_age_hours:.1f}h old "
                                    f"(limit={max_brief_age}h). Run /run to refresh."
                                ],
                                executed=False, mt5_ticket=None, executed_price=None,
                                executed_lots=None, mt5_error=None, position_id=None,
                                timestamp=start, elapsed_ms=0,
                            )
                            
                        # Check jika ada high-impact event terjadi setelah brief dibuat
                        from database.models import EconomicCalendar
                        from utils.market.currency_utils import get_symbol_currencies
                        sym_currencies = get_symbol_currencies(symbol)
                        brief_created = brief.generated_at.replace(tzinfo=timezone.utc) if brief.generated_at.tzinfo is None else brief.generated_at
                        # Only block if the high-impact event occurred very recently (within 30 mins) post-brief
                        recent_threshold = max(brief_created, start - timedelta(minutes=30))
                        post_brief_events = (await brief_session.execute(
                            _sel(EconomicCalendar)
                            .where(EconomicCalendar.event_time > recent_threshold)
                            .where(EconomicCalendar.event_time <= start)
                            .where(EconomicCalendar.impact.in_(['high', 'High', 'HIGH']))
                            .where(EconomicCalendar.currency.in_(list(sym_currencies)))
                            .limit(1)
                        )).scalar_one_or_none()
                        
                        if post_brief_events:
                            logger.warning(
                                f'Execution BLOCKED for {symbol}: Recent high-impact event "{post_brief_events.event_name}" '
                                f'occurred at {post_brief_events.event_time} (within 30m of execution). Brief may be stale for current conditions.'
                            )
                            return ExecutionResult(
                                symbol=symbol, analysis_id=analysis.id, decision=decision,
                                sizing=None, risk_approved=False,
                                risk_checks_passed=[], risk_checks_failed=['stale_fundamental_brief_post_event'],
                                risk_rejection_reasons=[
                                    f'Post-brief high-impact event detected: {post_brief_events.event_name} '
                                    f'at {post_brief_events.event_time}. Re-run analysis cycle first.'
                                ],
                                executed=False, mt5_ticket=None, executed_price=None,
                                executed_lots=None, mt5_error=None, position_id=None,
                                timestamp=start, elapsed_ms=0,
                            )

                        try:
                            from utils.protocol.brief_contamination_guard import BriefContaminationGuard
                            is_stale_mag, stale_reason = await BriefContaminationGuard.check_magnitude_based_staleness(
                                brief_session, symbol, gen_at, self.settings
                            )
                            if is_stale_mag:
                                logger.warning(f"Execution BLOCKED for {symbol}: {stale_reason}")
                                return ExecutionResult(
                                    symbol=symbol, analysis_id=analysis.id, decision=decision,
                                    sizing=None, risk_approved=False,
                                    risk_checks_passed=[], risk_checks_failed=['magnitude_staleness'],
                                    risk_rejection_reasons=[stale_reason],
                                    executed=False, mt5_ticket=None, executed_price=None,
                                    executed_lots=None, mt5_error=None, position_id=None,
                                    timestamp=start, elapsed_ms=0,
                                )
                        except Exception as e:
                            logger.debug(f"Magnitude staleness check failed: {e}")

            except Exception as brief_err:
                logger.debug(f"Brief age check failed (non-fatal): {brief_err}")

        # Cegah eksekusi order duplikat (Phase 5)
        from database.models import Position
        
        # Memory cache check to prevent race conditions
        global _EXECUTED_ANALYSIS_IDS
        _prune_executed_analysis_ids()
        if analysis.id in _EXECUTED_ANALYSIS_IDS:
            logger.warning(
                f"Execution REJECTED for {symbol}: Position already exists in memory cache for analysis_id {analysis.id} (duplicate_analysis_execution)"
            )
            return ExecutionResult(
                symbol=symbol, analysis_id=analysis.id, decision=decision,
                sizing=None, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['duplicate_analysis_execution'],
                risk_rejection_reasons=[f"Position already exists for this analysis (id={analysis.id})."],
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=0,
            )
            
        is_duplicate = (await session.execute(
            select(Position).where(Position.analysis_id == analysis.id).limit(1)
        )).scalar_one_or_none()
        
        # Cache-Before-Commit pattern:
        # Update _EXECUTED_ANALYSIS_IDS if position already exists in DB (duplicate).
        # For new executions, cache is updated only after MT5 order placement succeeds.
        if is_duplicate:
            _EXECUTED_ANALYSIS_IDS[analysis.id] = time.time()
            logger.warning(
                f"Execution REJECTED for {symbol}: Position already exists in DB for analysis_id {analysis.id} (duplicate_analysis_execution)"
            )
            return ExecutionResult(
                symbol=symbol, analysis_id=analysis.id, decision=decision,
                sizing=None, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['duplicate_analysis_execution'],
                risk_rejection_reasons=[f"Position already exists for this analysis (id={analysis.id})."],
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=0,
            )
            
        # NOTE: _EXECUTED_ANALYSIS_IDS[analysis.id] TIDAK di-set di sini.
        # Validasi Koneksi MT5 (Task 1.4)
        if not self.dry_run and isinstance(self.broker_adapter, MT5LiveAdapter):
            is_connected = await self.mt5.ensure_connected()
            if not is_connected:
                logger.error(f"Execution ABORTED for {symbol}: MT5 is not connected.")
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                return ExecutionResult(
                    symbol=symbol, analysis_id=analysis.id, decision=decision,
                    sizing=None, risk_approved=False,
                    risk_checks_passed=[], risk_checks_failed=['mt5_disconnected'],
                    risk_rejection_reasons=["MT5 connection is dead. Cannot place order safely."],
                    executed=False, mt5_ticket=None, executed_price=None,
                    executed_lots=None, mt5_error="MT5 Disconnected", position_id=None,
                    timestamp=start, elapsed_ms=elapsed,
                )

        # Check if post-release exemption applies
        if not is_post_release and analysis:
            txt = (
                str(getattr(analysis, "execution_notes", "") or "") + " " +
                str(getattr(analysis, "catalyst", "") or "") + " " +
                str(getattr(analysis, "reasoning", "") or "")
            ).lower()
            if "post-release" in txt or "post_release" in txt:
                is_post_release = True

        # News Blackout Check
        from database.models import EconomicCalendar
        from datetime import timedelta
        from utils.market.currency_utils import get_symbol_currencies
        news_window_minutes = self.settings.get('trading', {}).get('risk', {}).get('news_window_minutes', 30)
        blackout_window = timedelta(minutes=news_window_minutes)
        sym_currencies = get_symbol_currencies(symbol)
        
        upcoming = (await session.execute(
            select(EconomicCalendar)
            .where(EconomicCalendar.event_time >= start - blackout_window)
            .where(EconomicCalendar.event_time <= start + blackout_window)
            .where(EconomicCalendar.impact.in_(["high", "High", "HIGH"]))
            .where(EconomicCalendar.currency.in_(list(sym_currencies)))
        )).scalars().all()
        
        if upcoming and not is_post_release:
            logger.warning(
                f"Execution REJECTED for {symbol}: News blackout circuit breaker "
                f"triggered by {upcoming[0].event_name}"
            )
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol, analysis_id=analysis.id, decision=decision,
                sizing=None, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['news_blackout'],
                risk_rejection_reasons=[f"Trading blocked: Near high-impact news ({upcoming[0].event_name})"],
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=elapsed,
            )
        elif upcoming and is_post_release:
            logger.info(
                f"Execution ALLOWED for {symbol}: Post-release analysis exempt from news blackout ({upcoming[0].event_name})."
            )
        # Priced-in score gating is centralized upstream in risk_gate.py

        # Parsing kondisi entry
        entry_cond = {}
        if analysis.entry_zone:
            if isinstance(analysis.entry_zone, dict):
                entry_cond = analysis.entry_zone
            else:
                try:
                    entry_cond = json.loads(analysis.entry_zone)
                except Exception as e:
                    logger.debug(f"Failed to parse entry_zone JSON: {e}")
                    entry_cond = {}

        max_price_staleness = self.settings.get("execution", {}).get("max_price_staleness_seconds", 120)
        entry_price_raw, is_stale, age_seconds = await self._get_current_price(symbol, decision)
        
        if symbol == 'USDJPY' and not is_stale:
            PositionSizer.update_usdjpy_cache(entry_price_raw)
        
        if is_stale and age_seconds > max_price_staleness:
            logger.error(
                f"Execution ABORTED for {symbol}: price data is {age_seconds:.0f}s old "
                f"(limit={max_price_staleness}s). MT5 must be connected for safe execution."
            )
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=symbol, analysis_id=analysis.id, decision=decision,
                sizing=None, risk_approved=False,
                risk_checks_passed=[], risk_checks_failed=['stale_price_data'],
                risk_rejection_reasons=[
                    f"Price data {age_seconds:.0f}s old — MT5 connection required for execution"
                ],
                executed=False, mt5_ticket=None, executed_price=None,
                executed_lots=None, mt5_error=None, position_id=None,
                timestamp=start, elapsed_ms=elapsed,
            )

        if not is_stale and not self.dry_run:
            try:
                from utils.validation.data_validator import is_spread_acceptable
                if hasattr(self, 'broker_adapter') and self.broker_adapter is not None:
                    tick = await self.broker_adapter.get_tick(symbol)
                else:
                    tick = await self.mt5.get_current_price(symbol)
                if tick is None:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    return ExecutionResult(
                        symbol=symbol, analysis_id=analysis.id, decision=decision,
                        sizing=None, risk_approved=False,
                        risk_checks_passed=[], risk_checks_failed=['spread_check_unavailable'],
                        risk_rejection_reasons=["Cannot verify spread: price data unavailable."],
                        executed=False, mt5_ticket=None, executed_price=None,
                        executed_lots=None, mt5_error=None, position_id=None,
                        timestamp=start, elapsed_ms=elapsed,
                    )
                if tick and not is_spread_acceptable(symbol, tick['bid'], tick['ask']):
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    return ExecutionResult(
                        symbol=symbol, analysis_id=analysis.id, decision=decision,
                        sizing=None, risk_approved=False,
                        risk_checks_passed=[], risk_checks_failed=['spread_too_high'],
                        risk_rejection_reasons=["Spread circuit breaker triggered. Spread too wide."],
                        executed=False, mt5_ticket=None, executed_price=None,
                        executed_lots=None, mt5_error=None, position_id=None,
                        timestamp=start, elapsed_ms=elapsed,
                    )
            except Exception as e:
                logger.debug(f"Spread check failed (non-fatal): {e}")

        try:
            specified_price = float(entry_cond['price']) if entry_cond.get('price') is not None else None
        except (ValueError, TypeError):
            specified_price = None

        entry_price = specified_price if specified_price is not None else entry_price_raw
        order_type  = entry_cond.get('order_type') or entry_cond.get('type', 'market')

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
            
            if order_type == 'limit':
                # Validasi pergeseran harga pasar sejak analisis dibuat (Market Drift), BUKAN jarak limit ke harga pasar
                analyzed_market_price = float(getattr(analysis, 'price_at_analysis', current_price) or current_price)
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
                        symbol=symbol, analysis_id=analysis.id, decision=decision,
                        sizing=None, risk_approved=False,
                        risk_checks_passed=[], risk_checks_failed=['stale_entry_price'],
                        risk_rejection_reasons=[f"Market moved {market_drift_pct:.2f}% from analysis price (threshold {threshold*2}%)"],
                        executed=False, mt5_ticket=None, executed_price=None,
                        executed_lots=None, mt5_error=None, position_id=None,
                        timestamp=start, elapsed_ms=elapsed,
                    )
            elif order_type == 'market':
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
                        symbol=symbol, analysis_id=analysis.id, decision=decision,
                        sizing=None, risk_approved=False,
                        risk_checks_passed=[], risk_checks_failed=['stale_entry_price'],
                        risk_rejection_reasons=[f"Market price deviated {price_diff_pct:.2f}% (threshold {threshold}%)"],
                        executed=False, mt5_ticket=None, executed_price=None,
                        executed_lots=None, mt5_error=None, position_id=None,
                        timestamp=start, elapsed_ms=elapsed,
                    )

        # Ambil live equity
        if account_equity is None:
            account_equity = await self._get_equity()
        if account_equity is None or account_equity <= 0:
            account_equity = float(self.settings.get('paper_trading', {}).get('initial_balance', 10000.0))

        # Ambil level VIX terbaru untuk risiko dinamis
        vix_level = 18.0
        try:
            from database.models import VIXData
            vix_row = (await session.execute(
                select(VIXData).order_by(VIXData.date.desc()).limit(1)
            )).scalar_one_or_none()
            if vix_row:
                vix_level = vix_row.close
        except Exception as e:
            logger.debug(f"Failed to fetch VIX for sizing: {e}")

        # Ambil scaling risiko dinamis
        risk_cfg = self.settings.get("trading", {}).get("risk", {})
        base_risk_pct = risk_cfg.get("risk_percent_per_trade", 1.5)
        risk_percent_override = await self._get_dynamic_risk_percent(session, symbol, base_risk_pct)

        # NEW: fold analysis.risk_multiplier into risk_pct BEFORE sizing (defensive clamp 0.0-2.0, floor 0.30 if > 0)
        analysis_risk_multiplier = getattr(analysis, 'risk_multiplier', None)
        if analysis_risk_multiplier is not None:
            try:
                clamped_mult = max(0.0, min(2.0, float(analysis_risk_multiplier)))
                if 0.0 < clamped_mult < 0.30:
                    clamped_mult = 0.30
            except (TypeError, ValueError):
                clamped_mult = 1.0
            if clamped_mult != float(analysis_risk_multiplier):
                logger.warning(f'[{symbol}] risk_multiplier {analysis_risk_multiplier} adjusted/clamped to {clamped_mult}')
            risk_percent_override = risk_percent_override * clamped_mult

        tp_price = float(analysis.take_profit) if analysis.take_profit is not None else None
        sl_price = float(analysis.stop_loss) if analysis.stop_loss is not None else 0.0
        
        # (TP distance sanity checks are now centralized in tool_executor.py during generation)
        
        # Langkah 1: Position sizing under advisory lock
        async with transactional_advisory_lock(session, lock_key=f"sizing_{symbol}") as is_locked:
            if not is_locked:
                return ExecutionResult(
                    symbol=symbol, analysis_id=analysis.id, decision=decision,
                    sizing=None, risk_approved=False,
                    risk_checks_passed=[],
                    risk_checks_failed=['advisory_lock_contention'],
                    risk_rejection_reasons=['Concurrent execution locked by another transaction/worker.'],
                    executed=False, mt5_ticket=None, executed_price=None,
                    executed_lots=None, mt5_error=None, position_id=None,
                    timestamp=start, elapsed_ms=0,
                )
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
                analysis=analysis
            )

            if not verdict.approved:
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                result = ExecutionResult(
                    symbol=symbol, analysis_id=analysis.id, decision=decision,
                    sizing=sizing,
                    risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed,
                    risk_rejection_reasons=verdict.rejection_reasons,
                    executed=False, mt5_ticket=None, executed_price=None,
                    executed_lots=None, mt5_error=None, position_id=None,
                    timestamp=start, elapsed_ms=elapsed,
                )
                await self._log_result(session, result, analysis.id)
                logger.warning(f"Execution blocked: {result.summary()}")
                return result
            
        is_edge_signal = getattr(analysis, 'decision_source', None) == 'edge_registry'

        if verdict.approved and analysis.decision in ('buy', 'sell') and is_edge_signal:
            if (analysis.confidence or 0.0) < 0.3:
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                return ExecutionResult(symbol=symbol, analysis_id=analysis.id, decision=decision, sizing=sizing,
                                        risk_approved=False, risk_checks_passed=verdict.checks_passed,
                                        risk_checks_failed=verdict.checks_failed + ['edge_signal_low_confidence'],
                                        risk_rejection_reasons=[f'Edge signal confidence {analysis.confidence} < 0.3 minimum'],
                                        executed=False, mt5_ticket=None, executed_price=None, executed_lots=None,
                                        mt5_error=None, position_id=None, timestamp=start, elapsed_ms=elapsed)

        if verdict.approved and analysis.decision in ('buy', 'sell') and not is_edge_signal:
            # --- MINIMUM VERIFIABLE CONFLUENCE GATE ---
            min_verifiable = self.settings.get('trading', {}).get('risk', {}).get('min_verifiable_confluence', 4)
            if (analysis.confluence_score or 0) < min_verifiable:
                logger.warning(f"Execution BLOCKED for {symbol}: confluence score {analysis.confluence_score} < min_verifiable ({min_verifiable})")
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                return ExecutionResult(
                    symbol=symbol, analysis_id=analysis.id, decision=decision,
                    sizing=sizing, risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ['insufficient_confluence'],
                    risk_rejection_reasons=[f'Confluence score {analysis.confluence_score} < minimum required {min_verifiable}'],
                    executed=False, mt5_ticket=None, executed_price=None,
                    executed_lots=None, mt5_error=None, position_id=None,
                    timestamp=start, elapsed_ms=elapsed
                )

            if self.settings.get("trading", {}).get("risk", {}).get("confluence_verifier_enabled", True):
                try:
                    from analysis.validators.confluence_verifier import verify_confluence
                    verification = await verify_confluence(session, analysis, self.settings)
                    if not verification['verified']:
                        logger.warning(
                            f'Confluence verification FAILED for {symbol}: '
                            f'{verification["blocking_issues"]}'
                        )
                        
                        # Block execution jika ada blocking issues
                        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                        return ExecutionResult(
                            symbol=symbol, analysis_id=analysis.id, decision=decision,
                            sizing=sizing, risk_approved=False,
                            risk_checks_passed=verdict.checks_passed,
                            risk_checks_failed=verdict.checks_failed + ['confluence_verification'],
                            risk_rejection_reasons=[f'Confluence verification: {issue}' 
                                                   for issue in verification['blocking_issues']],
                            executed=False, mt5_ticket=None, executed_price=None,
                            executed_lots=None, mt5_error=None, position_id=None,
                            timestamp=start, elapsed_ms=elapsed
                        )
                    else:
                        score_val = verification.get("claude_score") or verification.get("ai_score") or verification.get("score")
                        logger.info(
                            f'Confluence verified for {symbol}: '
                            f'computed={verification["computed_score"]}, '
                            f'ai={score_val}'
                        )
                except Exception as e:
                    logger.warning(f'Confluence verification error (non-fatal, proceeding): {e}')

        # Task 2.1: Adversarial Validation Pass (Pre-Execution) - Reuse cached check if already run
        if verdict.approved and analysis.decision in ('buy', 'sell') and not is_edge_signal and self.settings.get('adversarial_check', {}).get('enabled', True):
            from database.models import SystemConfig
            cached_adv = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == f'adversarial_outcome_{analysis.id}')
            )).scalar_one_or_none()
            adv = None
            if cached_adv and cached_adv.value:
                try:
                    adv = json.loads(cached_adv.value)
                except Exception:
                    pass
            if not adv:
                from analysis.validators.adversarial_check import run_adversarial_check
                adv = await run_adversarial_check(session, analysis, self.settings)
            if adv.get('hard_block'):
                logger.warning(f"[{symbol}] HARD BLOCKED by adversarial check: {adv.get('hard_block_reason')}")
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                return ExecutionResult(symbol=symbol, analysis_id=analysis.id, decision=decision,
                    sizing=sizing, risk_approved=False, risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ['adversarial_hard_block'],
                    risk_rejection_reasons=[adv.get('hard_block_reason', '')],
                    executed=False, mt5_ticket=None, executed_price=None, executed_lots=None,
                    mt5_error=None, position_id=None, timestamp=start, elapsed_ms=elapsed)
            if adv.get('recommend_block') and adv.get('overall_quality') == 'low':
                logger.warning(f"[{symbol}] Adversarial check recommends block: {adv.get('block_reason')}")
                try:
                    await AgentNotifier().send_warning(f"⚠️ Adversarial Check — {symbol}\n{adv.get('strongest_counter_argument', '')[:200]}")
                except Exception:
                    pass

        # Fase 2: Execution (dengan DB transactional advisory lock, singkat)
        async with transactional_advisory_lock(session, lock_key=f"exec_{symbol}") as is_locked:
            if not is_locked:
                return ExecutionResult(
                    symbol=symbol, analysis_id=analysis.id, decision=decision,
                    sizing=sizing, risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ['advisory_lock_contention'],
                    risk_rejection_reasons=['Concurrent execution locked by another transaction/worker.'],
                    executed=False, mt5_ticket=None, executed_price=None,
                    executed_lots=None, mt5_error=None, position_id=None,
                    timestamp=start, elapsed_ms=0,
                )
            # Re-check cache duplikat dan database karena mungkin ada yang mengeksekusi selama kita di Fase 1 (Validation)
            db_duplicate_pos = None
            if analysis.id:
                db_duplicate_pos = (await session.execute(
                    select(Position).where(Position.analysis_id == analysis.id).limit(1)
                )).scalar_one_or_none()

            if (analysis.id in _EXECUTED_ANALYSIS_IDS) or (db_duplicate_pos is not None):
                logger.warning(
                    f"Execution REJECTED post-lock for {symbol}: Position already executed "
                    f"while waiting for lock (analysis_id={analysis.id})."
                )
                return ExecutionResult(
                    symbol=symbol, analysis_id=analysis.id, decision=decision,
                    sizing=sizing, risk_approved=False,
                    risk_checks_passed=verdict.checks_passed,
                    risk_checks_failed=verdict.checks_failed + ['duplicate_analysis_post_lock'],
                    risk_rejection_reasons=['Position was executed while waiting for lock.'],
                    executed=False, mt5_ticket=None, executed_price=None,
                    executed_lots=None, mt5_error=None, position_id=None,
                    timestamp=start, elapsed_ms=0,
                )
                
            # Concurrency safety: Re-check portfolio limits under execution lock
            # immediately prior to MT5 order placement to prevent concurrent execution races.
            try:
                from database.models import Position as _Position
                from sqlalchemy import select as _select, func as _func
                
                # Check for existing open position on the same symbol under the mutex
                symbol_open_exists = (await session.execute(
                    _select(_Position.id)
                    .where(_Position.symbol == symbol, _Position.status == 'open')
                )).scalar_one_or_none()
                if symbol_open_exists:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    logger.warning(
                        f'[Pre-MT5 Re-check] BLOCKED {symbol}: Open position already exists for {symbol} '
                        f'(symbol race condition prevented).'
                    )
                    return ExecutionResult(
                        symbol=symbol, analysis_id=analysis.id, decision=decision,
                        sizing=sizing, risk_approved=False,
                        risk_checks_passed=verdict.checks_passed,
                        risk_checks_failed=verdict.checks_failed + ['pre_mt5_symbol_recheck'],
                        risk_rejection_reasons=[
                            f'Race condition guard: Open position already exists for {symbol}.'
                        ],
                        executed=False, mt5_ticket=None, executed_price=None,
                        executed_lots=None, mt5_error=None, position_id=None,
                        timestamp=start, elapsed_ms=elapsed,
                    )

                re_check_open_count = (await session.execute(
                    _select(_func.count()).select_from(_Position)
                    .where(_Position.status == 'open')
                )).scalar_one_or_none() or 0
                
                max_concurrent = self.settings.get('trading', {}).get('risk', {}).get('max_concurrent_positions', 4)
                if re_check_open_count >= max_concurrent:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    logger.warning(
                        f'[Pre-MT5 Re-check] BLOCKED {symbol}: {re_check_open_count}/{max_concurrent} '
                        f'positions already open (race condition prevented).'
                    )
                    return ExecutionResult(
                        symbol=symbol, analysis_id=analysis.id, decision=decision,
                        sizing=sizing, risk_approved=False,
                        risk_checks_passed=verdict.checks_passed,
                        risk_checks_failed=verdict.checks_failed + ['pre_mt5_position_recheck'],
                        risk_rejection_reasons=[
                            f'Race condition guard: {re_check_open_count} positions open '
                            f'(limit={max_concurrent}). Position filled between risk check and execution.'
                        ],
                        executed=False, mt5_ticket=None, executed_price=None,
                        executed_lots=None, mt5_error=None, position_id=None,
                        timestamp=start, elapsed_ms=elapsed,
                    )
            except Exception as recheck_err:
                logger.debug(f'Pre-MT5 position re-check failed (non-fatal, proceeding): {recheck_err}')

            # Pilar 4: Evidence-First Pre-Trade Assertions
            verifier_enabled = self.settings.get("trading", {}).get("risk", {}).get("confluence_verifier_enabled", False)
            if verifier_enabled and hasattr(self, 'evidence_verifier') and self.evidence_verifier:
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
                        cf_raw = getattr(analysis, "confluence_factors_json", None) or getattr(analysis, "confluence_factors", None)
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
                        "invalidation": getattr(analysis, 'invalidation_condition', None) or analysis.invalidation or str(analysis.invalidation_price or ""),
                        "key_evidence": key_evidence,
                        "confluence_factors_json": key_evidence,
                        "rationale": getattr(analysis, "rationale", ""),
                    }
                    passed, assertions_failed = await self.evidence_verifier.pre_trade_assertions(signal_dict, session=session)
                    if not passed:
                        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                        logger.warning(f"Pre-trade assertions failed for {symbol}: {assertions_failed}")
                        return ExecutionResult(
                            symbol=symbol, analysis_id=analysis.id, decision=decision,
                            sizing=sizing, risk_approved=False,
                            risk_checks_passed=verdict.checks_passed,
                            risk_checks_failed=verdict.checks_failed + ['evidence_first_assertions'],
                            risk_rejection_reasons=assertions_failed,
                            executed=False, mt5_ticket=None, executed_price=None,
                            executed_lots=None, mt5_error=None, position_id=None,
                            timestamp=start, elapsed_ms=elapsed,
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
                session, order, OrderStatus.PENDING_SUBMIT,
                reason="Analysis order initialized"
            )
            await self._transition_order_state(
                session, order, OrderStatus.INTENT_COMMITTED,
                reason="Order intent committed to database with replay_policy=never",
                details={"analysis_id": analysis.id, "adapter": type(self.broker_adapter).__name__, "replay_policy": "never"}
            )
            await session.flush()
            await self._transition_order_state(
                session, order, OrderStatus.SUBMITTED,
                reason="Submitting analysis order to broker adapter",
                details={"analysis_id": analysis.id, "adapter": type(self.broker_adapter).__name__}
            )
            await session.flush()

            throttler = getattr(self, "rate_throttler", None)
            if throttler is not None:
                throttle_verdict = await throttler.wait_and_acquire(timeout=5.0)
                if not throttle_verdict.allowed:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    logger.warning(f"[RateThrottler] Analysis order throttled for {symbol}: {throttle_verdict.reason}")
                    await self._transition_order_state(
                        session, order, OrderStatus.REJECTED,
                        reason=f"Order rate throttled: {throttle_verdict.reason}",
                    )
                    return ExecutionResult(
                        symbol=symbol, analysis_id=analysis.id, decision=decision,
                        sizing=sizing, risk_approved=False,
                        risk_checks_passed=verdict.checks_passed,
                        risk_checks_failed=verdict.checks_failed + ['order_rate_throttled'],
                        risk_rejection_reasons=[f"Order rate throttled: {throttle_verdict.reason}. Retry after {throttle_verdict.retry_after}s"],
                        executed=False, mt5_ticket=None, executed_price=None,
                        executed_lots=None, mt5_error=f"Throttled: {throttle_verdict.reason}",
                        position_id=None, timestamp=start, elapsed_ms=elapsed,
                    )

            # R-1: Race condition pre-MT5 position re-check
            try:
                re_check_open_count = (await session.execute(select(func.count()).select_from(Position).where(Position.status == 'open'))).scalar_one_or_none() or 0
                max_concurrent = self.settings.get('trading', {}).get('risk', {}).get('max_concurrent_positions', 5)
                if re_check_open_count >= max_concurrent:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    logger.warning(f'[Pre-MT5 Re-check] BLOCKED {symbol}: {re_check_open_count}/{max_concurrent} positions already open (race condition prevented).')
                    await self._transition_order_state(
                        session, order, OrderStatus.REJECTED,
                        reason=f"Race condition guard: {re_check_open_count} positions open (limit={max_concurrent})",
                    )
                    return ExecutionResult(
                        symbol=symbol, analysis_id=analysis.id, decision=decision, sizing=sizing, risk_approved=False,
                        risk_checks_passed=verdict.checks_passed, risk_checks_failed=verdict.checks_failed + ['pre_mt5_position_recheck'],
                        risk_rejection_reasons=[f'Race condition guard: {re_check_open_count} positions open (limit={max_concurrent}). Position filled between risk check and execution.'],
                        executed=False, mt5_ticket=None, executed_price=None, executed_lots=None, mt5_error=None, position_id=None, timestamp=start, elapsed_ms=elapsed
                    )
            except Exception as recheck_err:
                logger.debug(f'Pre-MT5 position re-check failed (non-fatal, proceeding): {recheck_err}')

            # Submit order to broker adapter under EffectGate admission
            try:
                if hasattr(self, "effect_gate") and self.effect_gate is not None:
                    mt5_result = await self.effect_gate.admit(
                        lambda: self.broker_adapter.submit_order(
                            order=order,
                            sl=sl_price,
                            tp=tp_price,
                            comment=comment,
                            max_spread_multiplier=max_spread_mult,
                        ),
                        context_name=f"order_{order.client_order_id}_{symbol}"
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
                    session, order, OrderStatus.ABORT_REQUESTED,
                    reason=f"Effect gate blocked execution: {abort_err}",
                )
                await session.flush()
                return ExecutionResult(
                    symbol=symbol, analysis_id=analysis.id, decision=decision, sizing=sizing, risk_approved=False,
                    risk_checks_passed=verdict.checks_passed, risk_checks_failed=verdict.checks_failed + ['effect_gate_aborted'],
                    risk_rejection_reasons=[f"Effect gate blocked execution: {abort_err}"],
                    executed=False, mt5_ticket=None, executed_price=None, executed_lots=None, mt5_error=str(abort_err),
                    position_id=None, timestamp=start, elapsed_ms=elapsed
                )

            is_pending: bool = False
            if mt5_result.get('success'):
                status_returned = mt5_result.get('status')
                is_pending = (
                    status_returned in ('accepted', 'pending')
                    or (
                        (order.order_type or "").upper() in ("LIMIT", "STOP", "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP")
                        and float(mt5_result.get('executed_volume', 0.0)) == 0.0
                    )
                )
                exec_vol = float(mt5_result.get('executed_volume', 0.0))
                req_vol = float(order.requested_volume)

                reported_slippage = mt5_result.get('slippage_pips')
                exec_price = mt5_result.get('price')
                if reported_slippage is not None:
                    slippage = float(reported_slippage)
                elif exec_price is not None and entry_price:
                    from utils.market.instrument_identity import resolve_instrument_identity
                    sym_id = resolve_instrument_identity(order.symbol or symbol)
                    slippage = SizingCalculator.compute_slippage_pips(float(entry_price), float(exec_price), pip_size=sym_id.pip_size)
                else:
                    slippage = 0.0

                if is_pending:
                    await self._transition_order_state(
                        session, order, OrderStatus.ACCEPTED,
                        reason=f"Broker accepted pending order: ticket={mt5_result.get('ticket')}",
                        ticket=mt5_result.get('ticket'),
                        executed_price=exec_price,
                        slippage_pips=slippage,
                        filled_volume=0.0,
                        details={"analysis_id": analysis.id, "order_type": order.order_type, "status": "accepted"}
                    )
                elif 0.0 < exec_vol < req_vol:
                    await self._transition_order_state(
                        session, order, OrderStatus.PARTIALLY_FILLED,
                        reason=f"Partially filled {exec_vol}/{req_vol} lots at {exec_price}, ticket={mt5_result.get('ticket')}",
                        ticket=mt5_result.get('ticket'),
                        executed_price=exec_price,
                        slippage_pips=slippage,
                        filled_volume=exec_vol,
                        details={"analysis_id": analysis.id, "order_type": order.order_type, "status": "partially_filled", "filled_volume": exec_vol}
                    )
                else:
                    await self._transition_order_state(
                        session, order, OrderStatus.FILLED,
                        reason=f"Filled at {exec_price}, ticket={mt5_result.get('ticket')}",
                        ticket=mt5_result.get('ticket'),
                        executed_price=exec_price,
                        slippage_pips=slippage,
                        filled_volume=exec_vol if exec_vol > 0 else req_vol,
                        details={"analysis_id": analysis.id, "order_type": order.order_type, "status": "filled"}
                    )
            else:
                await self._transition_order_state(
                    session, order, OrderStatus.REJECTED,
                    reason=mt5_result.get('error') or "Broker order rejected",
                )

            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000

            # Step 4: Persist position to database if order is directly filled (market order)
            position_id = None
            if mt5_result.get('success'):
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
                            raise RuntimeError(f"Failed to persist position to DB for ticket {mt5_result.get('ticket')}")
                        await session.commit()
                    except Exception as db_err:
                        logger.critical(f"DB save failed after MT5 order {mt5_result.get('ticket')}. CLOSING orphan position.")
                        orphan_ticket = mt5_result.get('ticket')
                        try:
                            if not self.dry_run and orphan_ticket is not None:
                                if hasattr(self, 'broker_adapter') and self.broker_adapter:
                                    await self.broker_adapter.close_position(int(orphan_ticket))
                                else:
                                    await self.mt5.close_position(int(orphan_ticket))
                        except Exception as close_err:
                            await AgentNotifier().send_critical(f"ORPHAN TRADE: ticket={orphan_ticket} {symbol}. DB and close both failed!")
                        raise
                    
                    # Buka record paper trade untuk pelacakan (berlaku untuk dry-run & live)
                    try:
                        from utils.analytics.paper_tracker import PaperTracker
                        paper_tracker = PaperTracker(self.settings)
                        eff_risk_pct = sizing.risk_percent
                        await paper_tracker.open_paper_trade(session, analysis, risk_pct=eff_risk_pct)
                    except Exception as e:
                        logger.debug(f"Paper trade open failed (non-fatal): {e}")
                else:
                    await session.commit()

                # Stateful Multi-Phase Trade Plan (Probe 30%, Runner 70%)
                try:
                    from database.models import TradePlan, TradePlanLeg, TechnicalIndicator

                    total_lots = sizing.recommended_lots
                    if total_lots <= 0.01:
                        probe_lots = round(total_lots, 2)
                        runner_lots = 0.0
                    else:
                        probe_lots = round(max(0.01, round(total_lots * 0.30, 2)), 2)
                        runner_lots = round(max(0.0, round(total_lots - probe_lots, 2)), 2)

                    atr_val = None
                    atr_row = (await session.execute(
                        select(TechnicalIndicator)
                        .where(TechnicalIndicator.symbol == symbol, TechnicalIndicator.timeframe == "H1", TechnicalIndicator.indicator_name == "ATR_14")
                        .order_by(TechnicalIndicator.timestamp.desc())
                        .limit(1)
                    )).scalar_one_or_none()
                    if atr_row:
                        try:
                            atr_val = float(json.loads(atr_row.value_json))
                        except Exception:
                            pass

                    if not atr_val or atr_val <= 0:
                        atr_val = entry_price * 0.005

                    tp1_price = round(entry_price + (1.0 * atr_val) if decision == 'buy' else entry_price - (1.0 * atr_val), 5)
                    tp2_price = tp_price or round(entry_price + (2.0 * atr_val) if decision == 'buy' else entry_price - (2.0 * atr_val), 5)

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
                        notes=f"Multi-phase trade plan: probe={probe_lots}L (30%), runner={runner_lots}L (70%), TP1={tp1_price}"
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
                        ticket_id=mt5_result.get('ticket'),
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
                            ticket_id=mt5_result.get('ticket'),
                            position_id=position_id,
                            status=leg_status,
                            filled_at=leg_filled_at,
                        )
                        legs_to_add.append(runner_leg)

                    session.add_all(legs_to_add)
                    await session.commit()
                    logger.info(f"[{symbol}] Created TradePlan #{trade_plan.id}: probe={probe_lots}L (30%), runner={runner_lots}L (70%)")
                except Exception as tp_err:
                    logger.debug(f"TradePlan creation non-fatal: {tp_err}")
                    
                # Log AI Decision (Real Trade)
                try:
                    from analysis.memory.decision_log import DecisionLogger
                    await DecisionLogger.log_decision(
                        session=session,
                        analysis_id=analysis.id,
                        symbol=symbol,
                        decision=decision,
                        confidence=analysis.confidence or 0.0,
                        confluence_score=analysis.confluence_score,
                        rationale=analysis.rationale or ""
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
                                    f"⚠️ <b>Execution Verification Flagged</b>\n"
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
                        ticket=mt5_result.get('ticket'),
                        fundamental_brief=fund_brief,
                        specialist_outputs=spec_out,
                        debate_verdict=deb_verdict,
                        risk_decision={"approved": True, "lots": sizing.recommended_lots, "ticket": mt5_result.get('ticket')},
                        execution_details=mt5_result
                    )
                except Exception as verif_err:
                    logger.debug(f"Verification/Trajectory logging non-fatal error: {verif_err}")
    
                # Update timestamp eksekusi sukses terakhir
                try:
                    exec_key = "last_successful_execution"
                    cfg = (await session.execute(
                        select(SystemConfig).where(SystemConfig.key == exec_key)
                    )).scalar_one_or_none()
                    exec_info = json.dumps({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "symbol": symbol,
                        "direction": decision,
                        "lots": sizing.recommended_lots,
                    })
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
            executed=mt5_result.get('success', False),
            mt5_ticket=mt5_result.get('ticket'),
            executed_price=mt5_result.get('price'),
            executed_lots=sizing.recommended_lots if mt5_result.get('success') else None,
            mt5_error=mt5_result.get('error'),
            position_id=position_id,
            timestamp=start,
            elapsed_ms=elapsed,
        )

        await self._log_result(session, result, analysis.id)

        if result.executed:
            logger.info(f"TRADE PLACED: {result.summary()}")
            try:
                notifier = AgentNotifier()
                msg = (
                    f"✅ <b>TRADE EXECUTED — {result.symbol}</b>\n\n"
                    f"Direction: {result.decision.upper()}\n"
                    f"Lots: {result.executed_lots}\n"
                    f"Entry: {result.executed_price}\n"
                    f"<b>Ticket MT5: <code>{result.mt5_ticket}</code></b>\n\n"
                    f"<i>(Use /close {result.mt5_ticket} to manual close)</i>"
                )
                await notifier.send_info(msg)
            except Exception as e:
                logger.error(f"Failed to notify trade execution: {e}")
        else:
            logger.error(f"TRADE FAILED: {result.summary()}")
            try:
                notifier = AgentNotifier()
                await notifier.send_warning(f"❌ <b>TRADE FAILED</b>\n{result.summary()}")
            except Exception as e:
                logger.error(f"Failed to notify trade failure: {e}")
        _prune_executed_analysis_ids()


        return result


    async def execute_by_analysis_id(
        self,
        analysis_id: int,
        account_equity: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Muat AssetAnalysis berdasarkan ID dan jalankan eksekusi.
        Digunakan oleh ChatAgent saat user menyetujui proposed order dari DB.
        """
        async with get_session() as session:
            analysis = await session.get(AssetAnalysis, analysis_id)
            if analysis is None:
                raise ValueError(f"AssetAnalysis id={analysis_id} not found")
            return await self.execute_analysis(session, analysis, account_equity)


    async def _save_position(
        self,
        session: AsyncSession,
        analysis: AssetAnalysis,
        sizing: SizingResult,
        mt5_result: dict,
        pair_group_id: Optional[str] = None,
        auto_commit: bool = True,
        order_id: Optional[str] = None,
    ) -> Optional[int]:
        """Create a Position record in DB after successful MT5 order via TradeAuditLogger."""
        from execution.service.audit_logger import TradeAuditLogger
        return await TradeAuditLogger.save_position(
            session=session,
            analysis=analysis,
            sizing=sizing,
            mt5_result=mt5_result,
            dry_run=self.dry_run,
            pair_group_id=pair_group_id,
            auto_commit=auto_commit,
            order_id=order_id,
        )

    async def _log_result(
        self,
        session: AsyncSession,
        result: ExecutionResult,
        analysis_id: Optional[int],
    ) -> None:
        """Write execution result to ActivityLog via TradeAuditLogger."""
        from execution.service.audit_logger import TradeAuditLogger
        await TradeAuditLogger.log_result(
            session=session,
            summary_text=result.summary(),
            analysis_id=analysis_id,
        )

