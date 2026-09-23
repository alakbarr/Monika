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


@dataclass
class OrderRequest:
    """
    Decoupled Domain Data Transfer Object for order placement.
    Eliminates tight coupling to SQLAlchemy ORM models in broker layer.
    """
    symbol: str
    direction: str  # 'buy' or 'sell'
    volume: float
    order_type: str = "MARKET"
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    comment: str = ""
    magic: int = 0
    client_order_id: Optional[str] = None
    id: Optional[Any] = None
    mt5_ticket: Optional[int] = None
    filled_volume: float = 0.0
    created_at: Optional[Any] = None

    @property
    def requested_volume(self) -> float:
        return self.volume

    @property
    def requested_price(self) -> Optional[float]:
        return self.price


def normalize_order_request(order: Any) -> OrderRequest:
    """
    Convert any order representation (OrderRequest, ORM Order, dict) into standard OrderRequest.
    """
    if isinstance(order, OrderRequest):
        return order
    if isinstance(order, dict):
        return OrderRequest(
            symbol=order.get("symbol", ""),
            direction=order.get("direction", "buy"),
            volume=float(order.get("volume", order.get("requested_volume", 0.01))),
            order_type=str(order.get("order_type", "MARKET")).upper(),
            price=order.get("price", order.get("requested_price")),
            sl=order.get("sl", order.get("stop_loss")),
            tp=order.get("tp", order.get("take_profit")),
            comment=order.get("comment", ""),
            magic=int(order.get("magic", 0)),
            client_order_id=order.get("client_order_id", order.get("id")),
            id=order.get("id", order.get("client_order_id")),
            mt5_ticket=order.get("mt5_ticket", order.get("ticket")),
            filled_volume=float(order.get("filled_volume", 0.0)),
            created_at=order.get("created_at"),
        )
    symbol = getattr(order, "symbol", "")
    direction = str(getattr(order, "direction", "buy"))
    volume = getattr(order, "requested_volume", None) or getattr(order, "volume", 0.01)
    order_type = getattr(order, "order_type", "MARKET")
    if hasattr(order_type, "value"):
        order_type = order_type.value
    price = getattr(order, "requested_price", None) or getattr(order, "price", None)
    sl = getattr(order, "stop_loss", None) or getattr(order, "sl", None)
    tp = getattr(order, "take_profit", None) or getattr(order, "tp", None)
    comment = getattr(order, "comment", "")
    magic = getattr(order, "magic", 0)
    client_order_id = getattr(order, "client_order_id", None) or getattr(order, "id", None)
    order_id = getattr(order, "id", None) or client_order_id
    ticket = getattr(order, "mt5_ticket", None) or getattr(order, "ticket", None)
    filled = getattr(order, "filled_volume", 0.0) or 0.0
    created = getattr(order, "created_at", None)

    return OrderRequest(
        symbol=symbol,
        direction=direction,
        volume=float(volume),
        order_type=str(order_type).upper(),
        price=float(price) if price is not None else None,
        sl=float(sl) if sl is not None else None,
        tp=float(tp) if tp is not None else None,
        comment=str(comment),
        magic=int(magic),
        client_order_id=str(client_order_id) if client_order_id is not None else None,
        id=order_id,
        mt5_ticket=ticket,
        filled_volume=float(filled),
        created_at=created,
    )


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
