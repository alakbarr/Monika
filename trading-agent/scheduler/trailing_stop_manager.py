# ==============================================================================
# File: scheduler/trailing_stop_manager.py
# ==============================================================================

"""
Trailing Stop Manager: Manajemen trailing stop berbasis ATR.

Strategi:
- Jika profit mencapai X * ATR -> geser Stop Loss ke Breakeven (BE).
- Jika profit mencapai 2X * ATR -> aktifkan Trailing Stop dengan jarak Y * ATR.
(Hanya berjalan jika `trailing_stop.enabled` = true di settings).
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.db import get_session
from database.models import Position, PriceOHLCV, TechnicalIndicator

logger = logging.getLogger("TradingAgent.TrailingStop")


class TrailingStopManager:
    """
    Mengelola trailing stop otomatis untuk setiap posisi terbuka.
    Periode pemantauan (default 10 menit) diatur di konfigurasi.
    """

    def __init__(self, settings: dict, execution_service=None, recovery_event=None):
        self.settings = settings
        self.execution_service = execution_service
        self._recovery_event = recovery_event
        trail_cfg = settings.get("trading", {}).get("trailing_stop") or settings.get("trailing_stop", {})
        self.enabled = trail_cfg.get("enabled", True)  # Default True agar konsisten dengan settings.yaml
        self.breakeven_atr_multiple = float(trail_cfg.get("breakeven_atr_multiple", 1.0))
        self.trail_atr_multiple = float(trail_cfg.get("trail_atr_multiple", 1.5))
        self.check_timeframe = trail_cfg.get("timeframe", "H4")
        self.interval_minutes = float(trail_cfg.get("check_interval_minutes", 10))
        self._running = False
        self._is_forex_blocked = False
        self._stop_event = asyncio.Event()
        from execution.order_emulator import ClientOrderEmulator
        self.order_emulator = ClientOrderEmulator(
            execution_service=self.execution_service,
            settings=self.settings,
        )

    async def run_once(self) -> dict:
        """Cek semua posisi terbuka, update stop loss (BE/Trailing) bila memenuhi syarat."""
        if not self.enabled or not self.execution_service:
            return {"skipped": True, "reason": "disabled_or_no_execution_service"}

        now = datetime.now(timezone.utc)
        weekday = now.weekday()
        hour = now.hour
        # Market close window for forex (crypto 24/7 is exempt)
        is_friday_close = weekday == 4 and 20 <= hour <= 21
        is_sunday_open = weekday == 6 and 20 <= hour <= 21
        is_saturday = weekday == 5  # Tetap block sabtu untuk forex
        self._is_forex_blocked = is_friday_close or is_sunday_open or is_saturday

        async with get_session() as session:
            # Check pause / kill-switch state
            from database.models import SystemConfig
            cfgs = (await session.execute(
                select(SystemConfig).where(SystemConfig.key.in_(("kill_switch", "trading_paused", "system_paused")))
            )).scalars().all()
            for c in cfgs:
                if c.value and c.value.lower().startswith("true"):
                    logger.debug(f"TrailingStopManager: Skipped check because {c.key} is active ({c.value})")
                    return {"skipped": True, "reason": f"{c.key}_active"}

            open_positions = list((await session.execute(
                select(Position).where(Position.status == "open")
            )).scalars().all())

            if not open_positions:
                await self.order_emulator.sync_positions([])
                return {"positions_checked": 0}

            # Sync open positions with in-memory order emulator for sub-second tick tracking
            atr_map = {}
            for p in open_positions:
                if p.symbol not in atr_map:
                    atr_row = (await session.execute(
                        select(TechnicalIndicator)
                        .where(TechnicalIndicator.symbol == p.symbol)
                        .where(TechnicalIndicator.timeframe == self.check_timeframe)
                        .where(TechnicalIndicator.indicator_name == "ATR_14")
                        .order_by(TechnicalIndicator.timestamp.desc())
                        .limit(1)
                    )).scalar_one_or_none()
                    if atr_row:
                        import json
                        try:
                            atr_map[p.symbol] = float(json.loads(atr_row.value_json))
                        except Exception:
                            pass
            await self.order_emulator.sync_positions(open_positions, atr_lookup=atr_map)

            adjustments = []
            for pos in open_positions:
                if pos.pair_group_id and not pos.pair_group_id.startswith("tranche_"):
                    continue
                from utils.validation.data_validator import is_crypto_symbol
                if self._is_forex_blocked and not is_crypto_symbol(pos.symbol):
                    continue
                result = await self._check_position(session, pos)
                if result:
                    adjustments.append(result)

        return {"positions_checked": len(open_positions), "adjustments": adjustments}

    async def _check_position(self, session: AsyncSession, pos: Position, current_price_override: Optional[float] = None) -> dict:
        """Evaluasi logika Breakeven & Trailing per posisi."""
        if not pos.sl or not pos.entry_price or not pos.mt5_ticket:
            return {}

        # Per-position news window check
        from utils.market.currency_utils import get_symbol_currencies
        from database.models import EconomicCalendar
        from datetime import timedelta
        news_window_minutes = self.settings.get('trading', {}).get('risk', {}).get('news_window_minutes', 30)
        window = timedelta(minutes=news_window_minutes)
        pos_currencies = get_symbol_currencies(pos.symbol)
        now = datetime.now(timezone.utc)
        
        try:
            upcoming_pos_news = (await session.execute(
                select(EconomicCalendar)
                .where(EconomicCalendar.impact.in_(["high", "High", "HIGH"]))
                .where(EconomicCalendar.currency.in_(list(pos_currencies)))
                .where(EconomicCalendar.event_time >= now)
                .where(EconomicCalendar.event_time <= now + window)
                .limit(1)
            )).scalar_one_or_none()
            if upcoming_pos_news:
                event_time_str = upcoming_pos_news.event_time.strftime('%H:%M UTC') if upcoming_pos_news.event_time else '?'
                logger.info(
                    f'TrailingStop: pausing for {pos.symbol} during news window ({upcoming_pos_news.event_name} at {event_time_str})'
                )
                return {}
        except Exception as e:
            logger.debug(f'TrailingStop news check failed for {pos.symbol}: {e}')

        # Get current price from override, MT5, or fallback to last DB bar
        current_price = current_price_override
        if current_price is None and self.execution_service and hasattr(self.execution_service, 'mt5') and self.execution_service.mt5:
            try:
                open_mt5 = await self.execution_service.mt5.get_open_positions()
                for p in open_mt5:
                    if p.get('ticket') == pos.mt5_ticket and p.get('price_current'):
                        current_price = float(p.get('price_current'))
                        break
            except Exception as e:
                logger.debug(f"TrailingStopManager: Could not get MT5 live price for ticket {pos.mt5_ticket}: {e}")

        if current_price is None:
            last_bar = (await session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == pos.symbol)
                .where(PriceOHLCV.timeframe == self.check_timeframe)
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()

            if not last_bar:
                return {}
            current_price = last_bar.close

        # Get ATR
        atr_row = (await session.execute(
            select(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == pos.symbol)
            .where(TechnicalIndicator.timeframe == self.check_timeframe)
            .where(TechnicalIndicator.indicator_name == "ATR_14")
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()

        if not atr_row:
            return {}

        import json
        try:
            atr = float(json.loads(atr_row.value_json))
        except Exception:
            return {}

        entry = pos.entry_price
        current_sl = pos.sl
        
        new_sl = None
        reason = ""

        # TimesFM 3.0 Dynamic Volatility Trailing Adjustment
        effective_trail_mult = self.trail_atr_multiple
        if self.settings.get("timesfm", {}).get("volatility_trailing_adjustment", True):
            try:
                from indicators.timesfm_engine import TimesFMEngine
                tfm_engine = TimesFMEngine(self.settings)
                tfm_fc = await tfm_engine.get_latest_forecast(session, pos.symbol, timeframe='H1', max_age_hours=8.0)
                if tfm_fc:
                    vr = float(tfm_fc.get('volatility_expansion_ratio', 1.0))
                    if vr >= 1.30:
                        effective_trail_mult = round(self.trail_atr_multiple * 1.25, 2)
                    elif vr <= 0.75:
                        effective_trail_mult = round(self.trail_atr_multiple * 0.80, 2)
            except Exception:
                pass

        profit_distance = 0.0
        if pos.direction == "buy":
            profit_distance = current_price - entry
            sl_distance = entry - current_sl if current_sl else None
            
            # Auto-Breakeven saat TP1 (+1.0x ATR) tercapai atau profit >= 1x SL distance
            if profit_distance >= (1.0 * atr) or (sl_distance and profit_distance >= sl_distance):
                breakeven_sl = entry + (0.1 * atr)  # sedikit di atas entry untuk cover spread
                if breakeven_sl > current_sl:
                    new_sl = breakeven_sl
                    reason = f"tp1_breakeven (profit={profit_distance:.5f} >= 1.0x ATR {atr:.5f})"
            
            # Trail: jika harga bergerak searah profit sebesar 2x ATR, mulai trailing SL
            if profit_distance >= 2 * self.breakeven_atr_multiple * atr:
                trailing_sl = current_price - (effective_trail_mult * atr)
                if trailing_sl > current_sl and (new_sl is None or trailing_sl > new_sl):
                    new_sl = trailing_sl
                    reason = f"trailing_stop (profit={profit_distance:.4f}, trail={trailing_sl:.4f}, mult={effective_trail_mult}x)"

        elif pos.direction == "sell":
            profit_distance = entry - current_price
            sl_distance = current_sl - entry if current_sl else None
            
            # Auto-Breakeven saat TP1 (+1.0x ATR) tercapai atau profit >= 1x SL distance
            if profit_distance >= (1.0 * atr) or (sl_distance and profit_distance >= sl_distance):
                breakeven_sl = entry - (0.1 * atr)
                if breakeven_sl < current_sl:
                    new_sl = breakeven_sl
                    reason = f"tp1_breakeven (profit={profit_distance:.5f} >= 1.0x ATR {atr:.5f})"
            
            if profit_distance >= 2 * self.breakeven_atr_multiple * atr:
                trailing_sl = current_price + (effective_trail_mult * atr)
                if trailing_sl < current_sl and (new_sl is None or trailing_sl < new_sl):
                    new_sl = trailing_sl
                    reason = f"trailing_stop (profit={profit_distance:.4f}, trail={trailing_sl:.4f}, mult={effective_trail_mult}x)"

        # Check TP1 milestone and advance TradePlan status to PARTIAL_TP1_HIT
        is_tp1_hit = profit_distance >= (1.0 * atr)
        if is_tp1_hit:
            try:
                from database.models import TradePlan, TradePlanLeg
                from sqlalchemy.orm import selectinload
                tp_stmt = (
                    select(TradePlan)
                    .options(selectinload(TradePlan.legs))
                    .where(TradePlan.symbol == pos.symbol, TradePlan.status.in_(["PENDING_PROBE", "PROBE_FILLED", "CONFIRMED_SCALE_IN"]))
                    .order_by(TradePlan.created_at.desc())
                    .limit(1)
                )
                plan_record = (await session.execute(tp_stmt)).scalar_one_or_none()
                if plan_record:
                    plan_record.status = "PARTIAL_TP1_HIT"
                    probe_lots_to_close = 0.0
                    for leg in plan_record.legs:
                        if leg.leg_type == "probe" and leg.status == "filled":
                            leg.status = "tp_hit"
                            probe_vol = getattr(leg, "volume", None)
                            if probe_vol is None:
                                probe_vol = getattr(leg, "allocated_lots", None)
                            probe_lots_to_close += float(probe_vol or (pos.volume * 0.3 if pos.volume else 0.0))
                    await session.commit()
                    logger.info(f"[{pos.symbol}] TradePlan #{plan_record.id} advanced to PARTIAL_TP1_HIT")

                    # Execute actual partial close on MT5/broker
                    if probe_lots_to_close > 0 and pos.mt5_ticket and self.execution_service:
                        adapter = getattr(self.execution_service, "broker_adapter", None)
                        mt5_client = getattr(self.execution_service, "mt5", None)
                        try:
                            if adapter and hasattr(adapter, "close_position"):
                                await adapter.close_position(ticket=pos.mt5_ticket, lots=probe_lots_to_close)
                            elif mt5_client and hasattr(mt5_client, "close_position"):
                                await mt5_client.close_position(ticket=pos.mt5_ticket, lots=probe_lots_to_close)
                            logger.info(f"[{pos.symbol}] Executed MT5 partial close for TP1: ticket={pos.mt5_ticket}, lots={probe_lots_to_close}")
                        except Exception as close_err:
                            logger.error(f"[{pos.symbol}] Failed MT5 partial close on TP1: {close_err}")
            except Exception as tp_stat_err:
                logger.debug(f"TradePlan status update non-fatal: {tp_stat_err}")

        if new_sl is not None and self.execution_service is not None:
            tracked = getattr(self.order_emulator, "tracked_positions", {}).get(pos.mt5_ticket)
            if tracked and getattr(tracked, "is_modifying", False):
                logger.debug(f"[TrailingStopManager] Ticket {pos.mt5_ticket} is being modified by emulator, skipping.")
                return {}

            logger.info(
                f"TrailingStop: adjusting {pos.symbol} ticket={pos.mt5_ticket} "
                f"SL from {current_sl:.4f} to {new_sl:.4f} — {reason}"
            )
            emulator_lock = getattr(self.order_emulator, "_lock", None)
            async with (emulator_lock if emulator_lock is not None else asyncio.Lock()):
                if tracked:
                    tracked.is_modifying = True
                try:
                    result = await self.execution_service.modify_position_sl_tp(
                        pos.mt5_ticket, sl=new_sl, tp=None,
                        requested_by="trailing_stop_manager"
                    )
                    if result.get('success'):
                        if tracked:
                            tracked.current_sl = new_sl
                            tracked.last_sl_update = datetime.now(timezone.utc).timestamp()
                        if pos.analysis_id:
                            try:
                                from utils.analytics.paper_tracker import PaperTracker
                                tracker = PaperTracker()
                                async with get_session() as paper_session:
                                    await tracker.update_paper_trade_sl(paper_session, pos.analysis_id, new_sl)
                            except Exception as e:
                                logger.debug(f'Paper trade SL sync failed (non-fatal): {e}')
                    return {
                        "symbol": pos.symbol,
                        "ticket": pos.mt5_ticket,
                        "old_sl": current_sl,
                        "new_sl": new_sl,
                        "reason": reason,
                        "success": result.get("success", False),
                    }
                except Exception as e:
                    logger.error(f"Trailing stop adjustment failed: {e}")
                    return {"error": str(e)}
                finally:
                    if tracked:
                        tracked.is_modifying = False

        return {}

    async def start(self) -> None:
        """Looping pemantauan trailing stop (continuous)."""
        self._running = True
        if not self.enabled:
            logger.info("TrailingStopManager: disabled in settings (idling)")
            while self._running:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=3600)
                    break
                except asyncio.TimeoutError:
                    pass
                except asyncio.CancelledError:
                    break
            return
        
        logger.info(f"TrailingStopManager started (interval: {self.interval_minutes}min)")
        
        if self._recovery_event:
            logger.info("[TrailingStopManager] Waiting for recovery event before first check pass...")
            try:
                await asyncio.wait_for(self._recovery_event.wait(), timeout=180.0)
                logger.info("[TrailingStopManager] Recovery complete, starting trailing stop loop.")
            except asyncio.TimeoutError:
                logger.warning("[TrailingStopManager] Recovery wait timed out (180s). Proceeding anyway.")

        while self._running:
            try:
                result = await self.run_once()
                if result.get("adjustments"):
                    logger.info(f"Trailing stop adjustments: {result['adjustments']}")
            except Exception as e:
                logger.error(f"TrailingStopManager error: {e}")
            
            sleep_duration = self.interval_minutes * 60
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_duration)
                break
            except asyncio.TimeoutError:
                pass

    # Backwards compatibility alias
    check_once = run_once

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()

    async def on_tick(self, event: Any) -> None:
        """
        EventBus subscriber handler for TickPriceEvent.
        First delegates to ClientOrderEmulator for fast in-memory trailing/BE evaluation.
        Falls back to DB check only if not yet tracked in emulator.
        """
        if not self.enabled:
            return

        # Fast path: in-memory emulator tick evaluation
        adjustments = await self.order_emulator.on_tick(event)
        if adjustments:
            logger.info(f"[TrailingStopManager][Emulator] Adjustments: {adjustments}")
            return

        symbol = getattr(event, "symbol", "")
        if not symbol:
            return

        sym_clean = symbol.strip().upper().replace("/", "")

        # Throttle checks per symbol to at most once per second to prevent DB pool thrashing
        if not hasattr(self, "_last_tick_check"):
            self._last_tick_check = {}
        evt_time = getattr(event, "timestamp", None) or datetime.now(timezone.utc)
        now_ts = evt_time.timestamp()
        if now_ts - self._last_tick_check.get(sym_clean, 0) < 1.0:
            return
        self._last_tick_check[sym_clean] = now_ts

        from database.db import get_session
        from database.models import Position
        from sqlalchemy import select

        try:
            async with get_session() as session:
                positions = (await session.execute(
                    select(Position)
                    .where(Position.symbol == sym_clean)
                    .where(Position.status == "open")
                )).scalars().all()

                if not positions:
                    return

                for pos in positions:
                    if pos.pair_group_id:
                        continue
                    from utils.validation.data_validator import is_crypto_symbol
                    if self._is_forex_blocked and not is_crypto_symbol(pos.symbol):
                        continue

                    bid = getattr(event, "bid", 0.0)
                    ask = getattr(event, "ask", 0.0)
                    tick_price = getattr(event, "last", 0.0)
                    if not tick_price or tick_price <= 0:
                        direction = (pos.direction or "").upper()
                        tick_price = bid if direction == "BUY" else (ask or bid)

                    adj = await self._check_position(session, pos, current_price_override=tick_price)
                    if adj:
                        logger.info(f"[TrailingStopManager][on_tick] Position {pos.symbol} ticket={pos.mt5_ticket} adjusted: {adj}")

                    # Register newly resolved position into emulator for future in-memory tick speed
                    if pos.mt5_ticket and pos.entry_price and pos.sl:
                        try:
                            pos_atr = 0.0
                            atr_row = (await session.execute(
                                select(TechnicalIndicator)
                                .where(TechnicalIndicator.symbol == pos.symbol)
                                .where(TechnicalIndicator.timeframe == self.check_timeframe)
                                .where(TechnicalIndicator.indicator_name == "ATR_14")
                                .order_by(TechnicalIndicator.timestamp.desc())
                                .limit(1)
                            )).scalar_one_or_none()
                            if atr_row:
                                import json
                                try:
                                    pos_atr = float(json.loads(atr_row.value_json))
                                except Exception:
                                    pass

                            await self.order_emulator.register_position(
                                ticket=int(pos.mt5_ticket),
                                symbol=pos.symbol,
                                direction=pos.direction,
                                entry_price=float(pos.entry_price),
                                current_sl=float(pos.sl),
                                atr=pos_atr,
                                current_tp=float(pos.tp) if pos.tp else None,
                                analysis_id=pos.analysis_id,
                                pair_group_id=pos.pair_group_id,
                            )
                        except Exception:
                            pass
        except Exception as e:
            logger.debug(f"[TrailingStopManager] on_tick failed for {sym_clean}: {e}")

