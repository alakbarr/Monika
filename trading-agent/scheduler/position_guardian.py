# ==============================================================================
# File: scheduler/position_guardian.py
# ==============================================================================

"""
Position Guardian: Proteksi posisi terbuka saat rilis berita penting.

Opsi perlindungan (diatur di settings.yaml):
1. WIDEN_SL: Perlebar Stop Loss sementara untuk hindari slippage.
2. CLOSE_POSITION: Tutup posisi sebelum berita rilis.
3. ALERT_ONLY: Kirim notifikasi Telegram untuk intervensi manual.
"""
import asyncio
import logging
from typing import Any, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.db import get_session
from database.models import Position, EconomicCalendar, ActivityLog
import utils.clock as clock

logger = logging.getLogger("TradingAgent.PositionGuardian")

# Mata uang yang terkait dengan setiap instrumen (untuk pencocokan event kalender)
SYMBOL_CURRENCIES = {
    "XAUUSD": ["USD", "XAU"],
    "EURUSD": ["USD", "EUR"],
    "GBPUSD": ["USD", "GBP"],
    "USDJPY": ["USD", "JPY"],
    "AUDUSD": ["USD", "AUD"],
    "XTIUSD": ["USD", "OIL"],
    "BTCUSD": ["USD", "BTC"],
}


