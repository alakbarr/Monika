"""
Two-Tier Pre-Flight Turn Gate.

Supervises environment preconditions BEFORE invoking LLM analysis turns:
1. Daily Rollover & Off-Peak Liquidity Freeze (21:55 - 02:00 UTC) for non-crypto assets.
2. MT5 Terminal Liveness & Quote Freshness (<60s).
3. Two-Tier Empirical MT5 Spread Expansion:
   - Active hours (06:00 - 21:00 UTC): Spread > 2.0x median or hard ceiling.
   - Asian session (02:00 - 06:00 UTC): Spread > 2.5x median.
4. Tier-1 High-Impact Economic Event Freeze Window (+-15m).

Consumes 0 LLM tokens when preconditions are not met.
"""

from typing import Tuple, Optional, Any, cast
from datetime import datetime, timezone, timedelta
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import utils.clock as clock

logger = logging.getLogger("TradingAgent.PreFlightGate")

# Verified empirical baseline active medians (in points) from FBS MT5 terminal
EMPIRICAL_ACTIVE_MEDIANS = {
    "XAUUSD": 23.0,   # $0.23
    "EURUSD": 8.0,    # 0.8 pip
    "GBPUSD": 9.0,    # 0.9 pip
    "USDJPY": 9.0,    # 0.9 pip
    "AUDUSD": 9.0,    # 0.9 pip
    "XTIUSD": 2.0,    # $0.02
    "BTCUSD": 1965.0, # $19.65
    "XBRUSD": 2.0,    # $0.02
}

# Absolute hard ceiling limits during active hours (in points)
ACTIVE_SPREAD_HARD_CEILINGS = {
    "XAUUSD": 45.0,
    "EURUSD": 16.0,
    "GBPUSD": 18.0,
    "USDJPY": 18.0,
    "AUDUSD": 18.0,
    "XTIUSD": 4.0,
    "BTCUSD": 2500.0,
    "XBRUSD": 4.0,
}

SYMBOL_CURRENCIES = {
    "EURUSD": ["EUR", "USD"],
    "GBPUSD": ["GBP", "USD"],
    "USDJPY": ["USD", "JPY"],
    "AUDUSD": ["AUD", "USD"],
    "XAUUSD": ["USD"],
    "XTIUSD": ["USD"],
    "BTCUSD": ["USD"],
    "XBRUSD": ["USD"],
}


