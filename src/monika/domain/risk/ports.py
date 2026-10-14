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
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


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
    strategy_factor_family_resolver: Any | None = None
    broker_client_factory: Any | None = None

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
        cls.strategy_factor_family_resolver = None
        cls.broker_client_factory = None


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
    """Dynamically resolves default regime classifier function without static application coupling."""
    if RiskPortRegistry.regime_classifier_fn is not None:
        return RiskPortRegistry.regime_classifier_fn
    try:
        import sys

        mod = sys.modules.get("monika.application.analysis.calculators.regime_classifier")
        if mod and hasattr(mod, "classify_market_regime"):
            return mod.classify_market_regime
        import importlib

        mod = importlib.import_module("monika.application.analysis.calculators.regime_classifier")
        return getattr(mod, "classify_market_regime", None)
    except Exception:
        return None


def register_timesfm_alpha_calculator(calc: Any) -> None:
    """Register TimesFM alpha calculator from application layer."""
    RiskPortRegistry.timesfm_alpha_calculator = calc


def get_default_timesfm_alpha_calculator() -> Any:
    """Dynamically resolves default TimesFM alpha calculator without static application coupling."""
    if RiskPortRegistry.timesfm_alpha_calculator is not None:
        return RiskPortRegistry.timesfm_alpha_calculator
    try:
        import sys

        mod = sys.modules.get("monika.application.analysis.calculators.timesfm_alpha")
        if mod and hasattr(mod, "TimesFMAlphaCalculator"):
            return mod.TimesFMAlphaCalculator
        import importlib

        mod = importlib.import_module("monika.application.analysis.calculators.timesfm_alpha")
        return getattr(mod, "TimesFMAlphaCalculator", None)
    except Exception:
        return None


def register_risk_hook_emitter(emitter: Any) -> None:
    """Register risk lifecycle hook emitter from application layer."""
    RiskPortRegistry.risk_hook_emitter = emitter


async def emit_risk_hook(hook_name: str, **kwargs: Any) -> None:
    """Safely emit a risk lifecycle hook without static application plugin coupling."""
    if RiskPortRegistry.risk_hook_emitter is not None:
        try:
            res = RiskPortRegistry.risk_hook_emitter(hook_name, **kwargs)
            import inspect

            if inspect.isawaitable(res):
                await res
        except Exception:
            pass
        return

    try:
        import sys

        mod = sys.modules.get("monika.application.plugins.manager.manager")
        if mod and hasattr(mod, "get_plugin_manager") and hasattr(mod, "PluginHook"):
            hook_enum = getattr(mod.PluginHook, hook_name, None)
            if hook_enum:
                pm = mod.get_plugin_manager()
                await pm.emit(hook_enum, **kwargs)
        else:
            import importlib

            mod = importlib.import_module("monika.application.plugins.manager.manager")
            hook_enum = getattr(mod.PluginHook, hook_name, None)
            if hook_enum:
                pm = mod.get_plugin_manager()
                await pm.emit(hook_enum, **kwargs)
    except Exception:
        pass


def register_adaptive_risk_policy_factory(factory: Any) -> None:
    """Register adaptive risk policy factory from application layer."""
    RiskPortRegistry.adaptive_risk_policy_factory = factory


def get_default_adaptive_risk_policy(settings: dict[str, Any] | None = None) -> Any:
    """Dynamically resolves default AdaptiveRiskPolicy instance without static coupling."""
    if RiskPortRegistry.adaptive_risk_policy_factory is not None:
        return RiskPortRegistry.adaptive_risk_policy_factory(settings=settings)
    try:
        import sys

        mod = sys.modules.get("monika.application.analysis.calculators.adaptive_policy")
        if mod and hasattr(mod, "AdaptiveRiskPolicy"):
            return mod.AdaptiveRiskPolicy(settings=settings)
        import importlib

        mod = importlib.import_module("monika.application.analysis.calculators.adaptive_policy")
        cls = getattr(mod, "AdaptiveRiskPolicy", None)
        return cls(settings=settings) if cls else None
    except Exception:
        return None


