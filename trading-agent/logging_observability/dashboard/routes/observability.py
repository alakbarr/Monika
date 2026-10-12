"""
Compatibility facade shim for legacy observability.py.
Re-exports from canonical monika.interfaces.dashboard.routes.observability.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.observability as _canonical

from monika.interfaces.dashboard.routes.observability import (
    get_cycle_decision_lineage,
    get_cycle_trace_summary,
    get_graph_state,
    get_playbook_tree,
    get_prompt_cache_metrics,
    get_tool_latencies,
    get_trace_tree,
    get_traces,
    get_trade_trajectories,
    logger,
    observability_router,
)

__all__ = ['get_cycle_decision_lineage', 'get_cycle_trace_summary', 'get_graph_state', 'get_playbook_tree', 'get_prompt_cache_metrics', 'get_tool_latencies', 'get_trace_tree', 'get_traces', 'get_trade_trajectories', 'logger', 'observability_router']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
