# ==============================================================================
# File: application/execution/service/executors/analysis_executor.py
# ==============================================================================

"""
AssetAnalysis execution coordinator mixin.
Composes preflight validation and order submission passes into a unified pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.execution.service.executors.analysis_preflight import AnalysisPreflightMixin
from monika.application.execution.service.executors.analysis_submission import AnalysisSubmissionMixin
from monika.application.execution.service.base import _ExecutionServiceMixinBase
from monika.domain.risk.position_sizing import SizingResult
from monika.infrastructure.database.models import AssetAnalysis, Order, OrderStatus

if TYPE_CHECKING:
    from monika.application.execution.service.order_executor import ExecutionResult

logger = logging.getLogger("TradingAgent.ExecutionService.OrderExecutor")


class AnalysisOrderMixin(AnalysisPreflightMixin, AnalysisSubmissionMixin, _ExecutionServiceMixinBase):
    """Mixin coordinating single AssetAnalysis execution lifecycle."""

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
        from monika.application.execution.service.order_lifecycle_service import OrderLifecycleService

        await OrderLifecycleService.transition_order_state(
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
        from monika.application.execution.service.order_executor import _EXECUTED_ANALYSIS_IDS, get_session
        from monika.application.execution.service.reconciliation import ReconciliationHelper

        async with get_session() as session:
            await ReconciliationHelper.restore_executed_ids_from_db(session, _EXECUTED_ANALYSIS_IDS)

    async def execute_analysis(
        self,
        session: AsyncSession,
        analysis: AssetAnalysis,
        account_equity: Optional[float] = None,
        is_post_release: bool = False,
        **kwargs,
    ) -> ExecutionResult:
        """Memproses satu AssetAnalysis melalui pipeline eksekusi lengkap."""
        return await self._execute_analysis_internal(
            session, analysis, account_equity, is_post_release=is_post_release, **kwargs
        )

    async def _execute_analysis_internal(
        self,
        session: AsyncSession,
        analysis: AssetAnalysis,
        account_equity: Optional[float] = None,
        is_post_release: bool = False,
        **kwargs,
    ) -> ExecutionResult:
        """Internal execution pipeline delegating to preflight validation and locked broker submission."""
        fail_res, ctx = await self._validate_analysis_preflight(
            session=session,
            analysis=analysis,
            account_equity=account_equity,
            is_post_release=is_post_release,
            **kwargs,
        )
        if fail_res is not None:
            return fail_res

        assert ctx is not None
        return await self._submit_and_record_order(
            session=session,
            analysis=analysis,
            ctx=ctx,
            **kwargs,
        )

    async def execute_by_analysis_id(
        self,
        analysis_id: int,
        account_equity: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Muat AssetAnalysis berdasarkan ID dan jalankan eksekusi.
        Digunakan oleh ChatAgent saat user menyetujui proposed order dari DB.
        """
        from monika.application.execution.service.order_executor import get_session

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
        from monika.infrastructure.brokers.audit_logger import TradeAuditLogger

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
        from monika.infrastructure.brokers.audit_logger import TradeAuditLogger

        await TradeAuditLogger.log_result(
            session=session,
            summary_text=result.summary(),
            analysis_id=analysis_id,
        )
        try:
            from monika.core.telemetry.metrics_exporter import metrics

            if result.executed:
                metrics.inc_counter("trades_executed_total", 1.0, labels={"symbol": result.symbol})
            elif not result.risk_approved:
                metrics.inc_counter("trades_risk_blocked_total", 1.0, labels={"symbol": result.symbol})
            else:
                metrics.inc_counter("trades_failed_total", 1.0, labels={"symbol": result.symbol})
            if result.elapsed_ms > 0:
                metrics.record_histogram("execution_latency_ms", float(result.elapsed_ms))
        except Exception:
            pass