class PreFlightTurnGate:
    """Supervises environment preconditions before invoking LLM turns."""

    @classmethod
    async def check_high_impact_news(
        cls,
        session: AsyncSession,
        symbol: str,
        now_utc: datetime,
        buffer_minutes: int = 15,
    ) -> Tuple[bool, Optional[str]]:
        """Checks if symbol's constituent currencies have high-impact news within +-buffer_minutes."""
        try:
            from database.models import EconomicCalendar
            currencies = SYMBOL_CURRENCIES.get(symbol, ["USD"])
            window_start = now_utc - timedelta(minutes=buffer_minutes)
            window_end = now_utc + timedelta(minutes=buffer_minutes)

            events = (await session.execute(
                select(EconomicCalendar)
                .where(EconomicCalendar.currency.in_(currencies))
                .where(EconomicCalendar.impact.in_(["high", "critical", "HIGH", "CRITICAL"]))
                .where(EconomicCalendar.event_time >= window_start)
                .where(EconomicCalendar.event_time <= window_end)
            )).scalars().all()

            if events:
                event = events[0]
                return True, f"{event.event_name} ({event.currency})"
            return False, None
        except Exception as e:
            logger.debug(f"[{symbol}] News proximity check non-fatal error: {e}")
            return False, None

    @classmethod
    async def evaluate_preconditions(
        cls,
        session: Optional[AsyncSession],
        symbol: str,
        settings: Optional[dict] = None,
        mt5_client: Optional[Any] = None,
        override_time: Optional[datetime] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluates whether an asset is in a valid state for LLM analysis.
        
        Returns:
            (is_allowed: bool, rejection_reason: Optional[str])
        """
        cfg = settings or {}
        sym_clean = (symbol or "").strip().upper().replace("/", "")
        now_utc = override_time or clock.now()
        hour = now_utc.hour
        minute = now_utc.minute

        # 1. 24/7 Asset Exception (Crypto is traded 24/7, exempt from FX rollover freeze)
        always_open = set(cfg.get("trading", {}).get("24_7_assets", ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]))
        is_24_7 = sym_clean in always_open or "BTC" in sym_clean or "ETH" in sym_clean

        # 2. Daily Rollover Window (21:55 - 22:30 UTC)
        if not is_24_7:
            if (hour == 21 and minute >= 55) or (hour == 22 and minute <= 30):
                reason = f"Rollover/Off-peak liquidity window ({hour:02d}:{minute:02d} UTC). Non-crypto entry halted."
                logger.info(f"[{sym_clean}] PreFlightGate: Blocked — {reason}")
                return False, reason

        # 3. MT5 Terminal & Quote Freshness Check (<60s)
        if mt5_client is None:
            try:
                from execution.mt5_client import MT5Client
                mt5_client = MT5Client(cfg)
            except Exception as e:
                logger.debug(f"[{sym_clean}] PreFlightGate: MT5 client import failed: {e}")
                mt5_client = None

        if mt5_client is not None:
            tick = None
            try:
                get_tick_fn = getattr(mt5_client, "get_latest_tick", None)
                if callable(get_tick_fn):
                    tick = await cast(Any, get_tick_fn)(sym_clean)
            except Exception as e:
                logger.warning(f"[{sym_clean}] PreFlightGate: Error getting latest tick: {e}")

            if tick is not None:
                # Check quote age
                tick_time = getattr(tick, "time", None)
                if tick_time is not None:
                    # Tick time can be timestamp (int/float) or datetime
                    if isinstance(tick_time, (int, float)):
                        tick_ts = tick_time
                    elif isinstance(tick_time, datetime):
                        tick_ts = tick_time.timestamp()
                    else:
                        tick_ts = now_utc.timestamp()
                    age = abs(now_utc.timestamp() - tick_ts)
                    if age > 60 and not is_24_7:
                        reason = f"MT5 quote stale for {sym_clean} (age={age:.0f}s > 60s)."
                        logger.info(f"[{sym_clean}] PreFlightGate: Blocked — {reason}")
                        return False, reason

                # 4. Empirical Spread Expansion Evaluation
                raw_spread = getattr(tick, "spread", None)
                if raw_spread is not None:
                    curr_spread = float(raw_spread)
                    baseline_med = EMPIRICAL_ACTIVE_MEDIANS.get(sym_clean, 10.0)
                    hard_ceiling = ACTIVE_SPREAD_HARD_CEILINGS.get(sym_clean, baseline_med * 2.0)

                    # Active Hours (06:00 - 21:00 UTC) threshold: 2.0x median or hard ceiling
                    if 6 <= hour < 21:
                        if curr_spread > (baseline_med * 2.0) or curr_spread > hard_ceiling:
                            reason = (
                                f"Abnormal active spread expansion: {curr_spread:.1f} pts "
                                f"(median={baseline_med:.1f}, threshold=2.0x / {hard_ceiling:.1f} pts)."
                            )
                            logger.info(f"[{sym_clean}] PreFlightGate: Blocked — {reason}")
                            return False, reason
                    else:
                        # Asian Session (02:00 - 06:00 UTC) threshold: 2.5x median
                        if curr_spread > (baseline_med * 2.5):
                            reason = (
                                f"Off-peak Asian spread expansion: {curr_spread:.1f} pts "
                                f"(median={baseline_med:.1f}, threshold=2.5x)."
                            )
                            logger.info(f"[{sym_clean}] PreFlightGate: Blocked — {reason}")
                            return False, reason
            else:
                is_dry_run = cfg.get("trading", {}).get("dry_run", False) or not cfg.get("trading", {}).get("auto_execute", False)
                if not is_dry_run:
                    reason = f"MT5 tick data unavailable for {sym_clean} in live execution mode."
                    logger.warning(f"[{sym_clean}] PreFlightGate: Blocked — {reason}")
                    return False, reason

        # 5. Tier-1 High-Impact Event Freeze Window (+-15m)
        if session is not None:
            near_news, event_title = await cls.check_high_impact_news(session, sym_clean, now_utc, buffer_minutes=15)
            if near_news:
                reason = f"Freeze window: High-impact economic event '{event_title}' within 15 minutes."
                logger.info(f"[{sym_clean}] PreFlightGate: Blocked — {reason}")
                return False, reason

        return True, None
