# ==============================================================================
# File: scheduler/flash_crash_detector.py
# ==============================================================================

"""
Flash Crash Circuit Breaker (Async).

Mendeteksi lonjakan / anomali volatilitas ekstrem intra-candle dengan Dual-Threshold Confluence:
1. Lonjakan Relatif: Range Move >= N x ATR_14 (H1)
2. Lonjakan Absolut: Move Percentage >= Min % Move (berdasarkan kelas aset: Crypto, FX, Komoditas)

Tindakan saat terdeteksi:
1. Kirim notifikasi darurat ke Telegram via AgentNotifier.
2. Geser Stop Loss ke Breakeven (entry price) untuk semua posisi terbuka pada simbol tersebut.
3. Karantina / blokir entry baru pada simbol terkait selama cooldown (default 30 min) di Risk Gate.
4. Persistensi status karantina ke PostgreSQL SystemConfig agar tahan restart.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PriceOHLCV, TechnicalIndicator, Position, ActivityLog, SystemConfig
import utils.clock as clock

logger = logging.getLogger("TradingAgent.FlashCrashDetector")

# Baseline fallback thresholds per asset class
DEFAULT_SYMBOL_RULES = {
    "BTCUSD": {"atr_multiplier": 6.0, "min_pct_move": 4.0},
    "EURUSD": {"atr_multiplier": 5.0, "min_pct_move": 1.2},
    "GBPUSD": {"atr_multiplier": 5.0, "min_pct_move": 1.2},
    "USDJPY": {"atr_multiplier": 5.0, "min_pct_move": 1.2},
    "AUDUSD": {"atr_multiplier": 5.0, "min_pct_move": 1.2},
    "XAUUSD": {"atr_multiplier": 4.5, "min_pct_move": 2.5},
    "XTIUSD": {"atr_multiplier": 4.5, "min_pct_move": 2.5},
    "XBRUSD": {"atr_multiplier": 4.5, "min_pct_move": 2.5},
}


class FlashCrashDetector:
    """
    Sistem pemantau dan circuit breaker lonjakan harga kilat (Flash Crash) berbasis Dual-Threshold.
    """

    def __init__(self, settings: dict, execution_service=None, notifier=None):
        self.settings = settings or {}
        self.execution_service = execution_service
        self.notifier = notifier
        
        flash_cfg = self.settings.get("trading", {}).get("risk", {}).get("flash_crash", {})
        self.enabled: bool = flash_cfg.get("enabled", True)
        self.default_atr_multiplier: float = float(flash_cfg.get("default_atr_multiplier", flash_cfg.get("atr_multiplier", 5.0)))
        self.default_min_pct_move: float = float(flash_cfg.get("default_min_pct_move", 2.0))
        self.lookback_minutes: int = int(flash_cfg.get("lookback_minutes", 15))
        self.cooldown_minutes: int = int(flash_cfg.get("cooldown_minutes", 30))
        self.symbol_rules: dict[str, dict] = flash_cfg.get("symbol_rules", {})
        
        # Simpan waktu expiry blokir per simbol {symbol: datetime_utc}
        self._blocked_symbols: dict[str, datetime] = {}
        self._persisted_loaded: bool = False

    def get_symbol_thresholds(self, symbol: str) -> tuple[float, float]:
        """Mengembalikan (atr_multiplier, min_pct_move) untuk simbol tertentu."""
        sym_clean = symbol.strip().upper().replace('/', '')
        rule = self.symbol_rules.get(sym_clean) or DEFAULT_SYMBOL_RULES.get(sym_clean)
        if rule:
            atr_mult = float(rule.get("atr_multiplier", self.default_atr_multiplier))
            min_pct = float(rule.get("min_pct_move", self.default_min_pct_move))
            return atr_mult, min_pct
        return self.default_atr_multiplier, self.default_min_pct_move

    async def load_persisted_blocks(self, session: AsyncSession) -> None:
        """Memuat status karantina aktif dari database SystemConfig saat inisialisasi/restart."""
        try:
            now = clock.now()
            configs = (await session.execute(
                select(SystemConfig).where(SystemConfig.key.like("flash_crash_blocked_%"))
            )).scalars().all()
            
            for cfg in configs:
                if not cfg.value:
                    continue
                sym = cfg.key.replace("flash_crash_blocked_", "").strip().upper()
                try:
                    expiry = datetime.fromisoformat(cfg.value)
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                    if expiry > now:
                        self._blocked_symbols[sym] = expiry
                        logger.info(f"Loaded active flash crash quarantine for {sym} until {expiry.isoformat()}")
                except Exception as parse_err:
                    logger.debug(f"Could not parse flash crash config timestamp {cfg.value}: {parse_err}")
            self._persisted_loaded = True
        except Exception as e:
            logger.debug(f"Failed loading persisted flash crash blocks: {e}")

    def is_symbol_blocked(self, symbol: str) -> bool:
        """Mengecek apakah simbol sedang dalam status karantina flash crash."""
        if not self.enabled:
            return False
        sym_clean = symbol.strip().upper().replace('/', '')
        blocked_until = self._blocked_symbols.get(sym_clean)
        if not blocked_until:
            return False
        now = clock.now()
        if blocked_until.tzinfo is None and now.tzinfo is not None:
            blocked_until = blocked_until.replace(tzinfo=timezone.utc)
        elif blocked_until.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
            
        if now < blocked_until:
            return True
        else:
            self._blocked_symbols.pop(sym_clean, None)
            return False

    async def check(self, session: AsyncSession) -> list[dict]:
        """
        Memeriksa semua simbol universe terhadap kondisi flash crash menggunakan Dual-Threshold Confluence.
        """
        if not self.enabled:
            return []

        if not self._persisted_loaded:
            await self.load_persisted_blocks(session)

        now = clock.now()
        symbols = self.settings.get("trading", {}).get(
            "asset_universe",
            ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "BTCUSD", "XTIUSD", "XBRUSD"]
        )
        alerts = []

        for symbol in symbols:
            try:
                # 1. Ambil nilai ATR_14 H1 terbaru
                atr_row = (await session.execute(
                    select(TechnicalIndicator)
                    .where(TechnicalIndicator.symbol == symbol)
                    .where(TechnicalIndicator.timeframe == "H1")
                    .where(TechnicalIndicator.indicator_name == "ATR_14")
                    .where(TechnicalIndicator.timestamp <= now)
                    .order_by(TechnicalIndicator.timestamp.desc())
                    .limit(1)
                )).scalar_one_or_none()

                if not atr_row:
                    continue

                try:
                    atr_data = json.loads(atr_row.value_json)
                    atr_h1 = float(atr_data.get("atr", atr_data)) if isinstance(atr_data, dict) else float(atr_data)
                except Exception:
                    val_attr = getattr(atr_row, "value", None)
                    atr_h1 = float(val_attr) if val_attr is not None else None

                if not atr_h1 or atr_h1 <= 0:
                    continue

                # 2. Ambil candle M15 (atau fallback M5) dalam lookback window (ISOLASI TIMEFRAME: TIDAK H1)
                lookback_dt = now - timedelta(minutes=self.lookback_minutes)
                candles = (await session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == symbol)
                    .where(PriceOHLCV.timeframe == "M15")
                    .where(PriceOHLCV.timestamp >= lookback_dt)
                    .order_by(PriceOHLCV.timestamp.desc())
                )).scalars().all()

                if not candles:
                    candles = (await session.execute(
                        select(PriceOHLCV)
                        .where(PriceOHLCV.symbol == symbol)
                        .where(PriceOHLCV.timeframe == "M5")
                        .where(PriceOHLCV.timestamp >= lookback_dt)
                        .order_by(PriceOHLCV.timestamp.desc())
                    )).scalars().all()

                if not candles:
                    continue

                max_high = max(c.high for c in candles)
                min_low = min(c.low for c in candles)
                range_move = max_high - min_low
                current_price = candles[0].close if hasattr(candles[0], "close") and candles[0].close > 0 else candles[0].open

                if current_price <= 0:
                    continue

                move_pct = (range_move / current_price) * 100.0
                atr_mult_thresh, min_pct_thresh = self.get_symbol_thresholds(symbol)

                # 3. DUAL-THRESHOLD CONFLUENCE: Lonjakan Relatif (ATR) DAN Lonjakan Absolut (% Harga)
                is_flash_crash = (range_move >= (atr_mult_thresh * atr_h1)) and (move_pct >= min_pct_thresh)

                if is_flash_crash:
                    # Jika simbol sudah dalam blokir aktif, hindari notifikasi berulang
                    if self.is_symbol_blocked(symbol):
                        continue

                    blocked_until = now + timedelta(minutes=self.cooldown_minutes)
                    self._blocked_symbols[symbol] = blocked_until
                    try:
                        cfg_key = f"flash_crash_blocked_{symbol}"
                        existing_cfg = (await session.execute(
                            select(SystemConfig).where(SystemConfig.key == cfg_key)
                        )).scalar_one_or_none()
                        if existing_cfg:
                            existing_cfg.value = blocked_until.isoformat()
                        else:
                            session.add(SystemConfig(key=cfg_key, value=blocked_until.isoformat()))
                        await session.commit()
                    except Exception as e:
                        logger.debug(f"Failed to persist flash crash block to DB (non-fatal): {e}")

                    multiplier = round(range_move / atr_h1, 2)
                    alert_info = {
                        "symbol": symbol,
                        "range_move": range_move,
                        "move_pct": round(move_pct, 2),
                        "atr_h1": atr_h1,
                        "multiplier": multiplier,
                        "high": max_high,
                        "low": min_low,
                        "blocked_until": blocked_until.isoformat(),
                    }
                    alerts.append(alert_info)
                    logger.critical(
                        f"🚨 FLASH CRASH DETECTED on {symbol}! Move={range_move:.5f} ({move_pct:.2f}% | {multiplier}x ATR H1). "
                        f"Symbol blocked for {self.cooldown_minutes} min until {blocked_until}."
                    )

                    # 4. Emergency SL tighten ke breakeven untuk posisi terbuka
                    await self._protect_open_positions(session, symbol, now)

                    # 5. Kirim notifikasi Telegram (mendukung .send() dan .send_critical())
                    if self.notifier:
                        msg = (
                            f"🚨 <b>CIRCUIT BREAKER: FLASH CRASH DETECTED</b>\n\n"
                            f"Instrumen: <b>{symbol}</b>\n"
                            f"Pergerakan: <code>{range_move:.5f}</code> ({move_pct:.2f}% | {multiplier}x ATR H1: {atr_h1:.5f})\n"
                            f"High: {max_high:.5f} | Low: {min_low:.5f}\n\n"
                            f"🛡️ <b>Tindakan Otomatis</b>:\n"
                            f"• Stop Loss posisi terbuka otomatis digeser ke Breakeven\n"
                            f"• Entry baru diblokir selama {self.cooldown_minutes} menit."
                        )
                        try:
                            if hasattr(self.notifier, "send"):
                                await self.notifier.send(msg)
                            elif hasattr(self.notifier, "send_critical"):
                                await self.notifier.send_critical(msg)
                        except Exception as e:
                            logger.error(f"Failed to send flash crash alert: {e}")

                    # Catat ke ActivityLog
                    try:
                        session.add(ActivityLog(
                            category="risk",
                            description=f"FLASH CRASH: {symbol} moved {range_move:.5f} ({move_pct:.2f}% / {multiplier}x ATR). Cooldown {self.cooldown_minutes}m.",
                            actor="flash_crash_detector",
                        ))
                        from database.event_store import TradingEventStore
                        await TradingEventStore.emit(
                            session=session,
                            event_type="risk.flash_crash",
                            payload={
                                "symbol": symbol,
                                "range_move": range_move,
                                "move_pct": move_pct,
                                "multiplier": multiplier,
                                "cooldown_minutes": self.cooldown_minutes,
                            },
                            correlation_id=f"flash_crash_{symbol}_{int(now.timestamp())}",
                            actor="flash_crash_detector",
                        )
                        await session.commit()
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"Error checking flash crash for {symbol}: {e}")

        return alerts

    async def _protect_open_positions(self, session: AsyncSession, symbol: str, now: datetime):
        """Memperketat SL ke level breakeven untuk posisi terbuka pada simbol terdampak."""
        try:
            positions = (await session.execute(
                select(Position)
                .where(Position.status == "open")
                .where(Position.symbol == symbol)
            )).scalars().all()

            for pos in positions:
                if not pos.mt5_ticket:
                    continue
                direction = (pos.direction or '').lower()
                entry = pos.entry_price
                current_sl = pos.sl

                if not entry:
                    continue

                # Fetch live quote to verify position is in profit before moving SL to breakeven
                current_price = None
                exec_svc = self.execution_service
                if exec_svc and hasattr(exec_svc, "get_current_price"):
                    try:
                        current_price = await exec_svc.get_current_price(pos.symbol)
                    except Exception:
                        pass
                if current_price is None and exec_svc and hasattr(exec_svc, "mt5"):
                    try:
                        tick = await exec_svc.mt5.get_current_price(pos.symbol)
                        if isinstance(tick, dict):
                            current_price = tick.get("bid") if direction == "buy" else tick.get("ask")
                    except Exception:
                        pass
                pos_curr_price = getattr(pos, "current_price", None)
                if current_price is None and pos_curr_price is not None:
                    current_price = float(pos_curr_price)

                should_tighten = False
                new_sl: Optional[float] = None
                if current_price is not None:
                    # Only tighten to BE if position is currently in profit (avoid MT5 INVALID_STOPS rejection)
                    if direction == "buy" and current_price > entry:
                        if current_sl is None or current_sl < entry:
                            should_tighten = True
                            new_sl = entry
                    elif direction == "sell" and current_price < entry:
                        if current_sl is None or current_sl > entry:
                            should_tighten = True
                            new_sl = entry

                if should_tighten and new_sl is not None and exec_svc and hasattr(exec_svc, "modify_position_sl_tp"):
                    try:
                        await exec_svc.modify_position_sl_tp(
                            ticket=pos.mt5_ticket, sl=new_sl, tp=pos.tp, requested_by="flash_crash_detector"
                        )
                        logger.info(f"FlashCrash: SL tightened to breakeven ({new_sl}) for {pos.symbol} ticket={pos.mt5_ticket}")
                    except Exception as e:
                        logger.warning(f"FlashCrash: Failed tightening SL for ticket {pos.mt5_ticket}: {e}")
        except Exception as e:
            logger.error(f"FlashCrash _protect_open_positions error for {symbol}: {e}")

    async def on_tick(self, event: Any) -> None:
        """
        EventBus subscriber handler for TickPriceEvent.
        Performs fast, low-latency evaluation of sudden price spikes/crashes.
        """
        if not self.enabled:
            return

        symbol = getattr(event, "symbol", "")
        if not symbol:
            return

        sym_clean = symbol.strip().upper().replace("/", "")
        if self.is_symbol_blocked(sym_clean):
            return

        bid = getattr(event, "bid", 0.0)
        ask = getattr(event, "ask", 0.0)
        current_price = getattr(event, "last", 0.0) or ((bid + ask) / 2.0 if bid and ask else bid or ask)
        if current_price <= 0:
            return

        if not hasattr(self, "_tick_history"):
            self._tick_history = {}

        now = getattr(event, "timestamp", None) or clock.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        history = self._tick_history.setdefault(sym_clean, [])
        history.append((now, current_price))

        cutoff = now - timedelta(minutes=self.lookback_minutes)
        self._tick_history[sym_clean] = [h for h in history if h[0] >= cutoff]
        history = self._tick_history[sym_clean]

        if len(history) < 2:
            return

        prices = [h[1] for h in history]
        range_move = max(prices) - min(prices)
        move_pct = (range_move / current_price) * 100.0

        _, min_pct_thresh = self.get_symbol_thresholds(sym_clean)

        if move_pct >= min_pct_thresh:
            from database.db import get_session
            try:
                async with get_session() as session:
                    alerts = await self.check(session)
                    if not alerts:
                        # Direct sub-second flash crash protection if DB candles have not yet closed
                        blocked_until = now + timedelta(minutes=self.cooldown_minutes)
                        self._blocked_symbols[sym_clean] = blocked_until
                        try:
                            from database.models import SystemConfig
                            from sqlalchemy import select
                            cfg_key = f"flash_crash_blocked_{sym_clean}"
                            existing_cfg = (await session.execute(
                                select(SystemConfig).where(SystemConfig.key == cfg_key)
                            )).scalar_one_or_none()
                            if existing_cfg:
                                existing_cfg.value = blocked_until.isoformat()
                            else:
                                session.add(SystemConfig(key=cfg_key, value=blocked_until.isoformat()))
                            await session.commit()
                        except Exception as cfg_err:
                            logger.debug(f"Failed to persist flash crash block to DB: {cfg_err}")

                        await self._protect_open_positions(session, sym_clean, now)
                        alerts = [{"symbol": sym_clean, "range_move": range_move, "move_pct": move_pct}]

                    if alerts:
                        try:
                            from utils.protocol.event_bus import get_event_bus, CircuitBreakerEvent
                            bus = get_event_bus()
                            cb_event = CircuitBreakerEvent(
                                component="FlashCrashDetector",
                                reason=f"Flash crash on {sym_clean}: {move_pct:.2f}% price move",
                                is_active=True,
                                cooldown_seconds=self.cooldown_minutes * 60,
                                timestamp=now,
                            )
                            await bus.publish(cb_event)
                        except Exception as pub_err:
                            logger.debug(f"Failed to publish CircuitBreakerEvent from FlashCrashDetector: {pub_err}")
            except Exception as e:
                logger.error(f"[FlashCrashDetector] on_tick check failed for {sym_clean}: {e}")

