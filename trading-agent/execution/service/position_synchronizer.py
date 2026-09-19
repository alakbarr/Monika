# ==============================================================================
# File: execution/service/position_synchronizer.py
# ==============================================================================

import asyncio
import json
import logging
import math
import uuid
import time
import sys
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
from risk.position_sizing import PositionSizer, SizingResult
from risk.risk_gate import RiskGate
from utils.infra.notifier import AgentNotifier
from execution.service.state_machine import OrderStateMachine

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


from execution.service.base import _ExecutionServiceMixinBase

logger = logging.getLogger("TradingAgent.ExecutionService.PositionSynchronizer")

class PositionSynchronizerMixin(_ExecutionServiceMixinBase):
    """Mixin untuk rekonsiliasi posisi MT5 dengan database lokal dan modifikasi SL/TP."""

    async def sync_positions(self) -> dict:
        """Sinkronisasi posisi terbuka antara MT5 dan DB lokal."""
        async with get_session() as session:
            result = await self.mt5.sync_positions_from_mt5(session)
            
            if result.get("closed_positions"):
                import MetaTrader5 as mt5
                for pos in result["closed_positions"]:
                    reason = getattr(pos, "_mt5_close_reason", None)
                    if reason == mt5.DEAL_REASON_SL:
                        logger.warning(f"STOP LOSS HIT for ticket {pos.mt5_ticket}. PnL: {pos.pnl}")
                        await self._handle_stop_loss_hit(session, pos)
                    elif reason == mt5.DEAL_REASON_TP:
                        logger.info(f"TAKE PROFIT HIT for ticket {pos.mt5_ticket}. PnL: {pos.pnl}")
                    
                    # Update risk state for ALL natural closures (SL/TP/other)
                    if pos.pnl is not None:
                        try:
                            equity = None
                            try:
                                acct = await self.mt5.get_account_info()
                                equity = acct.get('equity') if acct else None
                            except Exception:
                                pass
                            if hasattr(self, 'gate') and self.gate:
                                await self.gate.update_risk_state(
                                    session, pnl_delta=pos.pnl, equity=equity
                                )
                        except Exception as e:
                            logger.error(f"Failed to update risk state after natural close {pos.mt5_ticket}: {e}")
                    
                    try:
                        holding_duration: Optional[float] = None
                        o_dt = pos.opened_at
                        c_dt = pos.closed_at
                        if o_dt is not None and c_dt is not None:
                            holding_duration = max(0.0, (c_dt - o_dt).total_seconds() / 3600.0)
                        
                        from database.models import AssetAnalysis, TradeOutcome
                        related_analysis = (await session.execute(
                            select(AssetAnalysis)
                            .where(AssetAnalysis.symbol == pos.symbol)
                            .where(AssetAnalysis.generated_at <= pos.opened_at)
                            .where(AssetAnalysis.decision.in_(["buy", "sell"]))
                            .order_by(AssetAnalysis.generated_at.desc())
                            .limit(1)
                        )).scalar_one_or_none()
                        
                        exit_price = getattr(pos, "_mt5_exit_price", None)
                        if not exit_price:
                            spec = self.sizer._get_instrument_spec(pos.symbol)
                            contract_size = getattr(spec, "contract_size", 100000.0) if spec else 100000.0
                            vol = pos.volume or 0.1
                            dir_sign = 1.0 if (pos.direction or '').lower() == 'buy' else -1.0
                            price_delta = ((pos.pnl or 0.0) / (vol * contract_size)) * dir_sign if (vol * contract_size) > 0 else 0.0
                            exit_price = pos.entry_price + price_delta

                        pos_comment = (getattr(pos, 'comment', None) or '').lower()
                        if reason == mt5.DEAL_REASON_SL:
                            exit_reason_mapped = "sl_hit"
                        elif reason == mt5.DEAL_REASON_TP:
                            exit_reason_mapped = "tp_hit"
                        elif "trailing" in pos_comment or "trail" in pos_comment:
                            exit_reason_mapped = "trailing_sl"
                        elif "breakeven" in pos_comment or "be" in pos_comment:
                            exit_reason_mapped = "breakeven_sl"
                        elif "partial" in pos_comment:
                            exit_reason_mapped = "partial_tp"
                        else:
                            exit_reason_mapped = "other"

                        outcome = TradeOutcome(
                            analysis_id=related_analysis.id if related_analysis else None,
                            position_id=pos.id,
                            symbol=pos.symbol,
                            direction=pos.direction,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            stop_loss=pos.sl,
                            take_profit=pos.tp,
                            pnl_usd=pos.pnl,
                            confluence_score=related_analysis.confluence_score if related_analysis else None,
                            priced_in_score=related_analysis.priced_in_score if related_analysis else None,
                            analysis_confidence=related_analysis.confidence if related_analysis else None,
                            opened_at=pos.opened_at,
                            closed_at=pos.closed_at,
                            holding_hours=holding_duration,
                            was_profitable=(pos.pnl or 0) > 0,
                            exit_reason=exit_reason_mapped,
                            was_debate_modified=bool(getattr(related_analysis, "was_debate_modified", False)) if related_analysis else False,
                            decision_source=getattr(related_analysis, "decision_source", None) if related_analysis else None,
                        )
                        session.add(outcome)
                        await session.commit()

                        if related_analysis and related_analysis.id:
                            # Non-blocking async background task to decouple reflection latency from position sync hot-path
                            async def _bg_link_outcome(an_id: int, pnl_val: float, h_hours: float, ex_reason: str):
                                try:
                                    async with get_session() as bg_sess:
                                        from analysis.memory.outcome_linker import OutcomeLinker
                                        await OutcomeLinker().process_closed_position(
                                            bg_sess,
                                            analysis_id=an_id,
                                            pnl=pnl_val,
                                            holding_hours=h_hours,
                                            exit_reason=ex_reason
                                        )
                                except Exception as linker_err:
                                    logger.debug(f'Background OutcomeLinker failed for analysis {an_id}: {linker_err}')

                            asyncio.create_task(_bg_link_outcome(
                                related_analysis.id,
                                pos.pnl or 0.0,
                                holding_duration or 0.0,
                                "sl_hit" if reason == mt5.DEAL_REASON_SL else ("tp_hit" if reason == mt5.DEAL_REASON_TP else "other")
                            ))

                        # Update trade trajectory outcome for learning loop
                        try:
                            from benchmark.trade_trajectory_logger import TradeTrajectoryLogger
                            TradeTrajectoryLogger().update_trajectory_outcome(
                                ticket=pos.mt5_ticket,
                                symbol=pos.symbol,
                                pnl_usd=pos.pnl,
                                reflection_tags=[exit_reason_mapped],
                            )
                        except Exception as traj_err:
                            logger.debug(f"Trajectory outcome update non-fatal: {traj_err}")
                    except Exception as e:
                        logger.debug(f"Failed to log trade outcome (non-fatal): {e}")

                closed_in_db = len(result["closed_positions"])
                # Check if EA might have closed positions (heartbeat stale)
                try:
                    from execution.ea_bridge.heartbeat_writer import HeartbeatManager
                    mt5_common = self.settings.get('execution', {}).get('mt5_common_dir')
                    hb_mgr = HeartbeatManager(mt5_common_path=mt5_common)
                    ea_alive, stale_seconds = hb_mgr.check_ea_alive()
                    if not ea_alive and stale_seconds > 0:
                        logger.critical(
                            f'EA heartbeat is stale ({stale_seconds}s)! '
                            f'{closed_in_db} positions closed outside system — EA dead-man switch may have triggered!'
                        )
                        try:
                            from utils.infra.notifier import AgentNotifier
                            await AgentNotifier().send_critical(
                                f'🚨 <b>EA Dead-Man Switch Suspected</b>\n'
                                f'{closed_in_db} position(s) closed outside system control.\n'
                                f'EA heartbeat stale: {stale_seconds}s\n'
                                f'Manual verification required immediately!'
                            )
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug(f'EA heartbeat check in sync failed (non-fatal): {e}')

            return result


    async def _handle_stop_loss_hit(self, session: AsyncSession, position: Position):
        logger.warning(f'SL Hit detected for {position.symbol}. Ticket: {position.mt5_ticket}')
        
        # Hanya set per-symbol cooldown, TIDAK pause global
        cooldown_hours = self.settings.get('trading', {}).get('risk', {}).get('post_sl_cooldown_hours', 6)
        
        # Cek berapa SL hits hari ini
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        from database.models import TradeOutcome, PaperTradeRecord
        from sqlalchemy import select, func
        today_sl_hits = (await session.execute(
            select(func.count(PaperTradeRecord.id))
            .where(PaperTradeRecord.closed_at >= today_start)
            .where(PaperTradeRecord.exit_reason == 'sl_hit')
        )).scalar_one_or_none() or 0
        
        # Pause global jika ada 3+ SL hits dalam sehari
        max_daily_sl = self.settings.get('trading', {}).get('risk', {}).get('max_daily_sl_hits', 3)
        paper_cfg = self.settings.get('trading', {}).get('paper_trading', {})
        pause_on_limit = paper_cfg.get('pause_system_on_daily_sl_limit', False)
        is_auto_execute = self.settings.get('trading', {}).get('auto_execute', False)

        if today_sl_hits >= max_daily_sl:
            if is_auto_execute or pause_on_limit:
                await self.gate.pause_trading(
                    session=session, 
                    reason=f'Auto-paused: {today_sl_hits} SL hits today (limit: {max_daily_sl})'
                )
                logger.critical(f'Global trading pause: {today_sl_hits} SL hits today')
            else:
                logger.warning(
                    f'[PaperTrading] Daily SL hit threshold reached: {today_sl_hits}/{max_daily_sl}. '
                    f'System pause bypassed due to paper_trading.pause_system_on_daily_sl_limit=false.'
                )
        
        # Notify tanpa pause global
        try:
            from utils.infra.notifier import AgentNotifier
            await AgentNotifier().send_warning(
                f'⚠️ <b>STOP LOSS HIT</b>\nSymbol: {position.symbol}\nTicket: {position.mt5_ticket}\nPnL: {position.pnl}\n'
                f'Per-symbol cooldown: {cooldown_hours}h (risk gate will handle)'
            )
        except Exception as e:
            logger.error(f'Failed to notify SL hit: {e}')


    async def modify_position_sl_tp(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        requested_by: str = "system",
    ) -> dict:
        """Modifikasi SL/TP pada posisi yang terbuka."""
        # P1-1: Paper positions — update DB only, no real MT5 call
        async with get_session() as session:
            db_pos = (await session.execute(
                select(Position).where(Position.mt5_ticket == ticket)
            )).scalar_one_or_none()
            if db_pos and getattr(db_pos, 'is_paper', False):
                if sl is not None:
                    db_pos.sl = sl
                if tp is not None:
                    db_pos.tp = tp
                if db_pos.analysis_id and sl is not None:
                    from utils.analytics.paper_tracker import PaperTracker
                    await PaperTracker(self.settings).update_paper_trade_sl(session, db_pos.analysis_id, sl)
                await session.commit()
                return {'success': True, 'paper': True}

        throttler = getattr(self, "rate_throttler", None)
        if throttler is not None:
            throttle_verdict = await throttler.acquire()
            if not throttle_verdict.allowed:
                logger.warning(
                    f"[RateThrottler] Position modification throttled for ticket {ticket}: {throttle_verdict.reason}"
                )
                return {
                    "success": False,
                    "error": f"Position modification rate throttled: {throttle_verdict.reason}",
                    "retcode": 10027,
                    "retry_after": throttle_verdict.retry_after,
                }

        result = await self.mt5.modify_position(ticket, sl=sl, tp=tp)
        async with get_session() as session:
            pos_symbol = 'UNKNOWN'
            if result.get('success'):
                db_pos = (await session.execute(
                    select(Position).where(Position.mt5_ticket == ticket)
                )).scalar_one_or_none()
                if db_pos:
                    pos_symbol = db_pos.symbol or 'UNKNOWN'
                    if sl is not None:
                        db_pos.sl = sl
                    if tp is not None:
                        db_pos.tp = tp
            else:
                db_pos = (await session.execute(
                    select(Position).where(Position.mt5_ticket == ticket)
                )).scalar_one_or_none()
                if db_pos and db_pos.symbol:
                    pos_symbol = db_pos.symbol

            session.add(OrderLog(
                action='modify',
                symbol=pos_symbol,
                params_json=json.dumps({'ticket': ticket, 'sl': sl, 'tp': tp}),
                requested_by=requested_by,
                approved_by='execution_service' if result.get('success') else 'REJECTED',
                result=json.dumps(result),
            ))
            await session.commit()
        return result

    async def reconcile_inflight_orders(self) -> dict:
        """
        Reconcile in-flight orders stuck in INTENT_COMMITTED or SUBMITTED state (C-4).
        Pi Pattern: replay_policy='never' means we NEVER blindly re-execute on restart.

        Algorithm:
        1. Query DB for orders in (INTENT_COMMITTED, SUBMITTED).
        2. Match against broker open positions (by symbol, direction, volume).
        3. If matched at broker -> settle as FILLED, record settlement timestamp.
        4. If not found at broker -> mark as INTERRUPTED (terminal state).
        5. Log critical notification.
        """
        logger.info("[Recovery] Scanning for in-flight orders (INTENT_COMMITTED, SUBMITTED)...")
        reconciled_count = 0
        interrupted_count = 0

        async with get_session() as session:
            inflight_orders = (await session.execute(
                select(Order).where(Order.status.in_([
                    OrderStatus.INTENT_COMMITTED,
                    OrderStatus.SUBMITTED
                ]))
            )).scalars().all()

            if not inflight_orders:
                logger.info("[Recovery] No in-flight orders found. Clean state.")
                return {"reconciled": 0, "interrupted": 0, "total": 0}

            logger.warning(f"[Recovery] Found {len(inflight_orders)} in-flight order(s) pending reconciliation.")

            # Get open positions and pending orders from broker
            broker_positions = []
            broker_orders = []
            try:
                if hasattr(self, "broker_adapter") and self.broker_adapter:
                    broker_positions = await self.broker_adapter.get_positions()
                    if hasattr(self.broker_adapter, "get_orders"):
                        broker_orders = await self.broker_adapter.get_orders()
                elif hasattr(self, "mt5") and self.mt5:
                    broker_positions = await self.mt5.get_open_positions()
                    if hasattr(self.mt5, "get_orders"):
                        broker_orders = await self.mt5.get_orders()
            except Exception as e:
                logger.error(f"[Recovery] Failed to fetch broker positions/orders for in-flight reconciliation: {e}")

            for order in inflight_orders:
                matched_pos = None
                order_dir = (order.direction or "").lower()
                order_vol = float(order.requested_volume or 0.0)

                for bp in broker_positions:
                    bp_sym = bp.get("symbol", "")
                    bp_type = str(bp.get("type", "")).lower()
                    bp_vol = float(bp.get("volume", 0.0))

                    if bp_sym == order.symbol and bp_type == order_dir and abs(bp_vol - order_vol) < 0.001:
                        matched_pos = bp
                        break

                if matched_pos:
                    ticket = matched_pos.get("ticket")
                    fill_price = float(matched_pos.get("open_price", order.requested_price or 0.0))
                    logger.critical(
                        f"[Recovery] In-flight order {order.client_order_id} ({order.symbol}) "
                        f"MATCHED broker position ticket={ticket} price={fill_price}. Settling as FILLED."
                    )
                    await OrderStateMachine.transition_order_state(
                        session=session,
                        order=order,
                        new_status=OrderStatus.FILLED,
                        reason="Reconciled on restart: Found matching open position at broker",
                        details={"reconciled": True, "ticket": ticket, "price": fill_price},
                        executed_price=fill_price,
                        ticket=ticket,
                        filled_volume=order_vol,
                    )
                    # Persist corresponding Position in database if not already existing
                    existing_pos = None
                    try:
                        pos_res = await session.execute(
                            select(Position).where(Position.mt5_ticket == ticket)
                        )
                        existing_pos = pos_res.scalar_one_or_none() if hasattr(pos_res, "scalar_one_or_none") else None
                    except Exception:
                        pass

                    if not existing_pos:
                        pos = Position(
                            order_id=order.id,
                            analysis_id=order.analysis_id,
                            mt5_ticket=ticket,
                            symbol=order.symbol,
                            direction=order_dir,
                            volume=order_vol,
                            entry_price=fill_price,
                            sl=getattr(order, "sl", None),
                            tp=getattr(order, "tp", None),
                            opened_at=datetime.now(timezone.utc),
                            status="open",
                            is_paper=False,
                        )
                        session.add(pos)
                        try:
                            await session.flush()
                        except Exception:
                            pass
                        logger.info(f"[Recovery] Created and persisted Position record for ticket={ticket}, order={order.client_order_id}")

                    reconciled_count += 1
                    try:
                        notifier = AgentNotifier()
                        await notifier.send_critical(
                            f"⚠️ <b>IN-FLIGHT ORDER RECONCILED</b>\n"
                            f"Order <code>{order.client_order_id}</code> ({order.symbol} {order_dir.upper()} {order_vol} lots)\n"
                            f"terbukti sudah dieksekusi di broker (Ticket: <code>{ticket}</code> @ {fill_price}).\n"
                            f"Status order disinkronkan ke FILLED."
                        )
                    except Exception:
                        pass
                else:
                    # Check if found as pending order at broker (e.g. LIMIT/STOP order)
                    matched_pending = None
                    for bo in broker_orders:
                        bo_sym = bo.get("symbol", "")
                        bo_vol = float(bo.get("volume", 0.0) or bo.get("volume_initial", 0.0))
                        if bo_sym == order.symbol and abs(bo_vol - order_vol) < 0.001:
                            matched_pending = bo
                            break

                    if matched_pending:
                        pending_ticket = matched_pending.get("ticket")
                        logger.info(
                            f"[Recovery] In-flight order {order.client_order_id} ({order.symbol}) "
                            f"FOUND as pending order at broker (ticket={pending_ticket}). Retaining SUBMITTED status."
                        )
                        if pending_ticket and not getattr(order, "mt5_ticket", None):
                            order.mt5_ticket = pending_ticket
                        reconciled_count += 1
                    else:
                        logger.warning(
                            f"[Recovery] In-flight order {order.client_order_id} ({order.symbol}) "
                            f"NOT found at broker. Marking as INTERRUPTED (replay_policy='never')."
                        )
                        await OrderStateMachine.transition_order_state(
                            session=session,
                            order=order,
                            new_status=OrderStatus.INTERRUPTED,
                            reason=(
                                "Process crashed or restarted while order was in-flight. "
                                "Replay policy is 'never'. Order was NOT found at broker. Safely terminated."
                            ),
                            details={"reconciled": False, "replay_policy": order.replay_policy},
                        )
                        interrupted_count += 1
                        try:
                            notifier = AgentNotifier()
                            await notifier.send_critical(
                                f"🔍 <b>IN-FLIGHT ORDER INTERRUPTED</b>\n"
                                f"Order <code>{order.client_order_id}</code> ({order.symbol} {order_dir.upper()})\n"
                                f"berada dalam status in-flight saat crash/restart.\n"
                                f"Tidak ditemukan di broker. Diberi status INTERRUPTED (tidak di-re-execute)."
                            )
                        except Exception:
                            pass

            await session.commit()

        logger.info(
            f"[Recovery] In-flight reconciliation finished: "
            f"{reconciled_count} reconciled as filled, {interrupted_count} marked interrupted."
        )
        return {
            "reconciled": reconciled_count,
            "interrupted": interrupted_count,
            "total": len(inflight_orders)
        }


