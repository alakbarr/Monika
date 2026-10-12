"""Type stubs for ib_insync package."""
from typing import Any, List, Optional

class Contract:
    symbol: str
    conId: int

class Forex(Contract):
    def __init__(self, pair: str, *args: Any, **kwargs: Any) -> None: ...

class CFD(Contract):
    def __init__(self, symbol: str, exchange: str = ..., currency: str = ..., *args: Any, **kwargs: Any) -> None: ...

class Crypto(Contract):
    def __init__(self, symbol: str, exchange: str = ..., currency: str = ..., *args: Any, **kwargs: Any) -> None: ...

class Stock(Contract):
    def __init__(self, symbol: str, exchange: str = ..., currency: str = ..., *args: Any, **kwargs: Any) -> None: ...

class Order:
    orderId: int
    action: str
    totalQuantity: float

class MarketOrder(Order):
    def __init__(self, action: str, totalQuantity: float, *args: Any, **kwargs: Any) -> None: ...

class LimitOrder(Order):
    def __init__(self, action: str, totalQuantity: float, lmtPrice: float, *args: Any, **kwargs: Any) -> None: ...

class StopOrder(Order):
    def __init__(self, action: str, totalQuantity: float, stopPrice: float, *args: Any, **kwargs: Any) -> None: ...

class Trade:
    contract: Contract
    order: Order
    orderStatus: Any

class Position:
    account: str
    contract: Contract
    position: float
    avgCost: float

class AccountValue:
    tag: str
    value: str

class Ticker:
    bid: float
    ask: float
    last: float
    time: Any

class IB:
    def __init__(self) -> None: ...
    def isConnected(self) -> bool: ...
    async def connectAsync(self, host: str, port: int, clientId: int, timeout: float = ...) -> Any: ...
    def managedAccounts(self) -> List[str]: ...
    def disconnect(self) -> None: ...
    async def qualifyContractsAsync(self, *contracts: Any) -> List[Any]: ...
    def reqMktData(self, contract: Any, genericTickList: str = ..., snapshot: bool = ..., regulatorySnapshot: bool = ...) -> Ticker: ...
    def placeOrder(self, contract: Any, order: Order) -> Trade: ...
    def cancelOrder(self, order: Order) -> Any: ...
    def openTrades(self) -> List[Trade]: ...
    def positions(self) -> List[Position]: ...
    def accountSummary(self, account: str = ...) -> List[AccountValue]: ...