def register_evidence_store_factory(factory: Any) -> None:
    """Register evidence store factory from application layer."""
    RiskPortRegistry.evidence_store_factory = factory


def get_default_evidence_store() -> Any:
    """Dynamically resolves EvidenceStore instance without static application coupling."""
    if RiskPortRegistry.evidence_store_factory is not None:
        return RiskPortRegistry.evidence_store_factory()
    try:
        import sys

        mod = sys.modules.get("monika.application.analysis.strategies.evidence_store")
        if mod and hasattr(mod, "EvidenceStore"):
            return mod.EvidenceStore()
        import importlib

        mod = importlib.import_module("monika.application.analysis.strategies.evidence_store")
        cls = getattr(mod, "EvidenceStore", None)
        return cls() if cls else None
    except Exception:
        return None


def register_copula_tail_risk_fitter(fitter: Any) -> None:
    """Register Archimedean copula tail risk fitting function from application layer."""
    RiskPortRegistry.copula_tail_risk_fitter = fitter


def get_default_copula_tail_risk_fitter() -> Any:
    """Dynamically resolves fit_clayton_copula without static application coupling."""
    if RiskPortRegistry.copula_tail_risk_fitter is not None:
        return RiskPortRegistry.copula_tail_risk_fitter
    try:
        import sys

        mod = sys.modules.get("monika.application.analysis.calculators.copula_tail_risk")
        if mod and hasattr(mod, "fit_clayton_copula"):
            return mod.fit_clayton_copula
        import importlib

        mod = importlib.import_module("monika.application.analysis.calculators.copula_tail_risk")
        return getattr(mod, "fit_clayton_copula", None)
    except Exception:
        return None


def register_strategy_factor_family_resolver(resolver: Any) -> None:
    """Register strategy factor family resolver from application layer."""
    RiskPortRegistry.strategy_factor_family_resolver = resolver


def get_strategy_factor_family(strategy_id: str | None) -> str:
    """Resolves factor family for given strategy id without static StrategyRegistry import."""
    if RiskPortRegistry.strategy_factor_family_resolver is not None:
        return str(RiskPortRegistry.strategy_factor_family_resolver(strategy_id))
    try:
        import sys

        mod = sys.modules.get("monika.application.analysis.strategies.registry")
        if mod and hasattr(mod, "StrategyRegistry"):
            strat_cls = mod.StrategyRegistry.get_strategy(strategy_id) if strategy_id else None
            return str(getattr(strat_cls, "factor_family", "trend")) if strat_cls else "trend"
        import importlib

        mod = importlib.import_module("monika.application.analysis.strategies.registry")
        reg = getattr(mod, "StrategyRegistry", None)
        strat_cls = reg.get_strategy(strategy_id) if (reg and strategy_id) else None
        return str(getattr(strat_cls, "factor_family", "trend")) if strat_cls else "trend"
    except Exception:
        return "trend"


def register_broker_client_factory(factory: Any) -> None:
    """Register factory providing broker client implementation to domain risk."""
    RiskPortRegistry.broker_client_factory = factory


def get_default_broker_client(settings: Any | None = None) -> Any:
    """Dynamically resolves default broker client without static coupling."""
    if RiskPortRegistry.broker_client_factory is not None:
        return RiskPortRegistry.broker_client_factory(settings)
    try:
        import sys

        mod = sys.modules.get("monika.application.execution.broker_registry")
        if mod and hasattr(mod, "get_broker"):
            broker_name = (
                settings.get("broker", {}).get("active_broker", "mt5") if isinstance(settings, dict) else "mt5"
            )
            return mod.get_broker(broker_name)
        import importlib

        mod = importlib.import_module("monika.application.execution.broker_registry")
        get_broker_fn = getattr(mod, "get_broker", None)
        if get_broker_fn is not None:
            broker_name = (
                settings.get("broker", {}).get("active_broker", "mt5") if isinstance(settings, dict) else "mt5"
            )
            return get_broker_fn(broker_name)
    except Exception:
        pass
    return None
