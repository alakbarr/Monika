"""
Compatibility facade shim for legacy system.py.
Re-exports from canonical monika.interfaces.dashboard.routes.system.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.system as _canonical

from monika.interfaces.dashboard.routes.system import (
    get_auth_role,
    get_brief,
    get_gemini_quota,
    get_health,
    get_health_diagnostics,
    get_metrics,
    get_vix,
    logger,
    ping,
    router,
    system_router,
)

__all__ = ['get_auth_role', 'get_brief', 'get_gemini_quota', 'get_health', 'get_health_diagnostics', 'get_metrics', 'get_vix', 'logger', 'ping', 'router', 'system_router']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
