# ==============================================================================
# File: interfaces/dashboard/routes/trading_endpoints/__init__.py
# Description: Modular Trading Sub-Routers Aggregation & Exports
# ==============================================================================

"""
Subpackage grouping modular trading routes by domain.
"""

from __future__ import annotations

from fastapi import APIRouter

from monika.interfaces.dashboard.routes.trading_endpoints.actions import (
    action_approve_trade,
    action_emergency_kill,
    action_kill_symbol,
    action_pause_trading,
    action_resume_trading,
    action_steer,
    action_trigger_cycle,
    action_unsuspend_symbols,
    actions_router,
)
from monika.interfaces.dashboard.routes.trading_endpoints.analysis import (
    analysis_router,
    get_analysis,
    get_debate_outcomes,
    get_decision_distribution,
    get_decision_dossier,
    get_mt5_signals,
    get_trade_triggers,
)
from monika.interfaces.dashboard.routes.trading_endpoints.market_data import (
    get_market_candles,
    get_market_structure_levels,
    get_technical_indicators_snapshot,
    market_data_router,
)
from monika.interfaces.dashboard.routes.trading_endpoints.orders import (
    get_orders,
    orders_router,
    preview_manual_order,
    submit_manual_order,
)
from monika.interfaces.dashboard.routes.trading_endpoints.overview import (
    get_activity,
    get_analysis_quality_realtime,
    get_edge_metrics,
    get_factor_analysis,
    get_overview,
    get_paper_trading_stats,
    get_ssvp_health,
    overview_router,
)
from monika.interfaces.dashboard.routes.trading_endpoints.positions import (
    action_bulk_breakeven,
    action_close_batch,
    action_close_position,
    action_position_breakeven,
    action_trailing_override,
    get_positions,
    modify_position,
    positions_router,
)
from monika.interfaces.dashboard.routes.trading_endpoints.risk import (
    action_override_risk,
    get_risk,
    get_risk_correlation_matrix,
    get_risk_scorecard,
    risk_router,
)

trading_router = APIRouter()
trading_router.include_router(overview_router)
trading_router.include_router(positions_router)
trading_router.include_router(orders_router)
trading_router.include_router(risk_router)
trading_router.include_router(analysis_router)
trading_router.include_router(actions_router)
trading_router.include_router(market_data_router)

__all__ = [
    "trading_router",
    "overview_router",
    "positions_router",
    "orders_router",
    "risk_router",
    "analysis_router",
    "actions_router",
    "market_data_router",
    # Overview
    "get_overview",
    "get_paper_trading_stats",
    "get_activity",
    "get_factor_analysis",
    "get_edge_metrics",
    "get_analysis_quality_realtime",
    "get_ssvp_health",
    # Positions
    "get_positions",
    "action_close_position",
    "action_position_breakeven",
    "action_bulk_breakeven",
    "action_trailing_override",
    "action_close_batch",
    "modify_position",
    # Orders
    "get_orders",
    "preview_manual_order",
    "submit_manual_order",
    # Risk
    "get_risk",
    "get_risk_scorecard",
    "get_risk_correlation_matrix",
    "action_override_risk",
    # Analysis
    "get_analysis",
    "get_decision_dossier",
    "get_decision_distribution",
    "get_debate_outcomes",
    "get_mt5_signals",
    "get_trade_triggers",
    # Actions
    "action_trigger_cycle",
    "action_steer",
    "action_kill_symbol",
    "action_emergency_kill",
    "action_resume_trading",
    "action_pause_trading",
    "action_unsuspend_symbols",
    "action_approve_trade",
    # Market data
    "get_technical_indicators_snapshot",
    "get_market_structure_levels",
    "get_market_candles",
]
