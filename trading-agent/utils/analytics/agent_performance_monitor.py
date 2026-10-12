"""
Compatibility facade shim for legacy agent_performance_monitor.py.
Re-exports from canonical monika.core.analytics.agent_performance_monitor.
"""

from __future__ import annotations

import monika.core.analytics.agent_performance_monitor as _canonical

from monika.core.analytics.agent_performance_monitor import (
    compute_agent_accuracy_report,
    compute_agent_accuracy_report_multi_horizon,
    compute_dynamic_escalation_threshold,
    get_currency_confidence_ceiling,
)

__all__ = ['compute_agent_accuracy_report', 'compute_agent_accuracy_report_multi_horizon', 'compute_dynamic_escalation_threshold', 'get_currency_confidence_ceiling']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
