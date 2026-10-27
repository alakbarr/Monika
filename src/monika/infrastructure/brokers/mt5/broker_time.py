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
_LIVE_TICK_VERIFIED: bool = False
_LAST_CONFIGURED_OFFSET_HOURS: Optional[float] = None


class BrokerTimeResolver:
    """Process-wide resolver for MT5 broker server time and canonical bar timestamps."""

    @classmethod
    def reset_cache(cls) -> None:
        """Reset process-wide cached broker offset state."""
        global _CACHED_OFFSET_SECONDS, _LAST_VALIDATED_AT, _LIVE_TICK_VERIFIED, _LAST_CONFIGURED_OFFSET_HOURS
        _CACHED_OFFSET_SECONDS = None
        _LAST_VALIDATED_AT = None
        _LIVE_TICK_VERIFIED = False
        _LAST_CONFIGURED_OFFSET_HOURS = None

    @classmethod
    def get_cached_offset_if_fresh(cls, settings: Optional[dict] = None) -> Optional[int]:
        """Return cached broker UTC offset in seconds if valid, fresh, and config-consistent."""
        if _CACHED_OFFSET_SECONDS is None or _LAST_VALIDATED_AT is None or not _LIVE_TICK_VERIFIED:
            return None
        now = datetime.now(timezone.utc)
        if (now - _LAST_VALIDATED_AT).total_seconds() >= 900:
            return None
        if isinstance(settings, dict):
            mt5_cfg = settings.get("trading", {}).get("mt5", {}) or settings.get("mt5", {})
            raw_val = mt5_cfg.get("broker_utc_offset_hours") if isinstance(mt5_cfg, dict) else None
            if raw_val is not None:
                try:
                    cfg_hours = float(raw_val)
                    if _LAST_CONFIGURED_OFFSET_HOURS is not None and cfg_hours != _LAST_CONFIGURED_OFFSET_HOURS:
                        return None
                    if int(cfg_hours * 3600) != _CACHED_OFFSET_SECONDS:
                        return None
                except ValueError, TypeError:
                    return None
        return _CACHED_OFFSET_SECONDS

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
        global _CACHED_OFFSET_SECONDS, _LAST_VALIDATED_AT, _LIVE_TICK_VERIFIED, _LAST_CONFIGURED_OFFSET_HOURS
        now = datetime.now(timezone.utc)

        if not force_refresh:
            fresh_cached = cls.get_cached_offset_if_fresh(settings)
            if fresh_cached is not None:
                return fresh_cached

        configured_hours = cls.get_configured_offset_hours(settings)
        offset_hours = configured_hours
        offset_sec = int(offset_hours * 3600)

        # Verify against live MT5 tick if extension is available and connected
        live_verified = False
        try:
            import MetaTrader5 as mt5_mod

            symbols_to_check = ["BTCUSD", "ETHUSD", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
            now_utc_ts = now.timestamp()
            for s in symbols_to_check:
                tick = mt5_mod.symbol_info_tick(s)
                tick_time = getattr(tick, "time", 0) if tick is not None else 0
                if isinstance(tick_time, (int, float)) and not isinstance(tick_time, bool) and tick_time > 0:
                    diff_s = float(tick_time) - now_utc_ts
                    live_offset_hours = round(diff_s / 3600.0)
                    residual_s = abs(diff_s - (live_offset_hours * 3600))
                    # Only validate against active ticks younger than 60s relative to their whole-hour broker offset
                    if -14 <= live_offset_hours <= 14 and residual_s < 60:
                        live_verified = True
                        if abs(live_offset_hours - offset_hours) >= 1.0:
                            logger.warning(
                                f"[BrokerTimeResolver] Clock skew / DST shift detected! Configured offset "
                                f"{offset_hours:+.1f}h differs from live tick ({live_offset_hours:+.1f}h, "
                                f"symbol={s}, residual={residual_s:.1f}s). Auto-adjusting to {live_offset_hours:+.1f}h."
                            )
                            offset_hours = float(live_offset_hours)
                            offset_sec = int(live_offset_hours * 3600)
                        break
        except Exception as e:
            logger.debug(f"[BrokerTimeResolver] Live tick check skipped/failed: {e}")

        prev_cached = _CACHED_OFFSET_SECONDS
        _CACHED_OFFSET_SECONDS = offset_sec
        _LAST_VALIDATED_AT = now
        _LIVE_TICK_VERIFIED = live_verified
        _LAST_CONFIGURED_OFFSET_HOURS = configured_hours
        if prev_cached != offset_sec or force_refresh:
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
            # Bar W1 di MT5 dibuka pada Minggu 00:00 broker time.
            # Dalam koordinat UTC (setelah dikurangi offset broker), bar pembuka minggu ini jatuh pada:
            # - Minggu (weekday 6): crypto atau broker UTC+0, maps ke Senin mendatang (+1 hari).
            # - Sabtu malam >= 20:00 UTC (weekday 5): broker UTC+2 s/d UTC+4, maps ke Senin mendatang (+2 hari).
            # - Hari kerja (Senin..Jumat): bar/tick berjalan pada minggu aktif, maps ke Senin minggu tersebut.
            # - Sabtu dini hari < 20:00 UTC: penutupan sesi Jumat, maps ke Senin minggu yang baru lewat.
            utc_dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            day = utc_dt.weekday()
            base_midnight = utc_dt.replace(hour=0, minute=0, second=0, microsecond=0)

            if day == 6:  # Sunday open -> upcoming Monday
                return base_midnight + timedelta(days=1)
            elif day == 5 and utc_dt.hour >= 20:  # Saturday night weekend open -> upcoming Monday
                return base_midnight + timedelta(days=2)
            elif day == 5 and utc_dt.hour < 20:  # Saturday early morning close -> current week's Monday
                return base_midnight - timedelta(days=5)
            else:  # Monday through Friday -> current week's Monday
                return base_midnight - timedelta(days=day)
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
