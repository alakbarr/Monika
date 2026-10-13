# ==============================================================================
# File: domain/risk/evaluators/market_checks.py
# ==============================================================================

"""
Data freshness, VIX volatility, news window, rollover, and microstructure checks for RiskGate.
"""

from __future__ import annotations

import json
import logging
import math
import zoneinfo
from datetime import datetime, timedelta, timezone, UTC
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.domain.market.currency_utils import get_symbol_currencies
from monika.domain.risk.evaluators.base import _RiskGateMixinBase, resolve_model
from monika.domain.risk.position_sizing import SizingResult

if TYPE_CHECKING:
    from monika.infrastructure.database.models import (
        EconomicCalendar,
        Position,
        PriceOHLCV,
        SystemConfig,
        TechnicalIndicator,
        UserPreference,
        VIXData,
    )
else:
    Position = resolve_model("Position")
    EconomicCalendar = resolve_model("EconomicCalendar")
    PriceOHLCV = resolve_model("PriceOHLCV")
    VIXData = resolve_model("VIXData")
    UserPreference = resolve_model("UserPreference")
    TechnicalIndicator = resolve_model("TechnicalIndicator")
    SystemConfig = resolve_model("SystemConfig")

logger = logging.getLogger("TradingAgent.RiskGate")


class RiskMarketChecksMixin(_RiskGateMixinBase):
    """Market condition, VIX, news event, and liquidity risk validation mixin."""

    async def _check_data_freshness(
        self, session: AsyncSession, symbol: str, as_of: datetime | None = None, is_backtest: bool = False
    ) -> tuple[bool, str]:
        """Tolak order jika data pasar (OHLCV/Indikator) basi atau tidak segar (hard gate)."""
        if is_backtest:
            return True, "backtest_freshness_ok"
        try:
            from monika.core.validation.data_validator import validate_data_freshness

            tfs = (
                self.settings.get("trading", {}).get("timeframes", ["M15", "H1", "H4", "D1"])
                if isinstance(self.settings, dict)
                else ["M15", "H1", "H4", "D1"]
            )
            freshness = await validate_data_freshness(session, [symbol], tfs)
            if not freshness.get("ready", True):
                errors = "; ".join(freshness.get("errors", []))
                return False, f"Stale market data: {errors}"
            return True, "data_freshness_ok"
        except Exception as e:
            logger.warning(f"Data freshness check error for {symbol}: {e}")
            return False, f"Data freshness check failed: {e}"

    async def _check_flash_crash_cooldown(self, symbol: str) -> tuple[bool, str]:
        """Pastikan simbol tidak sedang dalam status karantina Flash Crash circuit breaker."""
        if self.flash_crash_detector and self.flash_crash_detector.is_symbol_blocked(symbol):
            return False, f"Symbol {symbol} is in cooldown after Flash Crash circuit breaker trigger."
        return True, "flash_crash_not_active"

    async def _check_vix_threshold(
        self, session: AsyncSession, as_of: datetime | None = None, is_backtest: bool = False
    ) -> tuple[bool, str]:
        """Block new positions when VIX exceeds the configured pause threshold."""
        if is_backtest:
            return True, "vix_threshold_backtest_ok"
        from sqlalchemy import select

        risk_cfg = self.settings.get("trading", {}).get("risk", {})
        vix_thresholds = risk_cfg.get("vix_thresholds", {})
        pause_threshold = float(vix_thresholds.get("pause", 30))
        defensive_threshold = float(vix_thresholds.get("defensive", 25.0))

        now = as_of or clock.now()
        vix_row = (
            await session.execute(select(VIXData).where(VIXData.date <= now).order_by(VIXData.date.desc()).limit(1))
        ).scalar_one_or_none()

        vix_close = defensive_threshold  # Fail-safe default (defensive volatility)
        if vix_row is None:
            vix_age_days = 0
            vix_str_info = f"defaulting to {defensive_threshold} (Defensive Fail-Safe)"
        else:
            vix_close = vix_row.close
            now_dt = now if (hasattr(now, "tzinfo") and now.tzinfo) else now.replace(tzinfo=UTC)
            row_dt = (
                vix_row.date
                if (hasattr(vix_row.date, "tzinfo") and vix_row.date.tzinfo)
                else vix_row.date.replace(tzinfo=UTC)
            )
            vix_age_days = (now_dt - row_dt).total_seconds() / 86400
            vix_str_info = f"{vix_age_days:.1f} days old"

        if vix_row is not None and vix_age_days > 3.0:
            # Check if it's weekend or Monday before US close (vix_age_days up to 4.5 is normal for Friday close)
            is_weekend_or_monday = now.weekday() in (5, 6, 0)
            if is_weekend_or_monday and vix_age_days <= 4.5:
                vix_str_info += " (weekend/Monday expected delay)"
            else:
                # Fail-safe: if VIX is too stale, assume defensive risk
                vix_close = defensive_threshold
                vix_str_info += f" (stale -> defaulting to {defensive_threshold})"

        if vix_close >= pause_threshold:
            return False, (
                f"VIX={vix_close:.1f} >= pause threshold {pause_threshold}. "
                f"Extreme market fear detected. All new positions blocked. "
                f"Trading resumes automatically when VIX drops below {pause_threshold}."
            )

        return True, f"VIX={vix_close:.1f} ({vix_str_info} - below threshold {pause_threshold})"

    async def assess_weekend_gap_risk(
        self, session: AsyncSession, symbol: str, as_of: datetime | None = None
    ) -> tuple[bool, str]:
        """Blokir entri saat akhir pekan untuk aset non-24/7 (menghindari risiko gap)."""
        weekend_cfg = self.settings.get("trading", {}).get("weekend_management", {})
        exempted = weekend_cfg.get("exempted_symbols", ["BTCUSD", "ETHUSD"])
        gap_hours = weekend_cfg.get("gap_protection_hours", 2)

        sym_clean = symbol.upper().split(".")[0].rstrip("m").rstrip("+")
        if sym_clean in exempted or symbol in exempted or any(ex in symbol.upper() for ex in ("BTC", "ETH")):
            return True, f"{symbol} is exempted (24/7)"

        now = as_of or clock.now()
        weekday = now.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
        hour = now.hour

        # Block during actual weekend (market closed)
        if weekday == 5:
            return False, f"Forex/commodity markets closed all day Saturday. No new positions until Sunday 21:00 UTC."
        if weekday == 6 and hour < 21:
            return False, f"Forex/commodity markets closed (Sunday before 21:00 UTC). Sydney opens at ~21:00 UTC."

        # Block Friday within gap_protection_hours of close (21:00 UTC = high weekend gap risk)
        threshold_hour = 21 - gap_hours
        if weekday == 4 and hour >= threshold_hour:
            return False, (
                f"Blocked: {hour}:00 UTC Friday is within {gap_hours}h of weekend close (21:00 UTC). "
                f"High weekend gap risk. Wait until Sunday 21:00 UTC for new positions."
            )

        return True, "ok - not near weekend"

    async def _check_rollover_window(self, symbol: str, as_of: datetime | None = None) -> tuple[bool, str]:
        """Blokir entri saat jeda rollover harian (spread membesar). BTCUSD & ETHUSD kebal."""
        sym_clean = symbol.upper().split(".")[0].rstrip("m").rstrip("+")
        if (
            sym_clean in ("BTCUSD", "ETHUSD")
            or symbol in ("BTCUSD", "ETHUSD")
            or any(ex in symbol.upper() for ex in ("BTC", "ETH"))
        ):
            return True, f"{symbol} exempt from rollover check"

        now = as_of or clock.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        try:
            import zoneinfo

            ny_tz = zoneinfo.ZoneInfo("America/New_York")
            now_ny = now.astimezone(ny_tz)
            today_close = now_ny.replace(hour=17, minute=0, second=0, microsecond=0)
            diff_seconds = (now_ny - today_close).total_seconds()

            # Daily rollover window: 5 menit sebelum (-300s) hingga 30 menit sesudah (+1800s) 17:00 NY Close
            is_rollover = -300 <= diff_seconds <= 1800

            if is_rollover:
                window_start = today_close - timedelta(minutes=5)
                window_end = today_close + timedelta(minutes=30)
                start_utc = window_start.astimezone(UTC).strftime("%H:%M")
                end_utc = window_end.astimezone(UTC).strftime("%H:%M UTC")
                return False, (
                    f"Daily rollover window ({start_utc}-{end_utc}). Spreads are currently elevated. "
                    f"Current time: {now.strftime('%H:%M UTC')}. "
                    f"Retry after {end_utc}."
                )
        except Exception:
            hour = now.hour
            minute = now.minute
            is_rollover = (hour == 20 and minute >= 55) or (hour == 21 and minute <= 30)
            if is_rollover:
                return False, (
                    f"Daily rollover window (20:55-21:30 UTC). Spreads are currently elevated. "
                    f"Current time: {now.strftime('%H:%M UTC')}. "
                    f"Retry after 21:30 UTC."
                )

        return True, "Outside rollover window"

    async def _check_news_window(
        self,
        session: AsyncSession,
        symbol: str,
        as_of: datetime | None = None,
        is_backtest: bool = False,
        is_paper: bool = True,
    ) -> tuple[bool, str]:
        if is_backtest:
            return True, "news_window_backtest_ok"
        currencies = get_symbol_currencies(symbol)
        now = as_of or clock.now()
        window = timedelta(minutes=self.news_window_minutes)

        # 1. Check calendar data freshness via SystemConfig metadata first
        latest_calendar_fetch: datetime | None = None
        try:
            latest_fetch_cfg = (
                await session.execute(select(SystemConfig).where(SystemConfig.key == "last_calendar_fetch_at"))
            ).scalar_one_or_none()
            if latest_fetch_cfg and latest_fetch_cfg.value:
                dt = datetime.fromisoformat(latest_fetch_cfg.value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                latest_calendar_fetch = dt
        except Exception as e:
            logger.debug(f"Could not read last_calendar_fetch_at from SystemConfig: {e}")

        # Fallback to MAX(EconomicCalendar.fetched_at)
        if latest_calendar_fetch is None:
            max_fetched = (await session.execute(select(func.max(EconomicCalendar.fetched_at)))).scalar_one_or_none()
            if max_fetched is not None:
                if max_fetched.tzinfo is None:
                    max_fetched = max_fetched.replace(tzinfo=UTC)
                latest_calendar_fetch = max_fetched

        # Check if any calendar rows exist in DB at all
        total_events = (await session.execute(select(func.count(EconomicCalendar.id)))).scalar_one_or_none() or 0

        if total_events == 0 and latest_calendar_fetch is None:
            if is_paper:
                logger.warning(
                    "No economic calendar data exists in database. "
                    "Degraded mode: proceeding with warning instead of hard-block."
                )
                return True, "economic_calendar_empty_warning_pass"
            logger.error("No economic calendar data in database for live trade. Hard block.")
            return False, "economic_calendar_unavailable_blocked"

        calendar_age_hours = (now - latest_calendar_fetch).total_seconds() / 3600 if latest_calendar_fetch else 999.0

        # Check future coverage in DB (events within [-1h, +12h])
        future_coverage = (
            await session.execute(
                select(EconomicCalendar.id)
                .where(EconomicCalendar.event_time >= now - timedelta(hours=1))
                .where(EconomicCalendar.event_time <= now + timedelta(hours=12))
                .limit(1)
            )
        ).scalar_one_or_none()

        stale_warning = ""
        if calendar_age_hours > 8.0:
            if not is_paper:
                return (
                    False,
                    f"Economic calendar data is {calendar_age_hours:.1f}h stale (>8.0h limit). Live trade blocked.",
                )
            logger.warning(
                f"Economic calendar data is {calendar_age_hours:.1f}h old (threshold=8.0h). "
                f"Degraded mode: proceeding with warning instead of hard-block."
            )
            stale_warning = f" [WARNING: Calendar data is {calendar_age_hours:.1f}h old — degraded mode]"
        elif calendar_age_hours > 4.0:
            stale_warning = (
                f" [WARNING: Calendar data is {calendar_age_hours:.1f}h old — check upcoming events manually]"
            )

        # Check user-defined blacklisted events from UserPreference
        try:
            pref_stmt = select(UserPreference).where(
                UserPreference.is_active == True,
                (UserPreference.category == "event_blacklist") | (UserPreference.key == "event_blacklist"),
            )
            blacklists = (await session.execute(pref_stmt)).scalars().all()
            user_blacklisted_terms = []
            for pref in blacklists:
                try:
                    data = json.loads(pref.value_json)
                    if isinstance(data, list):
                        user_blacklisted_terms.extend([str(x).upper() for x in data])
                    elif isinstance(data, str):
                        user_blacklisted_terms.append(data.upper())
                except Exception:
                    if pref.value_json:
                        user_blacklisted_terms.append(str(pref.value_json).upper())

            if user_blacklisted_terms:
                user_blocked = (
                    (
                        await session.execute(
                            select(EconomicCalendar)
                            .where(EconomicCalendar.currency.in_(list(currencies)))
                            .where(EconomicCalendar.event_time >= now - window)
                            .where(EconomicCalendar.event_time <= now + window)
                        )
                    )
                    .scalars()
                    .all()
                )
                for ev in user_blocked:
                    if not ev.event_time:
                        continue
                    ev_name_upper = (ev.event_name or "").upper()
                    if any(term in ev_name_upper for term in user_blacklisted_terms):
                        delta = abs((ev.event_time - now).total_seconds() / 60)
                        return False, (
                            f"Event blacklisted by user preference: '{ev.event_name}' "
                            f"({ev.currency}) at {ev.event_time.strftime('%H:%M UTC')} "
                            f"(~{delta:.0f}min away, window={self.news_window_minutes}min)"
                            f"{stale_warning}"
                        )
        except Exception as e:
            logger.debug(f"[RiskGate] UserPreference blacklist check error: {e}")

        # Check for actual upcoming high-impact events
        upcoming = (
            await session.execute(
                select(EconomicCalendar)
                .where(EconomicCalendar.impact.in_(["high", "High", "HIGH"]))
                .where(EconomicCalendar.currency.in_(list(currencies)))
                .where(EconomicCalendar.event_time >= now - window)
                .where(EconomicCalendar.event_time <= now + window)
                .limit(1)
            )
        ).scalar_one_or_none()

        if upcoming is not None and upcoming.event_time is not None:
            delta = abs((upcoming.event_time - now).total_seconds() / 60)
            return False, (
                f"High-impact event within news window: '{upcoming.event_name}' "
                f"({upcoming.currency}) at {upcoming.event_time.strftime('%H:%M UTC')} "
                f"(~{delta:.0f}min away, window={self.news_window_minutes}min)"
                f"{stale_warning}"
            )

        return True, f"no high-impact events in window{stale_warning}"

    async def _check_schmitt_regime(
        self, session: AsyncSession, symbol: str, simulated_positions: list | None = None, is_backtest: bool = False
    ) -> tuple[bool, str]:
        """
        Check systemic correlation regime via Schmitt trigger.
        In FUSED regime: market contagion is high, cap concurrent positions to 2.
        """
        if is_backtest:
            return True, "schmitt_regime_backtest_exempt"
        try:
            from monika.domain.indicators.regime_detector import RegimeState, get_schmitt_regime_detector

            detector = get_schmitt_regime_detector()
            if detector.state == RegimeState.FUSED:
                open_count = (
                    await session.execute(select(func.count(Position.id)).where(Position.status == "open"))
                ).scalar_one_or_none() or 0
                if simulated_positions:
                    open_count += len(simulated_positions)
                if open_count >= 2:
                    return (
                        False,
                        f"Schmitt regime is FUSED (contagion density={detector.last_density:.2f}). Max 2 positions allowed (current={open_count})",
                    )
            return True, f"regime={detector.state.value} (density={detector.last_density:.2f})"
        except Exception as e:
            logger.warning(f"Schmitt regime check error: {e}")
            return False, f"schmitt_regime_check_failed: {e}"

    async def _check_vpin_toxicity(
        self, session: AsyncSession, symbol: str, as_of: datetime | None = None, is_backtest: bool = False
    ) -> tuple[bool, str]:
        """
        Check VPIN order flow toxicity for high-volatility assets (BTCUSD, XAUUSD).
        Blocks entry if VPIN > 0.75 (toxic informed order flow).
        """
        if is_backtest and as_of is None:
            return True, "vpin_check_backtest_exempt"
        try:
            from monika.domain.indicators.microstructure import VPIN_SYMBOLS

            if symbol.upper() not in VPIN_SYMBOLS:
                return True, f"{symbol} exempt from VPIN check"

            stmt = (
                select(TechnicalIndicator)
                .where(TechnicalIndicator.symbol == symbol)
                .where(TechnicalIndicator.indicator_name == "ORDER_FLOW_SNAPSHOT")
            )
            if as_of is not None:
                stmt = stmt.where(TechnicalIndicator.timestamp <= as_of)
            row = (
                await session.execute(stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1))
            ).scalar_one_or_none()

            if row and row.value_json:
                data = json.loads(row.value_json)
                vpin = data.get("vpin")
                if vpin is not None and float(vpin) > 0.75:
                    return False, f"VPIN order flow toxicity {vpin:.2f} > 0.75 threshold (adverse selection risk high)"
                return True, f"VPIN={vpin or 'n/a'} (clean flow)"
            return True, "VPIN check ok (no snapshot)"
        except Exception as e:
            logger.warning(f"VPIN toxicity check error: {e}")
            return False, f"vpin_check_failed: {e}"

    async def _check_adv_liquidity(
        self,
        session: AsyncSession,
        symbol: str,
        sizing: SizingResult,
        as_of: datetime | None = None,
        is_backtest: bool = False,
    ) -> tuple[bool, str]:
        """
        Subsystem 5: ADV (Average Daily Volume) liquidity floor.
        Blocks orders where proposed lot size exceeds institutional capacity
        (> 1.0% of 20-day Average Daily Volume) or during illiquid rollover windows.
        """
        now = as_of or clock.now()
        hour = now.hour
        # Illiquid daily rollover gap (21:55 - 22:15 UTC): wide spreads and empty books
        if (hour == 21 and now.minute >= 55) or (hour == 22 and now.minute <= 15):
            if sizing.recommended_lots > 0.5:
                return (
                    False,
                    f"Illiquid rollover window (21:55-22:15 UTC): lots={sizing.recommended_lots} exceeds 0.5 lot ceiling",
                )

        try:
            cutoff = now - timedelta(days=30)
            stmt = (
                select(PriceOHLCV.volume)
                .where(PriceOHLCV.symbol == symbol)
                .where(PriceOHLCV.timeframe.in_(["D1", "D", "1D"]))
                .where(PriceOHLCV.timestamp >= cutoff)
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(20)
            )
            rows = (await session.execute(stmt)).scalars().all()
            if rows and len(rows) >= 5:
                adv = float(sum(rows)) / len(rows)
                if not math.isfinite(adv) or adv <= 0:
                    return False, f"Non-finite or invalid ADV volume calculated for {symbol}: {adv}"
                if sizing.recommended_lots > (adv * 0.01):
                    return (
                        False,
                        f"Proposed volume {sizing.recommended_lots} lots exceeds 1.0% of 20-day ADV ({adv:.0f} units)",
                    )
        except Exception as e:
            logger.error(f"[{symbol}] ADV calculation failed: {e}")
            if not is_backtest:
                return False, f"ADV liquidity evaluation failed (fail-closed): {e}"

        return True, "ADV liquidity floor satisfied"


__all__ = ["RiskMarketChecksMixin"]
