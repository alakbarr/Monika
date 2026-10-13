# ==============================================================================
# File: interfaces/dashboard/routes/trading.py
# Description: Trading, Positions, Orders, Analysis, and Control Endpoints Facade
# ==============================================================================

"""
Backward-compatible facade for Dashboard Trading routes.

All endpoint handlers have been modularized under:
monika.interfaces.dashboard.routes.trading_endpoints/
"""

from __future__ import annotations

from monika.interfaces.dashboard.routes.trading_endpoints import *
from monika.interfaces.dashboard.routes.trading_endpoints import actions as actions
from monika.interfaces.dashboard.routes.trading_endpoints import analysis as analysis
from monika.interfaces.dashboard.routes.trading_endpoints import market_data as market_data
from monika.interfaces.dashboard.routes.trading_endpoints import orders as orders
from monika.interfaces.dashboard.routes.trading_endpoints import overview as overview
from monika.interfaces.dashboard.routes.trading_endpoints import positions as positions
from monika.interfaces.dashboard.routes.trading_endpoints import risk as risk
from monika.interfaces.dashboard.routes.trading_endpoints import trading_router
