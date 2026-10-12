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

