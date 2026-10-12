"""
Compatibility facade shim for legacy common.py.
Re-exports from canonical monika.interfaces.dashboard.routes.common.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.common as _canonical

from monika.interfaces.dashboard.routes.common import (
    BatchCloseRequest,
    BulkBreakevenRequest,
    ClosePositionRequest,
    CrystallizeSkillRequest,
    DeprecateSkillRequest,
    ManualOrderPreviewRequest,
    ManualOrderSubmitRequest,
    ModifyPositionRequest,
    OverrideRiskRequest,
    SteerRequest,
    TrailingOverrideRequest,
    TriggerCycleRequest,
    broadcast_live_event,
    get_buffered_events_since,
    get_current_stream_seq,
    get_dashboard_dependency,
    logger,
    record_stream_event,
    set_dashboard_dependencies,
)

__all__ = ['BatchCloseRequest', 'BulkBreakevenRequest', 'ClosePositionRequest', 'CrystallizeSkillRequest', 'DeprecateSkillRequest', 'ManualOrderPreviewRequest', 'ManualOrderSubmitRequest', 'ModifyPositionRequest', 'OverrideRiskRequest', 'SteerRequest', 'TrailingOverrideRequest', 'TriggerCycleRequest', 'broadcast_live_event', 'get_buffered_events_since', 'get_current_stream_seq', 'get_dashboard_dependency', 'logger', 'record_stream_event', 'set_dashboard_dependencies']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
