# ==============================================================================
# File: application/execution/service/executors/proposal_executor.py
# ==============================================================================

"""
TradeProposal financial fortress executor mixin.
Handles admission validation, idempotency guards, and plugin waterfall hooks.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.execution.service.base import _ExecutionServiceMixinBase

if TYPE_CHECKING:
    from monika.application.execution.service.order_executor import ExecutionResult

logger = logging.getLogger("TradingAgent.ExecutionService.OrderExecutor")


class ProposalOrderMixin(_ExecutionServiceMixinBase):
    """Mixin for executing immutable TradeProposal objects through Fortress gate."""

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
        from monika.application.execution.service.order_executor import ExecutionResult

        start = clock.now()
        from monika.application.agent.estop import get_estop_details, is_estop_active

        if is_estop_active():
            estop_info = get_estop_details() or {}
            reason = estop_info.get("reason", "ESTOP sentinel active")
            logger.critical(f"[ESTOP] execute_proposal blocked for {proposal.symbol}: {reason}")
            elapsed = (clock.now() - start).total_seconds() * 1000
            return ExecutionResult(
                symbol=proposal.symbol,
                analysis_id=proposal.metadata.get("analysis_id")
                if hasattr(proposal, "metadata") and proposal.metadata
                else getattr(proposal, "id", None),
                decision=proposal.direction.lower() if hasattr(proposal, "direction") else "hold",
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
                elapsed_ms=elapsed,
            )

        from monika.domain.risk.trade_proposal import FortressAdmissionValidator

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
        from monika.infrastructure.brokers.idempotency_guard import get_idempotency_guard

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

        meta = proposal.metadata if hasattr(proposal, "metadata") and isinstance(proposal.metadata, dict) else {}
        ana_obj = getattr(proposal, "analysis", None)
        analysis_id = meta.get("analysis_id") or getattr(ana_obj, "id", None)
        priced_in_score = meta.get("priced_in_score") or getattr(ana_obj, "priced_in_score", None)
        pair_group_id = meta.get("pair_group_id") or getattr(ana_obj, "pair_group_id", None)

        order_plan = {
            "symbol": proposal.symbol,
            "decision": proposal.direction.lower(),
            "entry_price": proposal.entry_price,
            "stop_loss": proposal.stop_loss,
            "take_profit": proposal.take_profit,
            "lot_size": proposal.lot_size,
            "confluence_score": int(proposal.confluence_score),
            "priced_in_score": priced_in_score,
            "analysis_id": analysis_id,
            "pair_group_id": pair_group_id,
        }

        # Pre-order waterfall hook
        try:
            from monika.application.harness.engine import get_plugin_engine

            engine = get_plugin_engine()
            if engine:
                allowed, plan_or_reason = await engine.emit_waterfall(
                    "pre_order",
                    order_plan,
                    proposal=proposal,
                    symbol=proposal.symbol,
                )
                if not allowed:
                    await guard.release_lock(idem_key)
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
            from monika.application.harness.engine import get_plugin_engine

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
