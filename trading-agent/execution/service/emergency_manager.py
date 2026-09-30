# ==============================================================================
# File: execution/service/emergency_manager.py
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

logger = logging.getLogger("TradingAgent.ExecutionService.EmergencyManager")

class EmergencyManagerMixin(_ExecutionServiceMixinBase):
    """Mixin untuk penutupan posisi darurat dan kill-switch proteksi modal."""

    async def close_position_by_ticket(
        self,
        ticket: int,
        requested_by: str = "system",
        reason: str = "",
    ) -> dict:
        """Menutup posisi spesifik berdasarkan tiket MT5."""
        if not hasattr(self, "_ticket_locks"):
            self._ticket_locks = {}

        # M-2: LRU Eviction of unlocked ticket locks to prevent memory leak
        if len(self._ticket_locks) >= 500:
            unlocked = [t for t, lk in self._ticket_locks.items() if not lk.locked()]
            for t in unlocked[:250]:
                self._ticket_locks.pop(t, None)

        ticket_lock = self._ticket_locks.setdefault(ticket, asyncio.Lock())

        if ticket_lock.locked():
            logger.warning(f"Position {ticket} close already in progress, skipping duplicate request from {requested_by}")
            return {"success": False, "error": f"Close already in progress for ticket {ticket}"}

        async with ticket_lock:
            # Check DB state first — prevent redundant close if already closed
            async with get_session() as session:
                db_pos = (await session.execute(
                    select(Position).where(Position.mt5_ticket == ticket)
                )).scalar_one_or_none()
                if db_pos and db_pos.status == "closed":
                    logger.info(f"Position {ticket} is already marked closed in DB.")
                    return {"success": True, "already_closed": True, "ticket": ticket}
                if db_pos and getattr(db_pos, 'is_paper', False):
                    return await self._close_paper_position(session, db_pos, requested_by, reason)

            logger.info(f"Closing position {ticket} (requested_by={requested_by}, reason={reason})")
            if hasattr(self, 'broker_adapter') and self.broker_adapter:
                result = await self.broker_adapter.close_position(ticket=ticket)
                if result.get('profit') is None and result.get('pnl') is not None:
                    result['profit'] = result['pnl']
            else:
                result = await self.mt5.close_position(
                    ticket=ticket,
                    comment=f"Close:{requested_by}"[:31],
                )

            async with get_session() as session:
                # Update DB position record
                db_pos = (await session.execute(
                    select(Position).where(Position.mt5_ticket == ticket)
                )).scalar_one_or_none()

                if db_pos and result.get('success'):
                    db_pos.status = 'closed'
                    db_pos.closed_at = datetime.now(timezone.utc)
                    db_pos.pnl = result.get('profit')

                    # Update risk state
                    if result.get('profit') is not None:
                        equity = await self._get_equity()
                        if asyncio.iscoroutine(equity):
                            equity = await equity
                        try:
                            equity = float(equity) if equity is not None else None
                        except (TypeError, ValueError):
                            equity = None
                        if not equity or equity <= 0:
                            equity = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
                        await self.gate.update_risk_state(
                            session=session,
                            pnl_delta=result['profit'],
                            equity=equity,
                        )
                        
                    if db_pos.analysis_id:
                        try:
                            from analysis.memory.outcome_linker import OutcomeLinker
                            holding_hours = 0.0
                            c_dt = db_pos.closed_at
                            o_dt = db_pos.opened_at
                            if c_dt is not None and o_dt is not None:
                                c_time = c_dt if c_dt.tzinfo is not None else c_dt.replace(tzinfo=timezone.utc)
                                o_time = o_dt if o_dt.tzinfo is not None else o_dt.replace(tzinfo=timezone.utc)
                                holding_hours = max(0.0, (c_time - o_time).total_seconds() / 3600.0)
                            await OutcomeLinker().process_closed_position(
                                session,
                                analysis_id=int(db_pos.analysis_id),
                                pnl=db_pos.pnl or 0.0,
                                holding_hours=holding_hours,
                                exit_reason=reason or "unknown"
                            )
                        except Exception as e:
                            logger.debug(f'OutcomeLinker failed for real trade (non-fatal): {e}')

                # Log to orders_log
                session.add(OrderLog(
                    action='close',
                    symbol=db_pos.symbol if db_pos else 'UNKNOWN',
                    params_json=json.dumps({'ticket': ticket, 'reason': reason}),
                    requested_by=requested_by,
                    approved_by='execution_service',
                    result=json.dumps(result),
                ))

                # Log to activity_log
                session.add(ActivityLog(
                    category='trading',
                    description=(
                        f"Position {ticket} closed: profit={result.get('profit')} "
                        f"| reason={reason} | requested_by={requested_by}"
                    ),
                    related_id=ticket,
                    actor='execution_service',
                ))
                await session.commit()

            if result.get('success'):
                logger.info(f"Position {ticket} closed: profit={result.get('profit')}")
            else:
                logger.error(f"Close position {ticket} failed: {result.get('error')}")

            return result


    async def _close_paper_position(
        self, session: AsyncSession, db_pos: Position,
        requested_by: str, reason: str
    ) -> dict:
        """Paper positions have no real MT5 counterpart — close synthetically.
        Repairs PositionGuardian / TrailingStopManager / PositionExitReviewer
        which previously silently no-op'd against fake tickets. (P1-1)
        """
        from database.models import PriceOHLCV, PaperTradeRecord
        exit_price = None
        try:
            if hasattr(self, "_get_current_price"):
                p_raw, is_stale, _ = await self._get_current_price(db_pos.symbol, db_pos.direction or "buy")
                if p_raw and p_raw > 0 and not is_stale:
                    exit_price = p_raw
            elif hasattr(self, "mt5") and self.mt5 and hasattr(self.mt5, "get_current_price"):
                tick = await self.mt5.get_current_price(db_pos.symbol)
                if tick:
                    if isinstance(tick, dict):
                        exit_price = tick.get("bid") if db_pos.direction == "buy" else tick.get("ask")
                    else:
                        exit_price = getattr(tick, "bid", None) if db_pos.direction == "buy" else getattr(tick, "ask", None)
        except Exception as p_err:
            logger.debug(f"[EmergencyManager] Live price fetch failed for paper close: {p_err}")

        if not exit_price or exit_price <= 0:
            last_bar = (await session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == db_pos.symbol)
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()
            exit_price = last_bar.close if last_bar else db_pos.entry_price
        now = clock.now()
        db_pos.status = 'closed'
        db_pos.closed_at = now

        if db_pos.analysis_id:
            paper = (await session.execute(
                select(PaperTradeRecord)
                .where(PaperTradeRecord.analysis_id == db_pos.analysis_id)
                .where(PaperTradeRecord.status == 'open')
            )).scalar_one_or_none()
            if paper:
                move = (exit_price - paper.entry_price) if paper.entry_price else 0
                if paper.direction == 'sell':
                    move = -move
                sl_dist = abs(paper.entry_price - paper.stop_loss) if (paper.entry_price and paper.stop_loss) else None
                paper.pnl_pct = round(move / sl_dist * (paper.risk_pct or 0.75), 4) if sl_dist else 0.0
                paper.status = 'closed'
                paper.closed_at = now
                paper.exit_price = exit_price
                paper.exit_reason = f'manual_{requested_by}'[:100]
                paper.holding_hours = (now - paper.opened_at).total_seconds() / 3600 if paper.opened_at else 0.0
                try:
                    from analysis.memory.outcome_linker import OutcomeLinker
                    if paper.analysis_id is not None:
                        await OutcomeLinker(self.settings).process_closed_position(
                            session, analysis_id=int(paper.analysis_id), pnl=paper.pnl_pct or 0.0,
                            holding_hours=paper.holding_hours or 0.0, exit_reason=paper.exit_reason or "unknown")
                except Exception as e:
                    logger.debug(f'OutcomeLinker failed for paper manual-close: {e}')

        await session.commit()
        logger.info(f'[PAPER] Position {db_pos.id} ({db_pos.symbol}) closed via {requested_by}: {reason}')
        return {'success': True, 'price': exit_price, 'profit': None, 'error': None}


    async def trigger_circuit_breaker(self, reason: str = "Circuit breaker triggered", cooldown_seconds: int = 300) -> dict:
        """
        Mengaktifkan karantina trading otomatis saat circuit breaker (mis. FlashCrash) terpicu.
        Mempause trading baru tanpa menutup paksa posisi yang sudah memiliki SL/breakeven.
        """
        logger.critical(f"CIRCUIT BREAKER TRIGGERED: {reason} (cooldown: {cooldown_seconds}s)")
        async with get_session() as session:
            await self.gate.pause_trading(session, f"CIRCUIT BREAKER: {reason}")
            session.add(ActivityLog(
                category='trading',
                description=f"CIRCUIT BREAKER: {reason} (cooldown: {cooldown_seconds}s)",
                actor='execution_service',
            ))
            await session.commit()

        try:
            from utils.infra.notifier import AgentNotifier
            await AgentNotifier().send_critical(
                f"⚡ <b>CIRCUIT BREAKER ACTIVATED</b>\n"
                f"<b>Reason:</b> {reason}\n"
                f"<b>Cooldown:</b> {cooldown_seconds}s\n"
                f"Trading proposals paused."
            )
        except Exception as notif_err:
            logger.debug(f"Circuit breaker notification failed: {notif_err}")

        return {"success": True, "action": "paused", "reason": reason, "cooldown": cooldown_seconds}

    async def kill_switch(self, reason: str = "Manual kill switch activated") -> dict:
        """
        DARURAT: Tutup SEMUA posisi terbuka segera (baik MT5 live maupun DB paper/synthetic).
        Beroperasi independen dari pipeline analisis.
        """
        import asyncio
        if not hasattr(self, "_kill_lock"):
            self._kill_lock = asyncio.Lock()

        async with self._kill_lock:
            logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
            if hasattr(self, "effect_gate") and self.effect_gate is not None:
                self.effect_gate.request_abort(f"Kill switch activated: {reason}")

            # First, pause all new trading
            async with get_session() as session:
                await self.gate.pause_trading(session, f"KILL SWITCH: {reason}")
                session.add(ActivityLog(
                    category='trading',
                    description=f"KILL SWITCH: {reason}",
                    actor='execution_service',
                ))
                await session.commit()

            from database.models import Position, PaperTradeRecord
            from sqlalchemy import select

            max_retries = 3
            result: Dict[str, Any] = {"closed": 0, "failed": 0, "total": 0, "errors": []}
            adapter = getattr(self, "broker_adapter", None)
            paper_closed_count = 0
            live_closed_count = 0

            # 0. CANCEL-BEFORE-FLATTEN INVARIANT:
            # Quiesce the orderbook by canceling all pending/resting orders FIRST.
            # Prevents resting limit/stop orders from getting filled post-liquidation.
            logger.info("Executing Cancel-Before-Flatten: canceling all resting pending orders...")
            if hasattr(self, "mt5") and hasattr(self.mt5, "cancel_all_pending_orders"):
                try:
                    cancel_res = await self.mt5.cancel_all_pending_orders()
                    logger.info(f"Cancel-Before-Flatten result: {cancel_res}")
                except Exception as ce:
                    logger.error(f"Error canceling pending orders during kill switch: {ce}")

            for attempt in range(max_retries):
                # 1. Broker terminal liquidation
                if adapter and hasattr(adapter, "close_all_positions"):
                    result = await adapter.close_all_positions(comment="KillSwitch")
                elif hasattr(self, "mt5") and hasattr(self.mt5, "close_all_positions"):
                    result = await self.mt5.close_all_positions(comment="KillSwitch")
                else:
                    result = {"closed": 0, "failed": 0, "total": 0, "errors": []}

                broker_closed = result.get('closed', 0)
                live_closed_count = max(live_closed_count, broker_closed)

                # 2. Sync broker state to DB & liquidate synthetic/paper positions
                async with get_session() as temp_session:
                    if hasattr(self, "mt5") and hasattr(self.mt5, "sync_positions_from_mt5"):
                        await self.mt5.sync_positions_from_mt5(temp_session)

                    # Close all open paper/dry-run positions in DB
                    open_db_positions = (await temp_session.execute(
                        select(Position).where(Position.status == 'open')
                    )).scalars().all()

                    for pos in open_db_positions:
                        is_paper_pos = getattr(pos, 'is_paper', False) or getattr(self, 'dry_run', False)
                        if is_paper_pos or not pos.mt5_ticket:
                            close_res = await self._close_paper_position(
                                temp_session, pos, requested_by="kill_switch", reason=reason
                            )
                            if close_res and close_res.get('success'):
                                paper_closed_count += 1

                    # Check remaining live broker positions in DB
                    active_live_db = (await temp_session.execute(
                        select(Position).where(Position.status == 'open', Position.is_paper == False)
                    )).scalars().all()

                if result.get('failed', 0) == 0 and not active_live_db:
                    break
                logger.warning(f"Kill switch attempt {attempt+1} failed or DB still has open positions. Retrying in 1s...")
                await asyncio.sleep(1.0)

            # 3. Clean up any remaining orphaned PaperTradeRecord rows
            try:
                async with get_session() as paper_session:
                    from database.models import PriceOHLCV
                    open_papers = (await paper_session.execute(
                        select(PaperTradeRecord).where(PaperTradeRecord.status == 'open')
                    )).scalars().all()

                    now = clock.now()
                    for paper in open_papers:
                        last_bar = (await paper_session.execute(
                            select(PriceOHLCV)
                            .where(PriceOHLCV.symbol == paper.symbol)
                            .order_by(PriceOHLCV.timestamp.desc())
                            .limit(1)
                        )).scalar_one_or_none()

                        exit_price = last_bar.close if last_bar else paper.entry_price
                        if paper.entry_price and exit_price:
                            move = exit_price - paper.entry_price
                            if paper.direction == 'sell':
                                move = -move
                            sl_dist = abs(paper.entry_price - paper.stop_loss) if paper.stop_loss else 1
                            pnl_pct = (move / sl_dist) * (paper.risk_pct or 0.75) if sl_dist > 0 else 0
                        else:
                            pnl_pct = 0.0
                            exit_price = paper.entry_price

                        paper.status = 'closed'
                        paper.closed_at = now
                        paper.exit_price = exit_price
                        paper.exit_reason = 'kill_switch'
                        paper.pnl_pct = round(pnl_pct, 4)
                        paper.holding_hours = (now - paper.opened_at).total_seconds() / 3600 if paper.opened_at else 0
                        paper_closed_count += 1

                    await paper_session.commit()
                    logger.info(f'Kill switch: closed {paper_closed_count} paper trades')
            except Exception as e:
                logger.error(f'Failed to close paper trades during kill switch (non-fatal): {e}')

            # 4. Aggregate metrics (live + paper)
            total_closed = live_closed_count + paper_closed_count
            failed_cnt = result.get('failed', 0)
            total_cnt = max(result.get('total', 0) + paper_closed_count, total_closed + failed_cnt)
            result['closed'] = total_closed
            result['failed'] = failed_cnt
            result['total'] = total_cnt
            result['paper_closed'] = paper_closed_count
            result['live_closed'] = live_closed_count

            # 5. Sync DB to reflect closures and de-arm kill_switch trigger flag
            async with get_session() as session:
                session.add(ActivityLog(
                    category='trading',
                    description=(
                        f"Kill switch complete: closed={total_closed} (live={live_closed_count}, "
                        f"paper={paper_closed_count}), failed={failed_cnt}, total={total_cnt}"
                    ),
                    actor='execution_service',
                ))

                session.add(OrderLog(
                    action='kill_switch',
                    symbol='ALL',
                    params_json=json.dumps({'reason': reason}),
                    requested_by='system_or_user',
                    approved_by='execution_service',
                    result=json.dumps(result),
                ))

                # De-arm SystemConfig kill_switch so restarted agent does not loop-trigger
                cfg_kill = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == "kill_switch")
                )).scalar_one_or_none()
                if cfg_kill:
                    cfg_kill.value = "false"
                else:
                    session.add(SystemConfig(key="kill_switch", value="false"))

                # Lockout is maintained safely via manual_trading_paused
                cfg_pause = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == "manual_trading_paused")
                )).scalar_one_or_none()
                pause_val = f"true:KILL SWITCH: {reason}"
                if cfg_pause:
                    cfg_pause.value = pause_val
                else:
                    session.add(SystemConfig(key="manual_trading_paused", value=pause_val))

                await safe_commit(session, label="kill_switch")

            # 6. Final verification - alert if any live agent positions remain on broker
            if result.get('total', 0) > 0 or result.get('failed', 0) > 0:
                await asyncio.sleep(2)
                if adapter and hasattr(adapter, "get_open_positions"):
                    remaining_positions = await adapter.get_open_positions()
                elif hasattr(self, "mt5") and hasattr(self.mt5, "get_open_positions"):
                    remaining_positions = await self.mt5.get_open_positions()
                else:
                    remaining_positions = []
                agent_positions = [p for p in remaining_positions if p.get('magic') == 20250101]
                if agent_positions:
                    logger.critical(f"Kill switch: {len(agent_positions)} positions STILL OPEN after {max_retries} retries!")
                    try:
                        from utils.infra.notifier import AgentNotifier
                        await AgentNotifier().send_critical(
                            f"🚨 KILL SWITCH INCOMPLETE\n"
                            f"{len(agent_positions)} posisi masih terbuka!\n"
                            f"Tutup manual segera: {[p['ticket'] for p in agent_positions]}"
                        )
                    except Exception as notif_err:
                        logger.error(f"Failed to send kill switch incomplete alert: {notif_err}")

            logger.critical(
                f"Kill switch complete: {total_closed}/{total_cnt} positions closed"
            )

            try:
                from utils.infra.notifier import AgentNotifier
                notifier = AgentNotifier()
                await notifier.send_critical(
                    f"🛑 <b>KILL SWITCH COMPLETE</b>\n"
                    f"Closed: {total_closed}/{total_cnt} (live={live_closed_count}, paper={paper_closed_count})\n"
                    f"Reason: {reason}"
                )
            except Exception as e:
                logger.error(f"Failed to notify kill switch completion: {e}")

            return result

    async def resume_trading(self, session: Optional[AsyncSession] = None, requested_by: str = "operator") -> dict:
        """
        Universal resume handler:
        - Resets EffectGate to ACTIVE
        - Unpauses RiskGate (trading_paused = False)
        - Clears SystemConfig pause & kill_switch flags
        - Clears suspended symbols in PaperTracker
        - Logs audit trail
        """
        if hasattr(self, "effect_gate") and self.effect_gate is not None:
            self.effect_gate.reset()

        async def _do_resume(sess: AsyncSession):
            if hasattr(self, "gate") and self.gate is not None:
                await self.gate.resume_trading(sess)

            # Ensure all flags are cleared in SystemConfig
            for key in ("kill_switch", "manual_trading_paused", "trading_paused", "system_paused"):
                cfg = (await sess.execute(
                    select(SystemConfig).where(SystemConfig.key == key)
                )).scalar_one_or_none()
                if cfg:
                    cfg.value = "false"

            sess.add(ActivityLog(
                category="trading",
                description=f"Trading resumed by {requested_by}: all pause & kill flags cleared, EffectGate reset.",
                actor=requested_by,
            ))
            await safe_commit(sess, label="universal_resume_trading")

        if session is not None:
            await _do_resume(session)
        else:
            async with get_session() as new_session:
                await _do_resume(new_session)

        logger.info(f"[ExecutionService] Trading successfully resumed by {requested_by}.")
        return {"success": True, "message": f"Trading resumed by {requested_by}."}