class PositionGuardian:
    """
    Memeriksa kalender ekonomi untuk event high-impact dan melindungi posisi.
    """

    def __init__(self, settings: dict, execution_service=None):
        self.settings = settings
        self.execution_service = execution_service
        guardian_cfg = settings.get("trading", {}).get("position_guardian", {})
        self.enabled = guardian_cfg.get("enabled", True)
        # Options: "alert_only", "close_before_news"
        self.strategy = guardian_cfg.get("strategy", "alert_only")
        # Minutes before news to take action
        self.warning_minutes = guardian_cfg.get("warning_minutes", 30)
        # Only act on events with impact level in this list
        self.impact_levels = guardian_cfg.get("impact_levels", ["high"])
        self._alerted_position_events: set[tuple[Any, Any]] = set()
        self._kill_switch_triggered: bool = False

    async def check_and_protect(self, emergency: bool = False) -> dict:
        """
        Cek kalender dan eksekusi proteksi posisi terbuka.
        Dipanggil rutin dari loop news_watcher.
        """
        if not self.enabled:
            return {"checked": True, "action_taken": False}

        now = clock.now()
        warning_window = now + timedelta(minutes=self.warning_minutes)

        async with get_session() as session:
            # Check DB emergency kill switch flag (from CLI/Web)
            from database.models import SystemConfig
            cfg_kill = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == "kill_switch")
            )).scalar_one_or_none()
            kill_active = bool(cfg_kill and str(cfg_kill.value).lower() in ("true", "1", "yes"))
            if kill_active:
                if not self._kill_switch_triggered:
                    self._kill_switch_triggered = True
                    logger.critical("[PositionGuardian] Emergency kill switch is ACTIVE in SystemConfig! Liquidating all positions.")
                    if self.execution_service:
                        await self.execution_service.kill_switch("Database emergency kill switch triggered")
                return {"checked": True, "action_taken": True, "kill_switch_active": True}
            else:
                self._kill_switch_triggered = False

            # Get open and orphan_pending_close positions
            all_active_positions = (await session.execute(
                select(Position).where(Position.status.in_(["open", "orphan_pending_close"]))
            )).scalars().all()

            if not all_active_positions:
                return {"checked": True, "action_taken": False, "positions_checked": 0}

            # Retry any emergency orphan positions
            for pos in all_active_positions:
                if pos.status == "orphan_pending_close" and pos.mt5_ticket:
                    logger.warning(f"Retrying close for orphan position {pos.symbol} ticket={pos.mt5_ticket}")
                    if self.execution_service:
                        res = await self.execution_service.close_position_by_ticket(
                            pos.mt5_ticket,
                            requested_by="position_guardian",
                            reason="Emergency orphan retry close",
                        )
                        if res and res.get("success"):
                            pos.status = "closed"
                            pos.closed_at = clock.now()
                            await session.commit()

            open_positions = [p for p in all_active_positions if p.status == "open"]

            # Orphan check: if one leg of a pair is closed, close the other
            paired_positions = [p for p in open_positions if p.pair_group_id]
            pair_groups = {}
            for p in paired_positions:
                pair_groups.setdefault(p.pair_group_id, []).append(p)

            for group_id, legs in pair_groups.items():
                if group_id and group_id.startswith("tranche_"):
                    await self._handle_tranche_scale_out(session, group_id, legs)
                    continue

                if len(legs) == 1:
                    # Only one leg open — other was closed (by SL/TP hit on MT5)
                    orphan = legs[0]
                    logger.warning(f"Orphan paired leg detected: {orphan.symbol} "
                                 f"ticket={orphan.mt5_ticket} [group={group_id[:8]}]")
                    await self._close_paired_orphan(session, orphan)

            # Get upcoming high-impact events
            upcoming_events = (await session.execute(
                select(EconomicCalendar)
                .where(EconomicCalendar.impact.in_(self.impact_levels))
                .where(EconomicCalendar.event_time >= now - timedelta(minutes=5))
                .where(EconomicCalendar.event_time <= warning_window)
            )).scalars().all()

            actions_taken = []
            
            if upcoming_events:
                # Check which positions are exposed to upcoming events
                for pos in open_positions:
                    if pos.pair_group_id:
                        continue  # Paired positions managed by orphan check above

                    pos_currencies = SYMBOL_CURRENCIES.get(pos.symbol, ["USD"])
                    for event in upcoming_events:
                        if event.event_time is not None and event.currency in pos_currencies:
                            minutes_to_event = (event.event_time - now).total_seconds() / 60
                            action = await self._protect_position(
                                session, pos, event, minutes_to_event
                            )
                            if action:
                                actions_taken.append(action)
                            break  # One action per position

            return {
                "checked": True,
                "action_taken": len(actions_taken) > 0,
                "actions": actions_taken,
                "upcoming_events": [
                    {
                        "event": e.event_name,
                        "currency": e.currency,
                        "time": e.event_time.strftime("%H:%M UTC") if e.event_time else "?"
                    }
                    for e in upcoming_events
                ]
            }

    async def _close_paired_orphan(self, session: AsyncSession, orphan: Position):
        """Close the remaining leg of a stat-arb pair."""
        try:
            if self.execution_service and orphan.mt5_ticket:
                await self.execution_service.close_position_by_ticket(
                    orphan.mt5_ticket,
                    requested_by="position_guardian",
                    reason=f"Paired leg closed (orphan cleanup)"
                )
        except Exception as e:
            logger.error(f"Failed to close paired orphan {orphan.symbol}: {e}")

    async def _handle_tranche_scale_out(
        self,
        session: AsyncSession,
        group_id: str,
        open_legs: list[Position],
    ) -> None:
        """
        Manages scale-out lifecycle for multi-leg tranche orders:
        When Leg 1 hits TP and closes, automatically move Leg 2's Stop Loss
        to Breakeven (entry_price) to secure risk-free runner status,
        and enable trailing ATR protection.
        """
        if len(open_legs) != 1:
            # Either both still open (waiting for TP1), or both closed
            return

        runner_leg = open_legs[0]
        if not runner_leg.entry_price:
            return

        # Check if the other tranche leg is already closed
        closed_legs = (await session.execute(
            select(Position)
            .where(Position.pair_group_id == group_id)
            .where(Position.status == "closed")
        )).scalars().all()

        if not closed_legs:
            return

        # Closed leg exists -> Leg 1 closed at TP. Move Leg 2 SL to Breakeven
        be_price = runner_leg.entry_price
        current_sl = runner_leg.sl
        is_buy = (runner_leg.direction or "").lower() == "buy"

        # Check if SL is already at or past breakeven
        is_at_be = False
        if current_sl is not None:
            if is_buy and current_sl >= be_price:
                is_at_be = True
            elif not is_buy and current_sl <= be_price:
                is_at_be = True

        if not is_at_be and self.execution_service and runner_leg.mt5_ticket:
            logger.info(
                f"[PositionGuardian] Tranche scale-out: Leg 1 closed for {runner_leg.symbol}. "
                f"Moving Leg 2 (ticket={runner_leg.mt5_ticket}) SL to Breakeven {be_price}."
            )
            try:
                res = await self.execution_service.modify_position_sl_tp(
                    ticket=runner_leg.mt5_ticket,
                    sl=be_price,
                    requested_by="position_guardian_tranche_scaleout",
                )
                if res and res.get("success"):
                    runner_leg.sl = be_price
                    session.add(ActivityLog(
                        category="risk",
                        description=(
                            f"PositionGuardian tranche scale-out: Leg 1 closed. "
                            f"Leg 2 {runner_leg.symbol} (ticket={runner_leg.mt5_ticket}) SL moved to BE {be_price}."
                        ),
                        actor="position_guardian",
                    ))
                    await session.commit()

                    try:
                        from utils.infra.notifier import AgentNotifier
                        await AgentNotifier().send_info(
                            f"🎯 <b>Tranche Scale-Out: Leg 1 Closed</b>\n"
                            f"Symbol: <b>{runner_leg.symbol}</b> | Ticket: <code>{runner_leg.mt5_ticket}</code>\n"
                            f"SL moved to Breakeven: <code>{be_price}</code>\n"
                            f"Leg 2 runner running risk-free with Trailing ATR active."
                        )
                    except Exception as notif_err:
                        logger.debug(f"Scale-out notification error: {notif_err}")
            except Exception as mod_err:
                logger.error(f"[PositionGuardian] Failed to move Leg 2 to BE: {mod_err}")


    async def _protect_position(
        self,
        session: AsyncSession,
        position: Position,
        event: EconomicCalendar,
        minutes_to_event: float,
    ) -> dict:
        """Mengeksekusi tindakan proteksi pada posisi terkait."""

        msg = (
            f"⚠️ <b>News Alert — Open Position</b>\n\n"
            f"Position: {position.symbol} {position.direction.upper()} "
            f"{position.volume}L @ {position.entry_price}\n"
            f"SL: {position.sl} | TP: {position.tp}\n\n"
            f"Upcoming: <b>{event.event_name}</b> ({event.currency})\n"
            f"Time: {event.event_time.strftime('%H:%M UTC') if event.event_time else '?'} "
            f"(~{minutes_to_event:.0f} min)\n"
            f"Impact: {event.impact.upper()}\n\n"
        )

        event_key = (position.mt5_ticket or position.id, event.id or event.event_name)
        if event_key in self._alerted_position_events:
            return {
                "symbol": position.symbol,
                "ticket": position.mt5_ticket,
                "action": "already_acted",
                "event": event.event_name,
                "minutes_to_event": minutes_to_event,
            }
        self._alerted_position_events.add(event_key)

        if self.strategy == "close_before_news":
            msg += f"Action: <b>AUTO-CLOSING position before news.</b>"
            logger.warning(
                f"PositionGuardian: closing {position.symbol} ticket={position.mt5_ticket} "
                f"before {event.event_name}"
            )
            if self.execution_service and position.mt5_ticket:
                try:
                    await self.execution_service.close_position_by_ticket(
                        position.mt5_ticket,
                        requested_by="position_guardian",
                        reason=f"Pre-news close: {event.event_name}"
                    )
                    action_type = "closed"
                except Exception as e:
                    logger.error(f"Pre-news close failed: {e}")
                    action_type = "close_failed"
            else:
                action_type = "no_execution_service"
        else:  # alert_only
            msg += (
                f"Action: <b>ALERT ONLY</b> — Manual action recommended.\n"
                f"Consider closing or widening SL before news."
            )
            action_type = "alerted"

        try:
            from utils.infra.notifier import AgentNotifier
            await AgentNotifier().send_warning(msg)
        except Exception as e:
            logger.warning(f"Position guardian alert failed: {e}")

        # Log to activity_log
        session.add(ActivityLog(
            category="risk",
            description=(
                f"PositionGuardian: {action_type} {position.symbol} ticket={position.mt5_ticket} "
                f"before {event.event_name} ({minutes_to_event:.0f}min)"
            ),
            actor="position_guardian",
        ))
        try:
            from database.event_store import TradingEventStore
            await TradingEventStore.emit(
                session=session,
                event_type="position.protected",
                payload={
                    "symbol": position.symbol,
                    "ticket": position.mt5_ticket,
                    "action": action_type,
                    "event": event.event_name,
                    "minutes_to_event": minutes_to_event,
                },
                correlation_id=f"pos_{position.mt5_ticket or position.id}",
                actor="position_guardian",
            )
        except Exception:
            pass
        await session.commit()

        return {
            "symbol": position.symbol,
            "ticket": position.mt5_ticket,
            "action": action_type,
            "event": event.event_name,
            "minutes_to_event": minutes_to_event,
        }

    async def check_friday_close_protection(self) -> dict:
        """
        Executed between 20:00-21:30 UTC every Friday.
        Ensures all non-exempt positions trigger notifications or are automatically liquidated.
        
        Evaluates auto_close_friday_positions configuration: if True, positions at risk
        are automatically liquidated (rather than alert-only). Defaults to False for safety.
        """
        now = clock.now()
        weekday = now.weekday()
        hour = now.hour
        
        # Hanya aktif Jumat 20:00-21:30 UTC
        if not (weekday == 4 and 20 <= hour <= 21):
            return {"skipped": True}
        
        weekend_cfg = self.settings.get("trading", {}).get("weekend_management", {})
        # Baca setting strategy atau boolean legacy auto_close_friday_positions
        strategy = weekend_cfg.get("strategy", "alert_only")
        auto_close_enabled = weekend_cfg.get("auto_close_friday_positions", False) or (strategy in ("close_positions", "close_if_profitable"))
        
        async with get_session() as session:
            open_positions = (await session.execute(
                select(Position).where(Position.status == "open")
            )).scalars().all()
            
            exempted = set(weekend_cfg.get("exempted_symbols", ["BTCUSD", "ETHUSD"]))
            at_risk = [p for p in open_positions if p.symbol not in exempted]
            
            if not at_risk:
                return {"positions_at_risk": 0}
            
            closed_count = 0
            close_errors = []
            
            if auto_close_enabled:
                # AUTO-CLOSE MODE: Tutup posisi at-risk sesuai strategi
                logger.warning(
                    f'[PositionGuardian] Friday auto-close AKTIF (strategi={strategy}): mengevaluasi {len(at_risk)} posisi '
                    f'sebelum weekend gap risk (21:00 UTC).'
                )
                for p in at_risk:
                    pnl_val = getattr(p, "unrealized_pnl", None)
                    pnl = float(pnl_val if pnl_val is not None else (getattr(p, "pnl", 0.0) or 0.0))
                    if strategy == "close_if_profitable" and pnl <= 0:
                        logger.info(f"[PositionGuardian] Skipping {p.symbol} ticket={p.mt5_ticket} (Friday close_if_profitable: PnL={pnl:.2f} <= 0)")
                        continue
                    try:
                        if self.execution_service and p.mt5_ticket:
                            await self.execution_service.close_position_by_ticket(
                                p.mt5_ticket,
                                requested_by="position_guardian_friday",
                                reason=f"Friday auto-close ({strategy}): weekend gap protection"
                            )
                            closed_count += 1
                            logger.info(f'[PositionGuardian] Closed {p.symbol} ticket={p.mt5_ticket} (Friday auto-close, pnl={pnl:.2f})')
                        else:
                            close_errors.append(f"{p.symbol}: no execution_service or ticket")
                    except Exception as e:
                        close_errors.append(f"{p.symbol}: {e}")
                        logger.error(f'[PositionGuardian] Friday auto-close failed for {p.symbol}: {e}')
                
                # Log ke ActivityLog
                session.add(ActivityLog(
                    category="risk",
                    description=(
                        f"PositionGuardian Friday auto-close: "
                        f"closed={closed_count}, errors={len(close_errors)} "
                        f"symbols={[p.symbol for p in at_risk]}"
                    ),
                    actor="position_guardian",
                ))
                await session.commit()
                
                # Notifikasi hasil
                lines = [f"🌙 <b>Friday Auto-Close Selesai</b>\n"]
                lines.append(f"Posisi ditutup: <b>{closed_count}/{len(at_risk)}</b>")
                if close_errors:
                    lines.append(f"\n⚠️ Gagal: {', '.join(close_errors[:3])}")
                lines.append("\nSemua posisi at-risk telah diamankan dari weekend gap.")
                
                try:
                    from utils.infra.notifier import AgentNotifier
                    await AgentNotifier().send_info("\n".join(lines))
                except Exception as e:
                    logger.error(f"Friday auto-close notification failed: {e}")
                
                return {
                    "positions_at_risk": len(at_risk),
                    "auto_closed": closed_count,
                    "close_errors": close_errors,
                }
            
            else:
                # ALERT-ONLY MODE (default): Kirim alert kritis
                lines = ["🌙 <b>CRITICAL: Market closing in <60 minutes</b>\n"]
                lines.append("Open positions at weekend gap risk:")
                for p in at_risk:
                    lines.append(f"• {p.symbol} {p.direction.upper()} {p.volume}L @ {p.entry_price} | SL:{p.sl}")
                lines.append(
                    f"\nAction required before 21:00 UTC Friday. "
                    f"Use /close <ticket> if needed.\n"
                    f"<i>Tip: Set weekend_management.auto_close_friday_positions: true "
                    f"in settings.yaml to auto-close next time.</i>"
                )
                
                try:
                    from utils.infra.notifier import AgentNotifier
                    await AgentNotifier().send_critical("\n".join(lines))
                except Exception as e:
                    logger.error(f"Friday close alert failed: {e}")
                
                return {"positions_alerted": len(at_risk)}

    async def on_tick(self, event: Any) -> None:
        """
        EventBus subscriber handler for TickPriceEvent.
        Provides sub-second event-driven position health and risk boundary surveillance.
        """
        if not self.enabled:
            return

        symbol = getattr(event, "symbol", "")
        if not symbol:
            return

        sym_clean = symbol.strip().upper().replace("/", "")

        # Throttle checks per symbol to at most once per second to prevent DB pool thrashing
        if not hasattr(self, "_last_tick_check"):
            self._last_tick_check = {}
        evt_time = getattr(event, "timestamp", None) or clock.now()
        now_ts = evt_time.timestamp()
        if now_ts - self._last_tick_check.get(sym_clean, 0) < 1.0:
            return
        self._last_tick_check[sym_clean] = now_ts

        from database.db import get_session
        from database.models import Position, SystemConfig
        from sqlalchemy import select

        try:
            async with get_session() as session:
                # Fast check for DB emergency kill switch
                cfg_kill = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == "kill_switch")
                )).scalar_one_or_none()
                kill_active = bool(cfg_kill and str(cfg_kill.value).lower() in ("true", "1", "yes"))
                if kill_active:
                    if not getattr(self, "_kill_switch_triggered", False):
                        self._kill_switch_triggered = True
                        logger.critical(f"[PositionGuardian][on_tick] Emergency kill switch ACTIVE on tick {sym_clean}! Liquidating.")
                        if self.execution_service:
                            await self.execution_service.kill_switch("Database emergency kill switch triggered via tick")
                    return
                else:
                    self._kill_switch_triggered = False

                # Check if we have active positions for this symbol
                positions = (await session.execute(
                    select(Position)
                    .where(Position.symbol == sym_clean)
                    .where(Position.status.in_(["open", "orphan_pending_close"]))
                )).scalars().all()

                if not positions:
                    return

                # Retry orphan closes immediately
                for pos in positions:
                    if pos.status == "orphan_pending_close" and pos.mt5_ticket:
                        if self.execution_service:
                            res = await self.execution_service.close_position_by_ticket(
                                pos.mt5_ticket,
                                requested_by="position_guardian_tick",
                                reason="Emergency orphan retry close on tick",
                            )
                            if res and res.get("success"):
                                pos.status = "closed"
                                pos.closed_at = clock.now()
                                await session.commit()
        except Exception as e:
            logger.debug(f"[PositionGuardian] on_tick error for {sym_clean}: {e}")

    async def evaluate_position_threat_with_jev(
        self, position: Any, current_price: Optional[float] = None
    ) -> dict:
        """
        Sub-100ms real-time position threat assessment via TypeSafe Jev System One.
        Evaluates adverse momentum and stop-loss vulnerability without generating text.
        """
        try:
            from analysis.providers.llm_factory import get_client_for_task
            from utils.typesafe.jev_primitives import build_position_guard_questions
            client = get_client_for_task("jev_position_guard", self.settings)
            if not hasattr(client, "classify_json"):
                return {}

            direction = (getattr(position, "direction", "") or "").lower()
            symbol = getattr(position, "symbol", "UNKNOWN")
            state = {
                "symbol": symbol,
                "direction": direction,
                "entry_price": getattr(position, "entry_price", None),
                "current_price": current_price,
                "sl": getattr(position, "sl", None),
                "tp": getattr(position, "tp", None),
                "volume": getattr(position, "volume", None),
            }
            questions = build_position_guard_questions(symbol, direction)
            res = await client.classify_json(prompt="", state=state, jev_questions=questions)
            return res or {}
        except Exception as e:
            logger.debug(f"[PositionGuardian] Jev position threat assessment bypassed: {e}")
            return {}



