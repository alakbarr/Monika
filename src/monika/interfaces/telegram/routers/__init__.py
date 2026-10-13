"""
Modular Telegram Sub-Routers for Command Handling and Dispatch.
"""

from monika.interfaces.telegram.routers.admin_router import AdminRouter
from monika.interfaces.telegram.routers.market_router import MarketRouter
from monika.interfaces.telegram.routers.quant_router import QuantRouter
from monika.interfaces.telegram.routers.risk_router import RiskRouter
from monika.interfaces.telegram.routers.trading_router import TradingRouter

__all__ = [
    "TradingRouter",
    "RiskRouter",
    "MarketRouter",
    "QuantRouter",
    "AdminRouter",
]
