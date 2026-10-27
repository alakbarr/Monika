# ==============================================================================
# File: execution/service/emergency_manager.py
# ==============================================================================

import asyncio
import json
import logging
import math
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.domain.risk.position_sizing import PositionSizer, SizingResult
from monika.domain.risk.risk_gate import RiskGate
from monika.infrastructure.brokers.broker_adapter import BrokerAdapter, MT5LiveAdapter
from monika.infrastructure.brokers.mt5_client import MT5Client


def get_session():
    import sys

    es = sys.modules.get("monika.application.execution.execution_service")
    fn = getattr(es, "get_session", None) if es else None
    if fn is not None:
        return fn()
    from monika.infrastructure.database.db import get_session as _real_get_session

    return _real_get_session()


def transactional_advisory_lock(*args, **kwargs):
    import sys

    es = sys.modules.get("monika.application.execution.execution_service")
    fn = getattr(es, "transactional_advisory_lock", None) if es else None
    if fn is not None:
        return fn(*args, **kwargs)
    from monika.infrastructure.database.db import transactional_advisory_lock as _real_lock

    return _real_lock(*args, **kwargs)


from monika.infrastructure.database.models import (
    ActivityLog,
    AssetAnalysis,
    Order,
    OrderEvent,
    OrderLog,
    OrderStatus,
    PaperTradeRecord,
    Position,
    RiskState,
    SystemConfig,
)
from monika.infrastructure.database.safe_ops import safe_commit
from monika.infrastructure.notifications.telegram_notifier import AgentNotifier


from monika.application.execution.service.base import _ExecutionServiceMixinBase

logger = logging.getLogger("TradingAgent.ExecutionService.EmergencyManager")


