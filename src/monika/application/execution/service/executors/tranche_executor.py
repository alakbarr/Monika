# ==============================================================================
# File: application/execution/service/executors/tranche_executor.py
# ==============================================================================

"""
Tranche Order Execution Mixin.
Handles splitting orders into sequential or multi-target sub-legs (e.g. TP1/TP2 scaling).
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import logging
import random
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.execution.service.base import _ExecutionServiceMixinBase
from monika.domain.execution.order_creator import OrderCreator
from monika.domain.risk.position_sizing import PositionSizer, get_instrument_spec
from monika.infrastructure.brokers.broker_adapter import MT5LiveAdapter
from monika.infrastructure.database.models import (
    AssetAnalysis,
    Order,
    OrderStatus,
    Position,
)

logger = logging.getLogger("TradingAgent.ExecutionService.OrderExecutor")


class TrancheOrderMixin(_ExecutionServiceMixinBase):
    """Mixin providing multi-target tranche order scaling."""

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
        from monika.application.execution.service.order_executor import (
            _EXECUTED_ANALYSIS_IDS,
            AgentNotifier,
            safe_commit,
            transactional_advisory_lock,
        )

        start = clock.now()
        symbol = analysis.symbol
        decision = (analysis.decision or "").lower()

        if decision not in ("buy", "sell"):
            return {"success": False, "reason": f"Decision '{decision}' is not tradeable"}

        # Calculate sizing
        entry_price = float(
            getattr(analysis, "current_price", None)
            or analysis.entry_price
            or getattr(analysis, "price_at_analysis", None)
            or 0.0
        )
        sl_price = float(analysis.stop_loss or 0.0)
        tp_price = float(analysis.take_profit or 0.0)

        if account_equity is None and self.dry_run:
            account_equity = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))

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
            logger.info(
                f"Total lots {total_lots} too small for tranche split ({lots_1}/{lots_2}) with min_lot {min_lot}. Falling back to single order."
            )
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
        tp_2 = getattr(analysis, "take_profit_2", None)
        if not tp_2:
            r_dist = abs(tp_price - entry_price)
            if decision == "buy":
                tp_2 = round(entry_price + (r_dist * 1.5), 5)
            else:
                tp_2 = round(entry_price - (r_dist * 1.5), 5)

        max_spread_mult = self.settings.get("execution", {}).get("max_spread_multiplier", {}).get(symbol, 10.0)

        async def _submit_tranche_leg(
            leg_num: int, lots: float, tp: Optional[float], comment_tag: str
        ) -> Tuple[Optional[Order], dict]:
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
                session, order, OrderStatus.PENDING_SUBMIT, reason=f"Tranche leg {leg_num} initialized"
            )
            await self._transition_order_state(
                session,
                order,
                OrderStatus.INTENT_COMMITTED,
                reason=f"Order intent committed for tranche leg {leg_num}",
                details={"analysis_id": analysis.id, "group_id": tranche_group_id},
            )
            await session.flush()
            await self._transition_order_state(
                session,
                order,
                OrderStatus.SUBMITTED,
                reason=f"Submitting tranche leg {leg_num} to broker adapter",
                details={"analysis_id": analysis.id, "group_id": tranche_group_id},
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
                            context_name=f"tranche_l{leg_num}_{order.client_order_id}_{symbol}",
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
                        import hashlib
                        import random

                        t = (
                            int(
                                hashlib.md5(
                                    f"{symbol}_{start.isoformat()}_{random.randint(10000, 99999)}_{comment_tag}".encode()
                                ).hexdigest(),
                                16,
                            )
                            % 9000000
                            + 1000000
                        )
                        res = {"success": True, "ticket": t, "price": entry_price, "error": None}
                    else:
                        res = await self.mt5.place_order(
                            symbol,
                            decision,
                            lots,
                            None,
                            sl_price,
                            tp,
                            comment=f"TRANCHE:{group_id[:6]}:{comment_tag}",
                        )
            except Exception as submit_err:
                logger.error(f"Tranche leg {leg_num} submission failed: {submit_err}")
                res = {"success": False, "error": str(submit_err)}

            if inspect.isawaitable(res):
                res = await res

            if res.get("success"):
                await self._transition_order_state(
                    session,
                    order,
                    OrderStatus.FILLED,
                    reason=f"Tranche leg {leg_num} filled",
                    ticket=res.get("ticket"),
                    executed_price=res.get("price") or entry_price,
                    filled_volume=lots,
                )
            else:
                await self._transition_order_state(
                    session, order, OrderStatus.REJECTED, reason=f"Tranche leg {leg_num} failed: {res.get('error')}"
                )
            return order, res

        # Place Leg 1
        order_leg1, res_leg1 = await _submit_tranche_leg(1, lots_1, tp_price, "L1")
        if not res_leg1.get("success"):
            await session.commit()
            return {"success": False, "reason": f"Leg 1 order failed: {res_leg1.get('error')}"}

        # Place Leg 2
        order_leg2, res_leg2 = await _submit_tranche_leg(2, lots_2, tp_2, "L2")
        if not res_leg2.get("success"):
            logger.error(
                f"Leg 2 order failed ({res_leg2.get('error')}). Rolling back Leg 1 ticket {res_leg1.get('ticket')}"
            )

            rollback_ok = False
            close_err = None
            if self.dry_run:
                rollback_ok = True
            elif res_leg1.get("ticket"):
                try:
                    adapter = getattr(self, "broker_adapter", None)
                    if adapter and hasattr(adapter, "close_position"):
                        close_res = await adapter.close_position(res_leg1["ticket"])
                    elif self.mt5:
                        close_res = await self.mt5.close_position(res_leg1["ticket"])
                    else:
                        close_res = {"success": False, "error": "No broker adapter or MT5 client available"}
                    rollback_ok = bool(close_res and close_res.get("success"))
                    if not rollback_ok:
                        close_err = close_res.get("error") if close_res else "Close position failed"
                except Exception as ex:
                    close_err = str(ex)
                    rollback_ok = False

            if not rollback_ok:
                err_msg = close_err or "Unknown error closing Leg 1"
                logger.critical(
                    f"EMERGENCY: Could not close orphan Leg 1 {symbol} ticket={res_leg1.get('ticket')}! Error: {err_msg}"
                )
                try:
                    await AgentNotifier().send_critical(
                        f"[DARURAT] ORPHAN TRANCHE EMERGENCY: {symbol} ticket={res_leg1.get('ticket')} rollback failed ({err_msg})!"
                    )
                except Exception as notif_err:
                    logger.error(f"Failed to send orphan alert: {notif_err}")

                analysis.execution_status = "orphan_emergency"
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
                    pos = (
                        await session.execute(select(Position).where(Position.mt5_ticket == res_leg1["ticket"]))
                    ).scalar_one_or_none()
                    if pos:
                        pos.status = "orphan_pending_close"
                    await session.commit()
                except Exception as save_orphan_err:
                    logger.error(f"Failed to persist orphan record: {save_orphan_err}")

                return {"success": False, "reason": f"Leg 2 order failed and Leg 1 rollback failed: {err_msg}"}
            else:
                analysis.execution_status = "rolled_back"
                analysis.execution_notes = (
                    f"Leg 2 order failed ({res_leg2.get('error')}). Leg 1 rolled back successfully."
                )
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
            f"[OK] Multi-leg Tranche executed: {symbol} {decision.upper()} "
            f"L1={lots_1}L @ TP {tp_price}, L2={lots_2}L @ TP {tp_2} "
            f"[group={tranche_group_id}]"
        )

        return {
            "success": True,
            "tranche_group_id": tranche_group_id,
            "tickets": [res_leg1.get("ticket"), res_leg2.get("ticket")],
            "lots": [lots_1, lots_2],
            "tps": [tp_price, tp_2],
        }
