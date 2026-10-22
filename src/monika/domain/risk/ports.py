# ==============================================================================
# File: domain/risk/ports.py
# ==============================================================================

"""
Domain Risk Ports & Protocols.

Defines pure abstract interfaces for risk data aggregation, account querying,
and instrument specification lookup, strictly isolated from concrete database
implementations (Clean Architecture Dependency Inversion Principle).
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class RiskDataProviderProtocol(Protocol):
    """
    Pure domain protocol for retrieving historical data, open positions,
    account equity, loss streaks, and configuration required by RiskGate.
    """

    async def get_open_positions(
        self,
        is_paper: bool = False,
        session: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Return list of active open positions as standardized dictionary records."""
        ...

    async def get_account_equity_and_balance(
        self,
        is_paper: bool = False,
        session: Any | None = None,
    ) -> tuple[float, float]:
        """Return (equity, balance) in account base currency (USD)."""
        ...

    async def get_daily_trades_count(
        self,
        symbol: str | None = None,
        is_paper: bool = False,
        session: Any | None = None,
    ) -> int:
        """Return number of executed trades for today."""
        ...

    async def get_recent_drawdown(
        self,
        is_paper: bool = False,
        session: Any | None = None,
    ) -> float:
        """Return current intraday drawdown percentage relative to peak equity."""
        ...

    async def get_recent_vix(
        self,
        session: Any | None = None,
    ) -> float | None:
        """Return latest available VIX index level."""
        ...

    async def get_system_config_value(
        self,
        key: str,
        default: Any = None,
        session: Any | None = None,
    ) -> Any:
        """Retrieve dynamic configuration override by key."""
        ...

    async def get_user_preference(
        self,
        key: str,
        default: Any = None,
        session: Any | None = None,
    ) -> Any:
        """Retrieve user configuration preference value."""
        ...

    async def get_recent_price_bars(
        self,
        symbol: str,
        timeframe: str = "H1",
        limit: int = 100,
        session: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve OHLCV price bars for volatility, correlation, or indicator checks."""
        ...

    async def get_loss_streak(
        self,
        is_paper: bool = False,
        session: Any | None = None,
    ) -> int:
        """Return count of consecutive realized losses."""
        ...

    async def get_economic_calendar_events(
        self,
        start_time: datetime,
        end_time: datetime,
        currencies: list[str] | None = None,
        session: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve high and medium impact economic calendar events in time window."""
        ...

    async def get_latest_timesfm_forecast(
        self,
        symbol: str,
        timeframe: str = "H1",
        max_age_hours: float = 8.0,
        session: Any | None = None,
        as_of: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Retrieve most recent cached TimesFM forecast quantiles for symbol."""
        ...

    async def get_latest_risk_state(
        self,
        session: Any | None = None,
    ) -> dict[str, Any] | None:
        """Retrieve latest recorded RiskState row as a dictionary."""
        ...

    async def record_risk_state(
        self,
        payload: dict[str, Any],
        session: Any | None = None,
    ) -> None:
        """Persist or update current daily RiskState metrics."""
        ...

    async def set_system_config_value(
        self,
        key: str,
        value: Any,
        session: Any | None = None,
    ) -> None:
        """Update or insert a dynamic configuration value."""
        ...

    async def get_conflicting_order(
        self,
        symbol: str,
        session: Any | None = None,
    ) -> dict[str, Any] | None:
        """Retrieve any pending or submitted order for symbol to prevent double submission."""
        ...

    async def get_recent_stop_losses(
        self,
        symbol: str,
        window_minutes: int = 60,
        session: Any | None = None,
    ) -> int:
        """Count realized stop-loss hits in the last window_minutes for cooldown."""
        ...

    async def get_symbol_closes(
        self,
        symbols: list[str],
        timeframe: str = "H1",
        limit: int = 100,
        session: Any | None = None,
    ) -> dict[str, list[float]]:
        """Retrieve closing prices series for multiple symbols for correlation calculation."""
        ...


@runtime_checkable
class InstrumentRegistryProtocol(Protocol):
    """
    Protocol for looking up instrument trading specifications (tick value, min lots, step).
    """

    def get_instrument_spec(self, symbol: str) -> dict[str, Any] | None:
        """Return trading specification dict for symbol or None if unlisted."""
        ...


@runtime_checkable
class ApprovalTransportProtocol(Protocol):
    """
    Protocol for cryptographic sealing and transport verification of approval requests.
    """

    def seal_request(self, payload: dict[str, Any]) -> str:
        """Create deterministic tamper-proof signature or token for approval payload."""
        ...

    def verify_decision(self, request_payload: dict[str, Any], token: str) -> bool:
        """Verify authenticity and integrity of approved decision token."""
        ...


class RiskPortRegistry:
    """Centralized, resettable registry for domain risk pluggable providers and callbacks."""

    risk_data_provider_factory: Any | None = None
    regime_classifier_fn: Any | None = None
    timesfm_alpha_calculator: Any | None = None
    risk_hook_emitter: Any | None = None
    adaptive_risk_policy_factory: Any | None = None
    evidence_store_factory: Any | None = None
    copula_tail_risk_fitter: Any | None = None
    evt_tail_calculator: Any | None = None
    strategy_factor_family_resolver: Any | None = None
    broker_client_factory: Any | None = None
    suspended_symbols_provider: Any | None = None
    event_publisher: Any | None = None
    notifier: Any | None = None
    session_factory: Any | None = None
    data_freshness_validator: Any | None = None

    @classmethod
    def reset(cls) -> None:
        """Reset all registered factories and hooks to default None state (for tests)."""
        cls.risk_data_provider_factory = None
        cls.regime_classifier_fn = None
        cls.timesfm_alpha_calculator = None
        cls.risk_hook_emitter = None
        cls.adaptive_risk_policy_factory = None
        cls.evidence_store_factory = None
        cls.copula_tail_risk_fitter = None
        cls.evt_tail_calculator = None
        cls.strategy_factor_family_resolver = None
        cls.broker_client_factory = None
        cls.suspended_symbols_provider = None
        cls.event_publisher = None
        cls.notifier = None
        cls.session_factory = None
        cls.data_freshness_validator = None


def register_data_freshness_validator(validator: Any) -> None:
    """Register market data freshness validator callable."""
    RiskPortRegistry.data_freshness_validator = validator


def get_default_data_freshness_validator() -> Any:
    """Returns registered market data freshness validator or None."""
    return RiskPortRegistry.data_freshness_validator


def register_suspended_symbols_provider(provider: Any) -> None:
    """Register provider for querying/clearing suspended trading symbols."""
    RiskPortRegistry.suspended_symbols_provider = provider


def get_default_suspended_symbols_provider() -> Any:
    """Returns registered suspended symbols provider or None."""
    return RiskPortRegistry.suspended_symbols_provider


def register_risk_data_provider_factory(factory: Any) -> None:
    """Register concrete RiskDataProvider factory from infrastructure layer."""
    RiskPortRegistry.risk_data_provider_factory = factory


def get_default_risk_data_provider(
    settings: dict[str, Any] | None = None,
    session: Any | None = None,
) -> Any:
    """Resolves default RiskDataProvider registered by infrastructure layer."""
    if RiskPortRegistry.risk_data_provider_factory is not None:
        return RiskPortRegistry.risk_data_provider_factory(session=session, settings=settings)
    return None


def register_regime_classifier(fn: Any) -> None:
    """Register market regime classification provider from application layer."""
    RiskPortRegistry.regime_classifier_fn = fn


def get_default_regime_classifier() -> Any:
    """Returns registered default regime classifier function or None."""
    return RiskPortRegistry.regime_classifier_fn


class DefaultTimesFMAlphaCalculator:
    """Default domain fallback for TimesFM Quantile Asymmetry Skew Alpha Calculator."""

    BULLISH_THRESHOLD: float = 1.35
    BEARISH_THRESHOLD: float = 0.75

    @classmethod
    def calculate_skew_from_quantiles(
        cls, quantiles: dict[str, Any], current_price: float | None = None
    ) -> dict[str, Any]:
        if not quantiles:
            return {"valid": False, "reason": "No quantiles provided"}
        try:
            q10_raw = quantiles.get("q10")
            q50_raw = quantiles.get("q50")
            q90_raw = quantiles.get("q90")
            if q10_raw is None or q50_raw is None or q90_raw is None:
                return {"valid": False, "reason": "Missing required quantiles (q10, q50, q90)"}
            q10 = float(q10_raw[-1] if isinstance(q10_raw, (list, tuple)) else q10_raw)
            q50 = float(q50_raw[-1] if isinstance(q50_raw, (list, tuple)) else q50_raw)
            q90 = float(q90_raw[-1] if isinstance(q90_raw, (list, tuple)) else q90_raw)
            if not (q10 <= q50 <= q90):
                return {"valid": False, "reason": f"Non-monotonic quantiles: q10={q10}, q50={q50}, q90={q90}"}
            upper = max(0.0, q90 - q50)
            lower = max(0.0, q50 - q10)
            skew = float(upper / lower) if lower >= 1e-8 else (2.5 if upper > 1e-8 else 1.0)
            if skew >= cls.BULLISH_THRESHOLD:
                bias = "BULLISH_EXPANSION"
                confidence = min(0.95, 0.50 + (skew - cls.BULLISH_THRESHOLD) * 0.3)
            elif skew <= cls.BEARISH_THRESHOLD:
                bias = "BEARISH_EXPANSION"
                confidence = min(0.95, 0.50 + (cls.BEARISH_THRESHOLD - skew) * 0.5)
            else:
                bias = "SYMMETRIC_NEUTRAL"
                confidence = 0.50
            return {
                "valid": True,
                "skew_ratio": round(skew, 3),
                "bias": bias,
                "confidence": round(confidence, 2),
                "q10": round(q10, 5),
                "q50": round(q50, 5),
                "q90": round(q90, 5),
            }
        except Exception as e:
            return {"valid": False, "reason": str(e)}

    @classmethod
    def get_sizing_multiplier(cls, alpha_result: dict[str, Any], direction: str) -> float:
        if not alpha_result or not alpha_result.get("valid"):
            return 1.0
        bias = alpha_result.get("bias", "SYMMETRIC_NEUTRAL")
        dir_clean = (direction or "").strip().upper()
        if dir_clean == "BUY":
            if bias == "BULLISH_EXPANSION":
                return 1.15
            elif bias == "BEARISH_EXPANSION":
                return 0.80
        elif dir_clean == "SELL":
            if bias == "BEARISH_EXPANSION":
                return 1.15
            elif bias == "BULLISH_EXPANSION":
                return 0.80
        return 1.0


def register_timesfm_alpha_calculator(calc: Any) -> None:
    """Register TimesFM alpha calculator from application layer."""
    RiskPortRegistry.timesfm_alpha_calculator = calc


def get_default_timesfm_alpha_calculator() -> Any:
    """Returns registered default TimesFM alpha calculator or domain fallback."""
    return RiskPortRegistry.timesfm_alpha_calculator or DefaultTimesFMAlphaCalculator


def register_evt_tail_calculator(calc: Any) -> None:
    """Register EVT tail risk calculator from application layer."""
    RiskPortRegistry.evt_tail_calculator = calc


def get_default_evt_tail_calculator() -> Any:
    """Returns registered default EVT tail calculator or None."""
    return RiskPortRegistry.evt_tail_calculator


def register_risk_hook_emitter(emitter: Any) -> None:
    """Register risk lifecycle hook emitter from application layer."""
    RiskPortRegistry.risk_hook_emitter = emitter


async def emit_risk_hook(hook_name: str, **kwargs: Any) -> None:
    """Safely emit a risk lifecycle hook via registered emitter."""
    if RiskPortRegistry.risk_hook_emitter is not None:
        try:
            res = RiskPortRegistry.risk_hook_emitter(hook_name, **kwargs)
            import inspect

            if inspect.isawaitable(res):
                await res
        except Exception:
            logger.exception("Error emitting risk lifecycle hook '%s'", hook_name)


def register_adaptive_risk_policy_factory(factory: Any) -> None:
    """Register adaptive risk policy factory from application layer."""
    RiskPortRegistry.adaptive_risk_policy_factory = factory


def get_default_adaptive_risk_policy(settings: dict[str, Any] | None = None) -> Any:
    """Returns registered default AdaptiveRiskPolicy instance or None."""
    if RiskPortRegistry.adaptive_risk_policy_factory is not None:
        return RiskPortRegistry.adaptive_risk_policy_factory(settings=settings)
    return None


def register_evidence_store_factory(factory: Any) -> None:
    """Register evidence store factory from application layer."""
    RiskPortRegistry.evidence_store_factory = factory


def get_default_evidence_store() -> Any:
    """Returns registered EvidenceStore instance or None."""
    if RiskPortRegistry.evidence_store_factory is not None:
        return RiskPortRegistry.evidence_store_factory()
    return None


def register_copula_tail_risk_fitter(fitter: Any) -> None:
    """Register Archimedean copula tail risk fitting function from application layer."""
    RiskPortRegistry.copula_tail_risk_fitter = fitter


def get_default_copula_tail_risk_fitter() -> Any:
    """Returns registered fit_clayton_copula or None."""
    return RiskPortRegistry.copula_tail_risk_fitter


def register_strategy_factor_family_resolver(resolver: Any) -> None:
    """Register strategy factor family resolver from application layer."""
    RiskPortRegistry.strategy_factor_family_resolver = resolver


def get_strategy_factor_family(strategy_id: str | None) -> str:
    """Resolves factor family for given strategy id via registered resolver."""
    if RiskPortRegistry.strategy_factor_family_resolver is not None:
        return str(RiskPortRegistry.strategy_factor_family_resolver(strategy_id))
    return "trend"


def register_broker_client_factory(factory: Any) -> None:
    """Register factory providing broker client implementation to domain risk."""
    RiskPortRegistry.broker_client_factory = factory


def get_default_broker_client(settings: Any | None = None) -> Any:
    """Returns registered default broker client or None."""
    if RiskPortRegistry.broker_client_factory is not None:
        return RiskPortRegistry.broker_client_factory(settings)
    return None


def register_event_publisher(publisher: Any) -> None:
    """Register domain event publisher implementation."""
    RiskPortRegistry.event_publisher = publisher


def get_default_event_publisher() -> Any:
    """Returns registered event publisher or None."""
    return RiskPortRegistry.event_publisher


def register_notifier(notifier: Any) -> None:
    """Register domain emergency notifier implementation."""
    RiskPortRegistry.notifier = notifier


def get_default_notifier() -> Any:
    """Returns registered notifier or None."""
    notifier = RiskPortRegistry.notifier
    if notifier is not None:
        if isinstance(notifier, type) or (callable(notifier) and not hasattr(notifier, "send_critical")):
            try:
                return notifier()
            except Exception:
                pass
        return notifier
    return None


def register_session_factory(factory: Any) -> None:
    """Register database session factory for domain risk state queries."""
    RiskPortRegistry.session_factory = factory


def get_default_session_factory() -> Any:
    """Returns registered database session factory or None."""
    return RiskPortRegistry.session_factory
