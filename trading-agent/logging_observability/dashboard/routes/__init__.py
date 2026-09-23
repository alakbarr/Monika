# ==============================================================================
# File: logging_observability/dashboard/routes/__init__.py
# Description: Router Aggregation and Exports for Dashboard API
# ==============================================================================

from logging_observability.dashboard.routes.common import (
    ClosePositionRequest,
    CrystallizeSkillRequest,
    DeprecateSkillRequest,
    ModifyPositionRequest,
    OverrideRiskRequest,
    SteerRequest,
    TriggerCycleRequest,
    _active_websockets,
    _dependencies,
    _get_settings_path,
    _safe_json,
    _start_time,
    broadcast_live_event,
    get_dashboard_dependency,
    set_dashboard_dependencies,
)
from logging_observability.dashboard.routes.config import config_router
from logging_observability.dashboard.routes.observability import (
    _build_graph_state_for_cycle,
    observability_router,
)
from logging_observability.dashboard.routes.system import system_router
from logging_observability.dashboard.routes.tokens import tokens_router
from logging_observability.dashboard.routes.trading import trading_router
from logging_observability.dashboard.routes.websocket import websocket_router
from logging_observability.dashboard.routes.trace_search import trace_search_router
from logging_observability.dashboard.routes.backtest import backtest_router
from logging_observability.dashboard.routes.memory import memory_router
from logging_observability.dashboard.routes.intelligence import intelligence_router

all_routers = [
    system_router,
    tokens_router,
    config_router,
    trading_router,
    trace_search_router,
    observability_router,
    websocket_router,
    backtest_router,
    memory_router,
    intelligence_router,
]

__all__ = [
    "system_router",
    "tokens_router",
    "config_router",
    "trading_router",
    "observability_router",
    "websocket_router",
    "trace_search_router",
    "backtest_router",
    "memory_router",
    "intelligence_router",
    "all_routers",
    "set_dashboard_dependencies",
    "get_dashboard_dependency",
    "broadcast_live_event",
    "_safe_json",
    "_dependencies",
    "_active_websockets",
    "_start_time",
    "_get_settings_path",
    "_build_graph_state_for_cycle",
    "TriggerCycleRequest",
    "OverrideRiskRequest",
    "ClosePositionRequest",
    "ModifyPositionRequest",
    "DeprecateSkillRequest",
    "CrystallizeSkillRequest",
    "SteerRequest",
]
