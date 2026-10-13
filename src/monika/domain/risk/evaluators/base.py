# ==============================================================================
# File: domain/risk/evaluators/base.py
# ==============================================================================

"""
Base typing and model resolution infrastructure for modular RiskGate check mixins.
Provides dynamic database model resolution, trading day cutoff helpers, and static attribute declarations.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple



from monika.domain.models_resolver import resolve_model


def get_trading_day_start(settings: dict, now: datetime | None = None) -> datetime:
    """
    Menghitung waktu mulai hari perdagangan berdasarkan broker daily rollover.
    Default: 21:00 UTC (17:00 New York / NY Close), aware terhadap Daylight Saving Time.
    """
    if now is None:
        from monika.core.primitives.clock import now as get_clock_now

        now = get_clock_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    risk_cfg = (settings or {}).get("trading", {}).get("risk", {})
    rollover_hour_cfg = risk_cfg.get("daily_rollover_utc_hour")

    # 1. Jika konfigurasi eksplisit jam 0 (midnight UTC)
    if rollover_hour_cfg is not None and int(rollover_hour_cfg) == 0:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 2. Broker Timezone Dynamic Calculation (Default: America/New_York at 17:00 Close)
    broker_tz_name = risk_cfg.get("broker_timezone", "America/New_York")
    broker_rollover_hour = int(risk_cfg.get("broker_rollover_hour", 17))

    try:
        import zoneinfo

        tz = zoneinfo.ZoneInfo(broker_tz_name)
        now_tz = now.astimezone(tz)
        if now_tz.hour >= broker_rollover_hour:
            tz_start = now_tz.replace(hour=broker_rollover_hour, minute=0, second=0, microsecond=0)
        else:
            tz_start = (now_tz - timedelta(days=1)).replace(
                hour=broker_rollover_hour, minute=0, second=0, microsecond=0
            )
        return tz_start.astimezone(UTC)
    except Exception:
        rollover_hour = int(rollover_hour_cfg if rollover_hour_cfg is not None else 21)
        if now.hour >= rollover_hour:
            return now.replace(hour=rollover_hour, minute=0, second=0, microsecond=0)
        else:
            yesterday = now - timedelta(days=1)
            return yesterday.replace(hour=rollover_hour, minute=0, second=0, microsecond=0)


def get_daily_risk_cutoff(now: datetime, risk_cfg: dict) -> datetime:
    """Helper alias untuk get_trading_day_start dengan parameter (now, risk_cfg)."""
    return get_trading_day_start({"trading": {"risk": risk_cfg}}, now)


class _RiskGateMixinBase:
    """
    Type-checking base class for RiskGate evaluators.
    Attributes are only declared during static analysis.
    At runtime, this class is an empty lightweight base.
    """

    if TYPE_CHECKING:
        settings: Dict[str, Any]
        max_daily_drawdown_pct: float
        max_concurrent: int
        correlation_limit: int
        news_window_minutes: int
        max_risk_pct: float
        _mt5: Any
        flash_crash_detector: Any
        dynamic_correlation_matrix: Any



__all__ = ["_RiskGateMixinBase", "resolve_model", "get_trading_day_start", "get_daily_risk_cutoff"]
