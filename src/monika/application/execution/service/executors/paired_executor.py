# ==============================================================================
# File: application/execution/service/executors/paired_executor.py
# ==============================================================================

"""
Paired & Hedged Execution Mixin.
Handles simultaneous two-legged market and spread hedged orders with atomic rollback.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.execution.effect_gate import AbortRequested
from monika.application.execution.service.base import _ExecutionServiceMixinBase
from monika.domain.execution.order_creator import OrderCreator
from monika.domain.risk.position_sizing import PositionSizer
from monika.infrastructure.brokers.broker_adapter import MT5LiveAdapter
from monika.infrastructure.database.models import (
    AssetAnalysis,
    Order,
    OrderStatus,
    PaperTradeRecord,
    Position,
)

logger = logging.getLogger("TradingAgent.ExecutionService.OrderExecutor")


class PairedOrderMixin(_ExecutionServiceMixinBase):
    """Mixin providing paired two-leg analysis and spread hedging execution."""

    async def execute_paired_analyses(
        self,
        session: AsyncSession,
        primary: AssetAnalysis,
        hedge: AssetAnalysis,
        pair_group_id: str,
        account_equity: Optional[float] = None,
    ) -> dict:
        """Execute a paired stat-arb trade. Both legs must fill or neither does."""
        from monika.application.execution.service.order_executor import (
            _EXECUTED_ANALYSIS_IDS,
            AgentNotifier,
            safe_commit,
            transactional_advisory_lock,
        )

        logger.info(
            f"Paired execution: {primary.symbol} {primary.decision} + "
            f"{hedge.symbol} {hedge.decision} [group={pair_group_id[:8]}]"
        )

        # Phase 1: Size with notional-weighted lots for proper spread hedge
        # Step 1: Size primary leg at full risk (the "anchor" leg)
        fallback_equity = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
        equity = account_equity if account_equity is not None else (await self._get_equity() or fallback_equity)
        spread_risk = self.settings.get("trading", {}).get("risk", {}).get("risk_percent_per_trade", 1.0)
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
                p_price = float(p_ez.get("price", 0))
                if p_price <= 0:
                    raise ValueError(f"Invalid primary entry price: {p_price}")
            except Exception as e:
                logger.warning(f"Failed to parse primary entry_zone: {e}")
                return {"success": False, "reason": f"Invalid primary entry_zone: {e}"}

            p_sl = float(primary.stop_loss) if primary.stop_loss is not None else 0.0
            p_tp = float(primary.take_profit) if primary.take_profit is not None else None

            sizing_primary = await self.sizer.calculate_with_session(
                session,
                primary.symbol,
                primary.decision,
                p_price,
                p_sl,
                p_tp,
                equity,
                risk_percent_override=spread_risk,
            )

            if not sizing_primary.is_valid:
                return {"success": False, "reason": f"Primary sizing failed: {sizing_primary.rejection_reasons}"}

            # Step 2: Calculate notional-weighted hedge lots
            # Goal: equal USD notional on both legs for market-neutral spread
            primary_info = await self.mt5.get_symbol_info(primary.symbol)
            hedge_info = await self.mt5.get_symbol_info(hedge.symbol)

            if not primary_info or not hedge_info:
                return {"success": False, "reason": "Symbol info unavailable for notional weighting"}

            primary_contract = primary_info.get("contract_size") or primary_info.get("trade_contract_size", 100)
            hedge_contract = hedge_info.get("contract_size") or hedge_info.get("trade_contract_size", 100)
            primary_notional = p_price * primary_contract

            try:
                if isinstance(hedge.entry_zone, dict):
                    h_ez = hedge.entry_zone
                else:
                    h_ez = json.loads(hedge.entry_zone) if hedge.entry_zone else {}
                h_price = float(h_ez.get("price", 0))
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
            lot_step = max(float(hedge_info.get("volume_step") or 0.01), 0.001)
            vol_min = max(float(hedge_info.get("volume_min") or 0.01), 0.001)
            vol_max = max(float(hedge_info.get("volume_max") or 100.0), vol_min)
            hedge_lots = max(vol_min, min(vol_max, round(round(raw_hedge_lots / lot_step) * lot_step, 2)))

            h_sl = float(hedge.stop_loss) if hedge.stop_loss is not None else 0.0
            h_tp = float(hedge.take_profit) if hedge.take_profit is not None else None

            # Build a SizingResult for the hedge leg
            sizing_hedge = await self.sizer.calculate_with_session(
                session,
                hedge.symbol,
                hedge.decision,
                h_price,
                h_sl,
                h_tp,
                equity,
                risk_percent_override=spread_risk,
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
                return {
                    "success": False,
                    "reason": f"Primary leg risk gate rejected: {verdict_primary.rejection_reasons}",
                }

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

            logger.info(
                f"Notional weighting: {primary.symbol}={sizing_primary.recommended_lots} lots "
                f"({primary_contract} contract), {hedge.symbol}={hedge_lots} lots "
                f"({hedge_contract} contract), ratio={primary_notional / hedge_notional:.3f}"
            )

            # Check max_concurrent_positions (pair counts as 2)
            open_count = await self._count_open_positions(session)
            max_pos = self.settings.get("trading", {}).get("risk", {}).get("max_concurrent_positions", 5)
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
                session, order_primary, OrderStatus.PENDING_SUBMIT, reason="Paired LEG1 order initialized"
            )
            await self._transition_order_state(
                session,
                order_primary,
                OrderStatus.INTENT_COMMITTED,
                reason="Paired LEG1 order intent committed",
                details={"pair_group_id": pair_group_id, "leg": 1},
            )
            await session.flush()
            await self._transition_order_state(
                session,
                order_primary,
                OrderStatus.SUBMITTED,
                reason="Submitting paired LEG1 order to broker adapter",
                details={"pair_group_id": pair_group_id, "leg": 1},
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
                            context_name=f"pair_l1_{order_primary.client_order_id}_{primary.symbol}",
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
                        import hashlib
                        import random

                        collision_seed_p = f"{primary.symbol}_{datetime.now(timezone.utc).isoformat()}_{random.randint(10000, 99999)}_LEG1"
                        dry_ticket_p = int(hashlib.md5(collision_seed_p.encode()).hexdigest(), 16) % 9000000 + 1000000
                        logger.info(
                            f"DRY RUN: Would execute paired LEG1 {primary.decision.upper()} {sizing_primary.recommended_lots} lots for {primary.symbol} (mock ticket: {dry_ticket_p})"
                        )
                        result_primary = {"success": True, "ticket": dry_ticket_p, "price": p_price, "error": None}
                    else:
                        result_primary = await self.mt5.place_order(
                            primary.symbol,
                            primary.decision,
                            sizing_primary.recommended_lots,
                            None,
                            primary.stop_loss,
                            primary.take_profit,
                            comment=f"PAIR:{pair_group_id[:8]}:LEG1",
                        )
            except AbortRequested as abort_err:
                logger.warning(f"[EffectGate] Paired LEG1 blocked for {primary.symbol}: {abort_err}")
                await self._transition_order_state(
                    session,
                    order_primary,
                    OrderStatus.ABORT_REQUESTED,
                    reason=f"Effect gate blocked execution: {abort_err}",
                )
                result_primary = {"success": False, "error": str(abort_err)}

            if not result_primary.get("success"):
                await self._transition_order_state(
                    session,
                    order_primary,
                    OrderStatus.REJECTED,
                    reason=f"Primary leg failed: {result_primary.get('error')}",
                )
                primary.execution_status = "failed"
                primary.execution_notes = f"Primary leg failed: {result_primary.get('error')}"
                await session.commit()
                return {"success": False, "reason": primary.execution_notes}
            else:
                await self._transition_order_state(
                    session,
                    order_primary,
                    OrderStatus.FILLED,
                    reason="Primary leg filled successfully",
                    ticket=result_primary.get("ticket"),
                    executed_price=result_primary.get("price"),
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
                session, order_hedge, OrderStatus.PENDING_SUBMIT, reason="Paired LEG2 order initialized"
            )
            await self._transition_order_state(
                session,
                order_hedge,
                OrderStatus.INTENT_COMMITTED,
                reason="Paired LEG2 order intent committed",
                details={"pair_group_id": pair_group_id, "leg": 2},
            )
            await session.flush()
            await self._transition_order_state(
                session,
                order_hedge,
                OrderStatus.SUBMITTED,
                reason="Submitting paired LEG2 order to broker adapter",
                details={"pair_group_id": pair_group_id, "leg": 2},
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
                            context_name=f"pair_l2_{order_hedge.client_order_id}_{hedge.symbol}",
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
                        import hashlib
                        import random

                        collision_seed_h = f"{hedge.symbol}_{datetime.now(timezone.utc).isoformat()}_{random.randint(10000, 99999)}_LEG2"
                        dry_ticket_h = int(hashlib.md5(collision_seed_h.encode()).hexdigest(), 16) % 9000000 + 1000000
                        logger.info(
                            f"DRY RUN: Would execute paired LEG2 {hedge.decision.upper()} {sizing_hedge.recommended_lots} lots for {hedge.symbol} (mock ticket: {dry_ticket_h})"
                        )
                        result_hedge = {"success": True, "ticket": dry_ticket_h, "price": h_price, "error": None}
                    else:
                        result_hedge = await self.mt5.place_order(
                            hedge.symbol,
                            hedge.decision,
                            sizing_hedge.recommended_lots,
                            None,
                            hedge.stop_loss,
                            hedge.take_profit,
                            comment=f"PAIR:{pair_group_id[:8]}:LEG2",
                        )
            except AbortRequested as abort_err:
                logger.warning(f"[EffectGate] Paired LEG2 blocked for {hedge.symbol}: {abort_err}")
                await self._transition_order_state(
                    session,
                    order_hedge,
                    OrderStatus.ABORT_REQUESTED,
                    reason=f"Effect gate blocked execution: {abort_err}",
                )
                result_hedge = {"success": False, "error": str(abort_err)}

            if not result_hedge.get("success"):
                await self._transition_order_state(
                    session,
                    order_hedge,
                    OrderStatus.REJECTED,
                    reason=f"Hedge leg failed: {result_hedge.get('error')}",
                )
                # CRITICAL: Rollback primary leg immediately (C-2)
                logger.error(f"Hedge leg failed! Rolling back primary: ticket={result_primary.get('ticket')}")
                if adapter is not None:
                    close_result = await adapter.close_position(result_primary["ticket"])
                elif self.dry_run:
                    close_result = {"success": True, "error": None}
                else:
                    close_result = await self.mt5.close_position(result_primary["ticket"])
                if not close_result or not close_result.get("success"):
                    err_msg = close_result.get("error") if close_result else "No response from MT5"
                    logger.critical(
                        f"EMERGENCY: Could not close orphan primary leg {primary.symbol} ticket={result_primary['ticket']}! Error: {err_msg}"
                    )
                    try:
                        await AgentNotifier().send_critical(
                            f"[DARURAT] ORPHAN TRADE EMERGENCY: {primary.symbol} ticket={result_primary['ticket']} close failed ({err_msg})!"
                        )
                    except Exception as notif_err:
                        logger.error(f"Failed to send orphan trade emergency alert: {notif_err}")
                    primary.execution_status = "orphan_emergency"
                    primary.execution_notes = (
                        f"Hedge failed ({result_hedge.get('error')}). Primary rollback FAILED: {err_msg}"
                    )

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
                        primary_pos = (
                            await session.execute(
                                select(Position).where(Position.mt5_ticket == result_primary["ticket"])
                            )
                        ).scalar_one_or_none()
                        if primary_pos:
                            primary_pos.status = "orphan_pending_close"
                    except Exception as save_orphan_err:
                        logger.error(f"Failed to persist orphan record: {save_orphan_err}")
                else:
                    primary.execution_status = "rolled_back"
                    primary.execution_notes = (
                        f"Hedge leg failed ({result_hedge.get('error')}). Primary rolled back successfully."
                    )
                hedge.execution_status = "failed"
                hedge.execution_notes = f"Hedge failed: {result_hedge.get('error')}"
                await session.commit()
                return {"success": False, "reason": "Hedge leg failed, rollback processed"}
            else:
                await self._transition_order_state(
                    session,
                    order_hedge,
                    OrderStatus.FILLED,
                    reason="Hedge leg filled successfully",
                    ticket=result_hedge.get("ticket"),
                    executed_price=result_hedge.get("price"),
                    filled_volume=sizing_hedge.recommended_lots,
                )

            # Mark executed analysis IDs in dedup cache
            _EXECUTED_ANALYSIS_IDS[primary.id] = time.time()
            _EXECUTED_ANALYSIS_IDS[hedge.id] = time.time()

            # Phase 3: Save both positions with pair_group_id inside lock to prevent race conditions
            try:
                await self._save_position(
                    session, primary, sizing_primary, result_primary, pair_group_id=pair_group_id, auto_commit=False
                )
                await self._save_position(
                    session, hedge, sizing_hedge, result_hedge, pair_group_id=pair_group_id, auto_commit=False
                )
                await session.commit()

                # Buka record paper trade untuk pelacakan (berlaku untuk dry-run & live)
                try:
                    from monika.core.analytics.paper_tracker import PaperTracker

                    paper_tracker = PaperTracker(self.settings)
                    await paper_tracker.open_paper_trade(session, primary, risk_pct=sizing_primary.risk_percent)
                    await paper_tracker.open_paper_trade(session, hedge, risk_pct=sizing_hedge.risk_percent)
                except Exception as paper_err:
                    logger.debug(f"Paper trade open for pair failed (non-fatal): {paper_err}")
            except Exception as db_err:
                logger.critical(
                    f"DB save failed after paired MT5 orders {result_primary.get('ticket')}/{result_hedge.get('ticket')}: {db_err}. CLOSING orphan paired positions."
                )
                if not self.dry_run:
                    for t in (result_primary.get("ticket"), result_hedge.get("ticket")):
                        if t:
                            try:
                                await self.mt5.close_position(t)
                            except Exception as close_err:
                                await AgentNotifier().send_critical(
                                    f"ORPHAN PAIRED TRADE: ticket={t}. DB commit and close both failed: {close_err}"
                                )
                raise

        logger.info(f"[OK] Paired trade executed: {primary.symbol}+{hedge.symbol} [group={pair_group_id[:8]}]")
        return {"success": True, "tickets": [result_primary["ticket"], result_hedge["ticket"]]}
