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

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock

logger = logging.getLogger("TradingAgent.PreFlightGate")

# Verified empirical baseline active medians (in points) from live MT5 terminal
EMPIRICAL_ACTIVE_MEDIANS = {
    "XAUUSD": 35.0,  # $0.35 (live active: 38.0)
    "EURUSD": 10.0,  # 1.0 pip (live active: 10.0)
    "GBPUSD": 11.0,  # 1.1 pip (live active: 11.0)
    "USDJPY": 10.0,  # 1.0 pip (live active: 10.0)
    "AUDUSD": 11.0,  # 1.1 pip (live active: 11.0)
    "XTIUSD": 4.0,  # $0.04 (live active: 4.0)
    "BTCUSD": 2000.0,  # $20.00 (live active: 1965.0)
    "XBRUSD": 3.5,  # $0.035 (live active: 3.0)
}

# Absolute hard ceiling limits during active hours (in points)
ACTIVE_SPREAD_HARD_CEILINGS = {
    "XAUUSD": 70.0,  # $0.70 (up to 2.0x active median)
    "EURUSD": 20.0,  # 2.0 pips
    "GBPUSD": 22.0,  # 2.2 pips
    "USDJPY": 20.0,  # 2.0 pips
    "AUDUSD": 22.0,  # 2.2 pips
    "XTIUSD": 10.0,  # $0.10 (up to 2.5x active median)
    "BTCUSD": 4500.0,  # $45.00 (tolerates crypto volatility & weekend widenings)
    "XBRUSD": 10.0,  # $0.10 (up to 2.8x active median)
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
            from monika.domain.market.currency_utils import get_symbol_currencies
            from monika.infrastructure.database.models import EconomicCalendar

            sym_clean = symbol.replace("/", "").replace("_", "").replace(".", "").upper()
            currencies = SYMBOL_CURRENCIES.get(sym_clean)
            if not currencies:
                c_set = get_symbol_currencies(sym_clean)
                currencies = (
                    list(c_set) if c_set else ([sym_clean[:3], sym_clean[3:6]] if len(sym_clean) >= 6 else ["USD"])
                )

            window_start = now_utc - timedelta(minutes=buffer_minutes)
            window_end = now_utc + timedelta(minutes=buffer_minutes)

            events = (
                (
                    await session.execute(
                        select(EconomicCalendar)
                        .where(EconomicCalendar.currency.in_(currencies))
                        .where(EconomicCalendar.impact.in_(["high", "critical", "HIGH", "CRITICAL"]))
                        .where(EconomicCalendar.event_time >= window_start)
                        .where(EconomicCalendar.event_time <= window_end)
                    )
                )
                .scalars()
                .all()
            )

            if events:
                event = events[0]
                return True, f"{event.event_name} ({event.currency})"
            return False, None
        except Exception as e:
            logger.warning(f"[{symbol}] News proximity check error (fail-closed): {e}")
            return True, f"Economic calendar error ({e})"

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
        is_replay_or_sim = (
            clock.is_simulated()
            or bool(cfg.get("replay_mode", False))
            or bool(cfg.get("simulation_mode", False))
            or bool(cfg.get("backtest_mode", False))
        )

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
                from monika.infrastructure.brokers.mt5_client import MT5Client

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

                    broker_offset = 0
                    if hasattr(mt5_client, "get_broker_utc_offset_seconds"):
                        try:
                            res_offset = await mt5_client.get_broker_utc_offset_seconds()
                            if isinstance(res_offset, (int, float)):
                                broker_offset = int(res_offset)
                        except Exception:
                            pass
                    elif hasattr(mt5_client, "_broker_utc_offset_seconds"):
                        broker_offset = int(getattr(mt5_client, "_broker_utc_offset_seconds", 0) or 0)

                    # Dynamic fallback if broker offset was not detected yet or shifted by whole hours (DST transition)
                    diff_s = tick_ts - now_utc.timestamp()
                    if broker_offset == 0 or abs(diff_s - broker_offset) >= 1800:
                        cand_hours = round(diff_s / 3600.0)
                        if abs(diff_s - cand_hours * 3600) < 180 and -14 <= cand_hours <= 14:
                            broker_offset = int(cand_hours * 3600)

                    tick_utc_ts = tick_ts - broker_offset
                    age = abs(now_utc.timestamp() - tick_utc_ts)
                    if not is_replay_or_sim and age > 180:
                        reason = f"MT5 quote stale for {sym_clean} (age={age:.0f}s > 180s)."
                        logger.info(f"[{sym_clean}] PreFlightGate: Blocked — {reason}")
                        return False, reason

                # 4. Empirical Spread Expansion Evaluation
                raw_spread = getattr(tick, "spread", None)
                if raw_spread is not None:
                    try:
                        curr_spread = float(raw_spread)
                    except ValueError, TypeError:
                        curr_spread = -1.0

                    import math

                    if math.isnan(curr_spread) or curr_spread <= 0:
                        is_dry_run = (
                            is_replay_or_sim
                            or cfg.get("trading", {}).get("dry_run", False)
                            or not cfg.get("trading", {}).get("auto_execute", False)
                        )
                        if not is_dry_run:
                            reason = f"Invalid or non-positive spread ({raw_spread}) for {sym_clean} in live mode."
                            logger.warning(f"[{sym_clean}] PreFlightGate: Blocked — {reason}")
                            return False, reason
                    else:
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
                is_dry_run = (
                    is_replay_or_sim
                    or cfg.get("trading", {}).get("dry_run", False)
                    or not cfg.get("trading", {}).get("auto_execute", False)
                )
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

            # 6. ADR Exhaustion Check: Halt LLM analysis when ADR is >= 95% exhausted
            try:
                from monika.application.analysis.calculators.daily_range_calculator import compute_daily_range_context

                adr_ctx = await compute_daily_range_context(session, sym_clean, settings=cfg, as_of=now_utc)
                if isinstance(adr_ctx, dict) and "error" not in adr_ctx:
                    pct_consumed = float(adr_ctx.get("today_range_pct_of_adr", 0.0) or 0.0)
                    if pct_consumed >= 0.95:
                        reason = (
                            f"Daily range exhausted: today's range ({adr_ctx.get('today_range_so_far', 0):.5f}) "
                            f"has consumed {pct_consumed:.1%} of ADR ({adr_ctx.get('adr', 0):.5f}). "
                            f"Turn halted to prevent exhaustion traps."
                        )
                        logger.info(f"[{sym_clean}] PreFlightGate: Blocked — {reason}")
                        return False, reason
            except Exception as adr_err:
                logger.debug(f"[{sym_clean}] PreFlightGate ADR exhaustion check non-fatal: {adr_err}")

        return True, None
