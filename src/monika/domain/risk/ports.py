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
        session: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of active open positions as standardized dictionary records."""
        ...

    async def get_account_equity_and_balance(
        self,
        is_paper: bool = False,
        session: Optional[Any] = None,
    ) -> Tuple[float, float]:
        """Return (equity, balance) in account base currency (USD)."""
        ...

    async def get_daily_trades_count(
        self,
        symbol: Optional[str] = None,
        is_paper: bool = False,
        session: Optional[Any] = None,
    ) -> int:
        """Return number of executed trades for today."""
        ...

    async def get_recent_drawdown(
        self,
        is_paper: bool = False,
        session: Optional[Any] = None,
    ) -> float:
        """Return current intraday drawdown percentage relative to peak equity."""
        ...

    async def get_recent_vix(
        self,
        session: Optional[Any] = None,
    ) -> Optional[float]:
        """Return latest available VIX index level."""
        ...

    async def get_system_config_value(
        self,
        key: str,
        default: Any = None,
        session: Optional[Any] = None,
    ) -> Any:
        """Retrieve dynamic configuration override by key."""
        ...

    async def get_user_preference(
        self,
        key: str,
        default: Any = None,
        session: Optional[Any] = None,
    ) -> Any:
        """Retrieve user configuration preference value."""
        ...

    async def get_recent_price_bars(
        self,
        symbol: str,
        timeframe: str = "H1",
        limit: int = 100,
        session: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve OHLCV price bars for volatility, correlation, or indicator checks."""
        ...

    async def get_loss_streak(
        self,
        is_paper: bool = False,
        session: Optional[Any] = None,
    ) -> int:
        """Return count of consecutive realized losses."""
        ...

    async def get_economic_calendar_events(
        self,
        start_time: datetime,
        end_time: datetime,
        currencies: Optional[List[str]] = None,
        session: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve high and medium impact economic calendar events in time window."""
        ...

    async def get_latest_timesfm_forecast(
        self,
        symbol: str,
        timeframe: str = "H1",
        max_age_hours: float = 8.0,
        session: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve most recent cached TimesFM forecast quantiles for symbol."""
        ...

    async def get_latest_risk_state(
        self,
        session: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve latest recorded RiskState row as a dictionary."""
        ...

    async def record_risk_state(
        self,
        payload: Dict[str, Any],
        session: Optional[Any] = None,
    ) -> None:
        """Persist or update current daily RiskState metrics."""
        ...

    async def set_system_config_value(
        self,
        key: str,
        value: Any,
        session: Optional[Any] = None,
    ) -> None:
        """Update or insert a dynamic configuration value."""
        ...

    async def get_conflicting_order(
        self,
        symbol: str,
        session: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve any pending or submitted order for symbol to prevent double submission."""
        ...

    async def get_recent_stop_losses(
        self,
        symbol: str,
        window_minutes: int = 60,
        session: Optional[Any] = None,
    ) -> int:
        """Count realized stop-loss hits in the last window_minutes for cooldown."""
        ...

    async def get_symbol_closes(
        self,
        symbols: List[str],
        timeframe: str = "H1",
        limit: int = 100,
        session: Optional[Any] = None,
    ) -> Dict[str, List[float]]:
        """Retrieve closing prices series for multiple symbols for correlation calculation."""
        ...


@runtime_checkable
class InstrumentRegistryProtocol(Protocol):
    """
    Protocol for looking up instrument trading specifications (tick value, min lots, step).
    """

    def get_instrument_spec(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return trading specification dict for symbol or None if unlisted."""
        ...


@runtime_checkable
class ApprovalTransportProtocol(Protocol):
    """
    Protocol for cryptographic sealing and transport verification of approval requests.
    """

    def seal_request(self, payload: Dict[str, Any]) -> str:
        """Create deterministic tamper-proof signature or token for approval payload."""
        ...

    def verify_decision(self, request_payload: Dict[str, Any], token: str) -> bool:
        """Verify authenticity and integrity of approved decision token."""
        ...


_risk_data_provider_factory: Optional[Any] = None


def register_risk_data_provider_factory(factory: Any) -> None:
    """Register concrete RiskDataProvider factory from infrastructure layer."""
    global _risk_data_provider_factory
    _risk_data_provider_factory = factory


def get_default_risk_data_provider(
    settings: Optional[Dict[str, Any]] = None,
    session: Optional[Any] = None,
) -> Any:
    """Dynamically resolves default RiskDataProvider without static infrastructure coupling."""
    global _risk_data_provider_factory
    if _risk_data_provider_factory is not None:
        return _risk_data_provider_factory(session=session, settings=settings)

    # Dynamic fallback resolution
    try:
        import sys
        mod = sys.modules.get("monika.infrastructure.database.repositories.risk_repository")
        if mod and hasattr(mod, "SqlAlchemyRiskRepository"):
            return mod.SqlAlchemyRiskRepository(session=session, settings=settings)
        import importlib
        mod = importlib.import_module("monika.infrastructure.database.repositories.risk_repository")
        repo_cls = getattr(mod, "SqlAlchemyRiskRepository")
        return repo_cls(session=session, settings=settings)
    except Exception:
        return None

