# ==============================================================================
# File: execution/broker_plugin.py
# ==============================================================================

"""
Unified Broker Plugin Interface & Standard Data Transfer Objects (DTO).
Enables zero-leakage platform neutrality across MT5, Paper Trading, Remote Gateways, and Crypto exchanges.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional

from harness.contract import TradingPlugin, PluginCategory, PluginMetadata


class ExitReason(str, Enum):
    SL_HIT = "SL_HIT"
    TP_HIT = "TP_HIT"
    MANUAL_CLOSE = "MANUAL_CLOSE"
    KILL_SWITCH = "KILL_SWITCH"
    EXPIRED = "EXPIRED"
    DEGRADED_EMERGENCY = "DEGRADED_EMERGENCY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TickData:
    symbol: str
    bid: float
    ask: float
    last: float
    spread: float
    time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    contract_size: float = 100000.0
    pip_size: float = 0.0001
    min_lot: float = 0.01
    max_lot: float = 50.0
    lot_step: float = 0.01
    stops_level_pips: float = 0.0
    margin_rate: float = 1.0


@dataclass(frozen=True)
class PositionData:
    ticket: int
    symbol: str
    direction: str  # 'buy' or 'sell'
    volume: float
    open_price: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    pnl: float = 0.0
    opened_at: Optional[datetime] = None
    magic: int = 0
    comment: str = ""
    is_paper: bool = False


@dataclass(frozen=True)
class DealData:
    ticket: int
    order_id: str
    symbol: str
    direction: str
    volume: float
    price: float
    profit: float
    exit_reason: ExitReason = ExitReason.UNKNOWN
    time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class AccountInfo:
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: float
    currency: str = "USD"


class BrokerPlugin(TradingPlugin, ABC):
    """
    Standard interface for all Broker & Execution plugins in Monika.
    """
    metadata: PluginMetadata

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, "metadata"):
            self.metadata.category = PluginCategory.BROKER

    @abstractmethod
    async def connect(self) -> bool:
        """Establish session with broker terminal, gateway, or paper engine."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect and clean up broker resources."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check active connectivity status."""
        pass

    @abstractmethod
    async def ensure_connected(self) -> bool:
        """Auto-reconnect if connection dropped."""
        pass

    @abstractmethod
    async def get_tick(self, symbol: str) -> Optional[TickData]:
        """Fetch latest live quote for symbol."""
        pass

    @abstractmethod
    async def get_symbol_spec(self, symbol: str) -> InstrumentSpec:
        """Fetch broker contract specifications."""
        pass

    @abstractmethod
    async def get_open_positions(self, symbol: Optional[str] = None) -> List[PositionData]:
        """Fetch current open positions."""
        pass

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Fetch account balance, equity, and margin levels."""
        pass

    @abstractmethod
    async def submit_order(self, order: Any, **kwargs) -> Dict[str, Any]:
        """Submit a new market or pending order."""
        pass

    @abstractmethod
    async def cancel_order(self, client_order_id: str, ticket: Optional[int] = None) -> bool:
        """Cancel a pending order."""
        pass

    @abstractmethod
    async def modify_position(self, ticket: int, sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        """Modify stop loss or take profit for an open position."""
        pass

    @abstractmethod
    async def close_position(self, ticket: int, lots: Optional[float] = None) -> Dict[str, Any]:
        """Close an active position."""
        pass

    @abstractmethod
    async def close_all_positions(self, comment: str = "KillSwitch") -> Dict[str, Any]:
        """Emergency liquidate all open positions."""
        pass
