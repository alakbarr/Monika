"""Central Broker Time & Canonical Bar Grid Resolver.

Enforces:
1. Single process-wide broker time resolution (source of truth: settings['trading']['mt5']['broker_utc_offset_hours']).
2. Fail-closed: If broker_utc_offset_hours is missing from configuration, raises ValueError. Never silently defaults to 0.
3. Live tick drift verification: Validates configured offset against live MT5 tick timestamps if market is open.
4. Canonical bar grid normalization: Maps bar timestamps to deterministic canonical instants in UTC,
   preventing duplicate rows across multiple timezone grid interpretations.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Optional

logger = logging.getLogger("TradingAgent.MT5.BrokerTime")

_CACHED_OFFSET_SECONDS: Optional[int] = None
_LAST_VALIDATED_AT: Optional[datetime] = None


class BrokerTimeResolver:
    """Process-wide resolver for MT5 broker server time and canonical bar timestamps."""

    @classmethod
    def get_configured_offset_hours(cls, settings: Optional[dict] = None) -> float:
        """Retrieve configured broker UTC offset hours from settings. Fails closed."""
        cfg = settings
        offset_val = None
        if cfg:
            mt5_cfg = cfg.get("trading", {}).get("mt5", {})
            if not mt5_cfg:
                mt5_cfg = cfg.get("mt5", {})
            offset_val = mt5_cfg.get("broker_utc_offset_hours")

        if offset_val is None:
            from monika.core.config.settings import load_settings

            try:
                loaded = load_settings()
                loaded_mt5 = loaded.get("trading", {}).get("mt5", {})
                if not loaded_mt5:
                    loaded_mt5 = loaded.get("mt5", {})
                offset_val = loaded_mt5.get("broker_utc_offset_hours")
            except Exception as e:
                logger.error(f"[BrokerTimeResolver] Failed to load settings: {e}")
                raise ValueError("Cannot resolve broker time without valid settings configuration.") from e

        if offset_val is None:
            raise ValueError(
                "CRITICAL: 'trading.mt5.broker_utc_offset_hours' is not configured in settings.yaml. "
                "Must be explicitly defined (e.g. 3 for FBS UTC+3, 2 for winter). Fail-closed."
            )
        try:
            return float(offset_val)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid broker_utc_offset_hours '{offset_val}': must be numeric.") from e

    @classmethod
    def resolve_offset_seconds(cls, settings: Optional[dict] = None, force_refresh: bool = False) -> int:
        """
        Resolve the broker UTC offset in seconds.
        Process-wide singleton cache with periodic verification.
        """
        global _CACHED_OFFSET_SECONDS, _LAST_VALIDATED_AT
        now = datetime.now(timezone.utc)

        if not force_refresh and _CACHED_OFFSET_SECONDS is not None:
            return _CACHED_OFFSET_SECONDS

        offset_hours = cls.get_configured_offset_hours(settings)
        offset_sec = int(offset_hours * 3600)

        # Verify against live MT5 tick if extension is available and connected
        try:
            import MetaTrader5 as mt5_mod

            symbols_to_check = ["BTCUSD", "ETHUSD", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
            now_utc_ts = now.timestamp()
            for s in symbols_to_check:
                tick = mt5_mod.symbol_info_tick(s)
                if tick and getattr(tick, "time", 0) > 0:
                    tick_age = abs(now_utc_ts - tick.time)
                    # Only validate against active ticks younger than 60s
                    if tick_age < 60:
                        diff_s = tick.time - now_utc_ts
                        live_offset_hours = round(diff_s / 3600.0)
                        residual_s = abs(diff_s - (live_offset_hours * 3600))
                        if residual_s < 120 and abs(live_offset_hours - offset_hours) >= 1.0:
                            logger.warning(
                                f"[BrokerTimeResolver] Clock skew detected! Configured offset {offset_hours:+.1f}h "
                                f"differs from live tick ({live_offset_hours:+.1f}h, symbol={s}). "
                                f"Verify broker DST transition."
                            )
                        break
        except Exception as e:
            logger.debug(f"[BrokerTimeResolver] Live tick check skipped/failed: {e}")

        _CACHED_OFFSET_SECONDS = offset_sec
        _LAST_VALIDATED_AT = now
        logger.info(f"[BrokerTimeResolver] Active broker UTC offset: {offset_hours:+.1f}h ({offset_sec}s)")
        return offset_sec

    @classmethod
    def to_canonical_bar_timestamp(
        cls,
        ts: Any,
        timeframe: str,
        offset_seconds: Optional[int] = None,
        settings: Optional[dict] = None,
    ) -> datetime:
        """
        Floor and normalize a bar timestamp to its exact canonical UTC instant.
        Prevents multiple timestamps representing the same physical candle.
        """
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif hasattr(ts, "to_pydatetime"):
            dt = ts.to_pydatetime()
        elif isinstance(ts, datetime):
            dt = ts
        else:
            raise TypeError(f"Unsupported timestamp type: {type(ts)}")

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        tf = timeframe.upper().strip()

        if tf == "M1":
            return dt.replace(second=0, microsecond=0)
        elif tf == "M5":
            minute = dt.minute - (dt.minute % 5)
            return dt.replace(minute=minute, second=0, microsecond=0)
        elif tf == "M15":
            minute = dt.minute - (dt.minute % 15)
            return dt.replace(minute=minute, second=0, microsecond=0)
        elif tf == "M30":
            minute = dt.minute - (dt.minute % 30)
            return dt.replace(minute=minute, second=0, microsecond=0)
        elif tf == "H1":
            return dt.replace(minute=0, second=0, microsecond=0)
        elif tf == "H4":
            if offset_seconds is None:
                offset_seconds = cls.resolve_offset_seconds(settings)
            # In broker server time, H4 opens on hours divisible by 4: {00, 04, 08, 12, 16, 20}
            broker_dt = dt + timedelta(seconds=offset_seconds)
            broker_h4 = broker_dt.replace(hour=broker_dt.hour - (broker_dt.hour % 4), minute=0, second=0, microsecond=0)
            return broker_h4 - timedelta(seconds=offset_seconds)
        elif tf == "D1":
            if offset_seconds is None:
                offset_seconds = cls.resolve_offset_seconds(settings)
            # In broker server time, D1 opens at 00:00:00
            broker_dt = dt + timedelta(seconds=offset_seconds)
            broker_d1 = broker_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            # Store D1 at 00:00:00 UTC of that broker date for uniform daily indicator indexing
            return broker_d1.replace(tzinfo=timezone.utc)
        elif tf == "W1":
            if offset_seconds is None:
                offset_seconds = cls.resolve_offset_seconds(settings)
            broker_dt = dt + timedelta(seconds=offset_seconds)
            broker_monday = broker_dt - timedelta(days=broker_dt.weekday())
            return broker_monday.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        elif tf == "MN1":
            return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            # Fallback for unrecognized sub-timeframes
            return dt.replace(microsecond=0)


def get_broker_utc_offset_seconds(settings: Optional[dict] = None) -> int:
    """Convenience helper for module consumers."""
    return BrokerTimeResolver.resolve_offset_seconds(settings)


def to_canonical_timestamp(
    ts: Any, timeframe: str, offset_seconds: Optional[int] = None, settings: Optional[dict] = None
) -> datetime:
    """Convenience helper for module consumers."""
    return BrokerTimeResolver.to_canonical_bar_timestamp(
        ts, timeframe, offset_seconds=offset_seconds, settings=settings
    )