class EmergencyManagerMixin(_ExecutionServiceMixinBase):
    """Mixin untuk penutupan posisi darurat dan kill-switch proteksi modal."""

    def get_ticket_lock(self, ticket: int) -> asyncio.Lock:
        """Get or create canonical per-ticket mutex lock to synchronize order actions."""
        if not hasattr(self, "_ticket_locks"):
            self._ticket_locks = {}
        if len(self._ticket_locks) >= 500:
            unlocked = [t for t, lk in self._ticket_locks.items() if not lk.locked()]
            for t in unlocked[:250]:
                self._ticket_locks.pop(t, None)
        return self._ticket_locks.setdefault(ticket, asyncio.Lock())

    async def close_position_by_ticket(
        self,
        ticket: int,
        requested_by: str = "system",
        reason: str = "",
        volume: Optional[float] = None,
        lots: Optional[float] = None,
    ) -> dict:
        """Menutup posisi spesifik berdasarkan tiket MT5 (penuh atau sebagian)."""
        close_lots = volume if volume is not None else lots
        ticket_lock = self.get_ticket_lock(ticket)

        if ticket_lock.locked():
            logger.warning(
                f"Position {ticket} close already in progress, skipping duplicate request from {requested_by}"
            )
            return {"success": False, "error": f"Close already in progress for ticket {ticket}"}

        if not hasattr(self, "_closing_tickets"):
            self._closing_tickets = set()
        self._closing_tickets.add(ticket)

        try:
            async with ticket_lock:
                # Check DB state first — prevent redundant close if already closed
                async with get_session() as session:
                    db_pos = (
                        await session.execute(select(Position).where(Position.mt5_ticket == ticket))
                    ).scalar_one_or_none()
                    if db_pos and db_pos.status == "closed":
                        logger.info(f"Position {ticket} is already marked closed in DB.")
                        return {"success": True, "already_closed": True, "ticket": ticket}
                    if db_pos and getattr(db_pos, "is_paper", False):
                        return await self._close_paper_position(
                            session, db_pos, requested_by, reason, volume=close_lots
                        )

                logger.info(
                    f"Closing position {ticket} (requested_by={requested_by}, reason={reason}, volume={close_lots})"
                )
                try:
                    if hasattr(self, "broker_adapter") and self.broker_adapter:
                        result = await asyncio.wait_for(
                            self.broker_adapter.close_position(ticket=ticket, lots=close_lots),
                            timeout=15.0,
                        )
                        if result.get("profit") is None and result.get("pnl") is not None:
                            result["profit"] = result["pnl"]
                    else:
                        result = await asyncio.wait_for(
                            self.mt5.close_position(
                                ticket=ticket,
                                volume=close_lots,
                                lots=close_lots,
                                comment=f"Close:{requested_by}"[:31],
                            ),
                            timeout=15.0,
                        )
                except TimeoutError, asyncio.TimeoutError:
                    logger.critical(f"Liquidation timed out after 15.0s for ticket {ticket}")
                    result = {"success": False, "error": f"Liquidation timed out after 15.0s for ticket {ticket}"}

                async with get_session() as session:
                    # Update DB position record
                    db_pos = (
                        await session.execute(select(Position).where(Position.mt5_ticket == ticket))
                    ).scalar_one_or_none()

                    if db_pos and result.get("success"):
                        is_partial = False
                        if close_lots is not None and db_pos.volume and db_pos.volume > (float(close_lots) + 1e-4):
                            is_partial = True
                            db_pos.volume = round(float(db_pos.volume) - float(close_lots), 4)
                            db_pos.pnl = (db_pos.pnl or 0.0) + (result.get("profit") or 0.0)
                        else:
                            db_pos.status = "closed"
                            db_pos.closed_at = datetime.now(timezone.utc)
                            db_pos.pnl = (db_pos.pnl or 0.0) + (result.get("profit") or 0.0)

                        # Update risk state
                        if result.get("profit") is not None:
                            equity = await self._get_equity()
                            if asyncio.iscoroutine(equity):
                                equity = await equity
                            try:
                                equity = float(equity) if equity is not None else None
                            except TypeError, ValueError:
                                equity = None
                            if not equity or equity <= 0:
                                if self.dry_run:
                                    equity = float(
                                        self.settings.get("paper_trading", {}).get("initial_balance", 10000.0)
                                    )
                                else:
                                    equity = None
                            await self.gate.update_risk_state(
                                session=session,
                                pnl_delta=result["profit"],
                                equity=equity,
                            )

                        if db_pos.analysis_id and not is_partial:
                            try:
                                from monika.application.analysis.memory.outcome_linker import OutcomeLinker

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
                                    exit_reason=reason or "unknown",
                                    defer_reflection=True,
                                )
                            except Exception as e:
                                logger.debug(f"OutcomeLinker failed for real trade (non-fatal): {e}")

                    # Log to orders_log
                    session.add(
                        OrderLog(
                            action="close"
                            if not (close_lots and db_pos and db_pos.status != "closed")
                            else "partial_close",
                            symbol=db_pos.symbol if db_pos else "UNKNOWN",
                            params_json=json.dumps({"ticket": ticket, "reason": reason, "volume": close_lots}),
                            requested_by=requested_by,
                            approved_by="execution_service",
                            result=json.dumps(result),
                        )
                    )

                    # Log to activity_log
                    session.add(
                        ActivityLog(
                            category="trading",
                            description=(
                                f"Position {ticket} closed: profit={result.get('profit')} "
                                f"| reason={reason} | requested_by={requested_by} | volume={close_lots}"
                            ),
                            related_id=ticket,
                            actor="execution_service",
                        )
                    )
                    await session.commit()

                if result.get("success"):
                    logger.info(f"Position {ticket} closed: profit={result.get('profit')} volume={close_lots}")
                else:
                    logger.error(f"Close position {ticket} failed: {result.get('error')}")

                return result
        finally:
            self._closing_tickets.discard(ticket)

    async def _close_paper_position(
        self,
        session: AsyncSession,
        db_pos: Position,
        requested_by: str,
        reason: str,
        volume: Optional[float] = None,
    ) -> dict:
        """Paper positions have no real MT5 counterpart — close synthetically.
        Repairs PositionGuardian / TrailingStopManager / PositionExitReviewer
        which previously silently no-op'd against fake tickets. (P1-1)
        """
        from monika.infrastructure.database.models import PaperTradeRecord, PriceOHLCV

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
                        exit_price = (
                            getattr(tick, "bid", None) if db_pos.direction == "buy" else getattr(tick, "ask", None)
                        )
        except Exception as p_err:
            logger.debug(f"[EmergencyManager] Live price fetch failed for paper close: {p_err}")

        if not exit_price or exit_price <= 0:
            last_bar = (
                await session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == db_pos.symbol)
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            exit_price = last_bar.close if last_bar else db_pos.entry_price
        now = clock.now()
        is_partial = False
        if volume is not None and db_pos.volume and db_pos.volume > (float(volume) + 1e-4):
            is_partial = True
            db_pos.volume = round(float(db_pos.volume) - float(volume), 4)
        else:
            db_pos.status = "closed"
            db_pos.closed_at = now

        if db_pos.analysis_id and not is_partial:
            paper = (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.analysis_id == db_pos.analysis_id)
                    .where(PaperTradeRecord.status == "open")
                )
            ).scalar_one_or_none()
            if paper:
                move = (exit_price - paper.entry_price) if paper.entry_price else 0
                if paper.direction == "sell":
                    move = -move
                sl_dist = abs(paper.entry_price - paper.stop_loss) if (paper.entry_price and paper.stop_loss) else None
                paper.pnl_pct = round(move / sl_dist * (paper.risk_pct or 0.75), 4) if sl_dist else 0.0
                paper.status = "closed"
                paper.closed_at = now
                paper.exit_price = exit_price
                paper.exit_reason = f"manual_{requested_by}"[:100]
                paper.holding_hours = (now - paper.opened_at).total_seconds() / 3600 if paper.opened_at else 0.0
                try:
                    from monika.application.analysis.memory.outcome_linker import OutcomeLinker

                    if paper.analysis_id is not None:
                        await OutcomeLinker(self.settings).process_closed_position(
                            session,
                            analysis_id=int(paper.analysis_id),
                            pnl=paper.pnl_pct or 0.0,
                            holding_hours=paper.holding_hours or 0.0,
                            exit_reason=paper.exit_reason or "unknown",
                            defer_reflection=True,
                        )
                except Exception as e:
                    logger.debug(f"OutcomeLinker failed for paper manual-close: {e}")

        await session.commit()
        logger.info(f"[PAPER] Position {db_pos.id} ({db_pos.symbol}) closed via {requested_by}: {reason}")
        return {"success": True, "price": exit_price, "profit": None, "error": None}

    async def trigger_circuit_breaker(
        self, reason: str = "Circuit breaker triggered", cooldown_seconds: int = 300
    ) -> dict:
        """
        Mengaktifkan karantina trading otomatis saat circuit breaker (mis. FlashCrash) terpicu.
        Mempause trading baru tanpa menutup paksa posisi yang sudah memiliki SL/breakeven.
        """
        logger.critical(f"CIRCUIT BREAKER TRIGGERED: {reason} (cooldown: {cooldown_seconds}s)")
        async with get_session() as session:
            await self.gate.pause_trading(session, f"CIRCUIT BREAKER: {reason}")
            session.add(
                ActivityLog(
                    category="trading",
                    description=f"CIRCUIT BREAKER: {reason} (cooldown: {cooldown_seconds}s)",
                    actor="execution_service",
                )
            )
            await session.commit()

        try:
            from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

            await AgentNotifier().send_critical(
                f" <b>CIRCUIT BREAKER ACTIVATED</b>\n"
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
                session.add(
                    ActivityLog(
                        category="trading",
                        description=f"KILL SWITCH: {reason}",
                        actor="execution_service",
                    )
                )
                await session.commit()

            from sqlalchemy import select

            from monika.infrastructure.database.models import PaperTradeRecord, Position

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
                try:
                    if adapter and hasattr(adapter, "close_all_positions"):
                        result = await asyncio.wait_for(adapter.close_all_positions(comment="KillSwitch"), timeout=15.0)
                    elif hasattr(self, "mt5") and hasattr(self.mt5, "close_all_positions"):
                        result = await asyncio.wait_for(
                            self.mt5.close_all_positions(comment="KillSwitch"), timeout=15.0
                        )
                    else:
                        result = {"closed": 0, "failed": 0, "total": 0, "errors": []}
                except TimeoutError, asyncio.TimeoutError:
                    logger.critical("Broker terminal liquidation timed out after 15.0s!")
                    result = {"closed": 0, "failed": 1, "total": 1, "errors": ["Liquidation timed out after 15.0s"]}

                broker_closed = result.get("closed", 0)
                live_closed_count = max(live_closed_count, broker_closed)

                # 2. Sync broker state to DB & liquidate synthetic/paper positions
                async with get_session() as temp_session:
                    if hasattr(self, "mt5") and hasattr(self.mt5, "sync_positions_from_mt5"):
                        await self.mt5.sync_positions_from_mt5(temp_session)

                    # Close all open paper/dry-run positions in DB
                    open_db_positions = (
                        (await temp_session.execute(select(Position).where(Position.status == "open"))).scalars().all()
                    )

                    for pos in open_db_positions:
                        is_paper_pos = getattr(pos, "is_paper", False) or getattr(self, "dry_run", False)
                        if is_paper_pos or not pos.mt5_ticket:
                            close_res = await self._close_paper_position(
                                temp_session, pos, requested_by="kill_switch", reason=reason
                            )
                            if close_res and close_res.get("success"):
                                paper_closed_count += 1

                    # Check remaining live broker positions in DB
                    active_live_db = (
                        (
                            await temp_session.execute(
                                select(Position).where(Position.status == "open", Position.is_paper == False)
                            )
                        )
                        .scalars()
                        .all()
                    )

                if result.get("failed", 0) == 0 and not active_live_db:
                    break
                logger.warning(
                    f"Kill switch attempt {attempt + 1} failed or DB still has open positions. Retrying in 1s..."
                )
                await asyncio.sleep(1.0)

            # 3. Clean up any remaining orphaned PaperTradeRecord rows
            try:
                async with get_session() as paper_session:
                    from monika.infrastructure.database.models import PriceOHLCV

                    open_papers = (
                        (await paper_session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == "open")))
                        .scalars()
                        .all()
                    )

                    now = clock.now()
                    for paper in open_papers:
                        last_bar = (
                            await paper_session.execute(
                                select(PriceOHLCV)
                                .where(PriceOHLCV.symbol == paper.symbol)
                                .order_by(PriceOHLCV.timestamp.desc())
                                .limit(1)
                            )
                        ).scalar_one_or_none()

                        exit_price = last_bar.close if last_bar else paper.entry_price
                        if paper.entry_price and exit_price:
                            move = exit_price - paper.entry_price
                            if paper.direction == "sell":
                                move = -move
                            sl_dist = abs(paper.entry_price - paper.stop_loss) if paper.stop_loss else 1
                            pnl_pct = (move / sl_dist) * (paper.risk_pct or 0.75) if sl_dist > 0 else 0
                        else:
                            pnl_pct = 0.0
                            exit_price = paper.entry_price

                        paper.status = "closed"
                        paper.closed_at = now
                        paper.exit_price = exit_price
                        paper.exit_reason = "kill_switch"
                        paper.pnl_pct = round(pnl_pct, 4)
                        paper.holding_hours = (now - paper.opened_at).total_seconds() / 3600 if paper.opened_at else 0
                        paper_closed_count += 1

                    await paper_session.commit()
                    logger.info(f"Kill switch: closed {paper_closed_count} paper trades")
            except Exception as e:
                logger.error(f"Failed to close paper trades during kill switch (non-fatal): {e}")

            # 4. Aggregate metrics (live + paper)
            total_closed = live_closed_count + paper_closed_count
            failed_cnt = result.get("failed", 0)
            total_cnt = max(result.get("total", 0) + paper_closed_count, total_closed + failed_cnt)
            result["closed"] = total_closed
            result["failed"] = failed_cnt
            result["total"] = total_cnt
            result["paper_closed"] = paper_closed_count
            result["live_closed"] = live_closed_count

            # 5. Sync DB to reflect closures and de-arm kill_switch trigger flag
            async with get_session() as session:
                session.add(
                    ActivityLog(
                        category="trading",
                        description=(
                            f"Kill switch complete: closed={total_closed} (live={live_closed_count}, "
                            f"paper={paper_closed_count}), failed={failed_cnt}, total={total_cnt}"
                        ),
                        actor="execution_service",
                    )
                )

                session.add(
                    OrderLog(
                        action="kill_switch",
                        symbol="ALL",
                        params_json=json.dumps({"reason": reason}),
                        requested_by="system_or_user",
                        approved_by="execution_service",
                        result=json.dumps(result),
                    )
                )

                # De-arm SystemConfig kill_switch so restarted agent does not loop-trigger
                cfg_kill = (
                    await session.execute(select(SystemConfig).where(SystemConfig.key == "kill_switch"))
                ).scalar_one_or_none()
                if cfg_kill:
                    cfg_kill.value = "false"
                else:
                    session.add(SystemConfig(key="kill_switch", value="false"))

                # Lockout is maintained safely via manual_trading_paused
                cfg_pause = (
                    await session.execute(select(SystemConfig).where(SystemConfig.key == "manual_trading_paused"))
                ).scalar_one_or_none()
                pause_val = f"true:KILL SWITCH: {reason}"
                if cfg_pause:
                    cfg_pause.value = pause_val
                else:
                    session.add(SystemConfig(key="manual_trading_paused", value=pause_val))

                await safe_commit(session, label="kill_switch")

            # 6. Final verification - alert if any live agent positions remain on broker
            if result.get("total", 0) > 0 or result.get("failed", 0) > 0:
                await asyncio.sleep(2)
                if adapter and hasattr(adapter, "get_open_positions"):
                    remaining_positions = await adapter.get_open_positions()
                elif hasattr(self, "mt5") and hasattr(self.mt5, "get_open_positions"):
                    remaining_positions = await self.mt5.get_open_positions()
                else:
                    remaining_positions = []
                configured_magic = int(self.settings.get("trading", {}).get("mt5", {}).get("magic", 20250101))
                agent_positions = [p for p in remaining_positions if p.get("magic") == configured_magic]
                if agent_positions:
                    logger.critical(
                        f"Kill switch: {len(agent_positions)} positions STILL OPEN after {max_retries} retries!"
                    )
                    try:
                        from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

                        await AgentNotifier().send_critical(
                            f"[DARURAT] KILL SWITCH INCOMPLETE\n"
                            f"{len(agent_positions)} posisi masih terbuka!\n"
                            f"Tutup manual segera: {[p['ticket'] for p in agent_positions]}"
                        )
                    except Exception as notif_err:
                        logger.error(f"Failed to send kill switch incomplete alert: {notif_err}")

            logger.critical(f"Kill switch complete: {total_closed}/{total_cnt} positions closed")

            try:
                from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

                notifier = AgentNotifier()
                await notifier.send_critical(
                    f"[STOP] <b>KILL SWITCH COMPLETE</b>\n"
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

        # Ensure physical disk kill switch flag is removed
        from monika.core.paths import DATA_DIR

        disk_flag = DATA_DIR / "kill_switch.flag"
        if disk_flag.exists():
            try:
                disk_flag.unlink(missing_ok=True)
                logger.info(f"[ExecutionService] Removed disk kill switch flag: {disk_flag}")
            except Exception as flag_err:
                logger.error(f"[ExecutionService] Failed removing disk kill flag: {flag_err}")

        async def _do_resume(sess: AsyncSession):
            if hasattr(self, "gate") and self.gate is not None:
                await self.gate.resume_trading(sess)

            # Ensure all flags are cleared in SystemConfig
            for key in ("kill_switch", "manual_trading_paused", "trading_paused", "system_paused"):
                cfg = (await sess.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
                if cfg:
                    cfg.value = "false"

            sess.add(
                ActivityLog(
                    category="trading",
                    description=f"Trading resumed by {requested_by}: all pause & kill flags cleared, EffectGate reset.",
                    actor=requested_by,
                )
            )
            await safe_commit(sess, label="universal_resume_trading")

        if session is not None:
            await _do_resume(session)
        else:
            async with get_session() as new_session:
                await _do_resume(new_session)

        logger.info(f"[ExecutionService] Trading successfully resumed by {requested_by}.")
        return {"success": True, "message": f"Trading resumed by {requested_by}."}

    async def close_positions_batch(
        self,
        filter_type: str = "all",
        requested_by: str = "user_chat",
        reason: str = "Batch close positions",
        symbol: Optional[str] = None,
    ) -> dict:
        """
        Menutup posisi secara batch dengan filter ('all', 'profit_only', 'loss_only')
        dan opsi filter simbol spesifik.
        Berbeda dari kill_switch: TIDAK mem-pause trading daemon dan TIDAK memicu emergency lockout.
        """
        closed_tickets = []
        failed_tickets = []
        errors = []

        # 1. Ambil posisi live broker jika ada
        live_positions = []
        adapter = getattr(self, "broker_adapter", None)
        if adapter and hasattr(adapter, "get_open_positions"):
            live_positions = await adapter.get_open_positions()
        elif hasattr(self, "mt5") and hasattr(self.mt5, "get_open_positions"):
            live_positions = await self.mt5.get_open_positions()

        for pos in live_positions:
            raw_ticket = pos.get("ticket")
            if raw_ticket is None:
                continue
            ticket = int(raw_ticket)
            sym = pos.get("symbol")
            if symbol and sym and sym.strip().upper() != symbol.strip().upper():
                continue
            profit = float(pos.get("profit", 0.0) or 0.0)
            if filter_type == "profit_only" and profit <= 0:
                continue
            if filter_type == "loss_only" and profit >= 0:
                continue
            res = await self.close_position_by_ticket(ticket=ticket, requested_by=requested_by, reason=reason)
            if res.get("success"):
                closed_tickets.append(ticket)
            else:
                failed_tickets.append(ticket)
                if res.get("error"):
                    errors.append(f"Ticket {ticket}: {res['error']}")

        # 2. Ambil posisi paper DB jika ada
        async with get_session() as session:
            paper_query = select(Position).where(Position.status == "open")
            if symbol:
                paper_query = paper_query.where(Position.symbol == symbol.strip().upper())
            db_positions = (await session.execute(paper_query)).scalars().all()
            for db_pos in db_positions:
                if getattr(db_pos, "is_paper", False):
                    pnl = float(db_pos.pnl or 0.0)
                    if filter_type == "profit_only" and pnl <= 0:
                        continue
                    if filter_type == "loss_only" and pnl >= 0:
                        continue
                    res = await self._close_paper_position(session, db_pos, requested_by=requested_by, reason=reason)
                    if res.get("success"):
                        closed_tickets.append(f"paper_{db_pos.id}")
                    else:
                        failed_tickets.append(f"paper_{db_pos.id}")

        return {
            "success": len(failed_tickets) == 0,
            "filter": filter_type,
            "closed_count": len(closed_tickets),
            "failed_count": len(failed_tickets),
            "closed_tickets": closed_tickets,
            "failed_tickets": failed_tickets,
            "errors": errors,
        }
