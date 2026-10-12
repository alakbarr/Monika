"""
Compatibility facade shim for legacy trading.py.
Re-exports from canonical monika.interfaces.dashboard.routes.trading.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.trading as _canonical

from monika.interfaces.dashboard.routes.trading import (
    action_approve_trade,
    action_bulk_breakeven,
    action_close_batch,
    action_close_position,
    action_emergency_kill,
    action_kill_symbol,
    action_override_risk,
    action_pause_trading,
    action_position_breakeven,
    action_resume_trading,
    action_steer,
    action_trailing_override,
    action_trigger_cycle,
    action_unsuspend_symbols,
    get_activity,
    get_analysis,
    get_analysis_quality_realtime,
    get_debate_outcomes,
    get_decision_distribution,
    get_decision_dossier,
    get_edge_metrics,
    get_factor_analysis,
    get_market_candles,
    get_market_structure_levels,
    get_mt5_signals,
    get_orders,
    get_overview,
    get_paper_trading_stats,
    get_positions,
    get_risk,
    get_risk_correlation_matrix,
    get_risk_scorecard,
    get_ssvp_health,
    get_technical_indicators_snapshot,
    get_trade_triggers,
    logger,
    modify_position,
    preview_manual_order,
    submit_manual_order,
    trading_router,
)

__all__ = ['action_approve_trade', 'action_bulk_breakeven', 'action_close_batch', 'action_close_position', 'action_emergency_kill', 'action_kill_symbol', 'action_override_risk', 'action_pause_trading', 'action_position_breakeven', 'action_resume_trading', 'action_steer', 'action_trailing_override', 'action_trigger_cycle', 'action_unsuspend_symbols', 'get_activity', 'get_analysis', 'get_analysis_quality_realtime', 'get_debate_outcomes', 'get_decision_distribution', 'get_decision_dossier', 'get_edge_metrics', 'get_factor_analysis', 'get_market_candles', 'get_market_structure_levels', 'get_mt5_signals', 'get_orders', 'get_overview', 'get_paper_trading_stats', 'get_positions', 'get_risk', 'get_risk_correlation_matrix', 'get_risk_scorecard', 'get_ssvp_health', 'get_technical_indicators_snapshot', 'get_trade_triggers', 'logger', 'modify_position', 'preview_manual_order', 'submit_manual_order', 'trading_router']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
