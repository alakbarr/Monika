"""
Compatibility facade shim for legacy api.py.
Re-exports from canonical monika.interfaces.dashboard.api.
"""

from __future__ import annotations

import monika.interfaces.dashboard.api as _canonical

from monika.interfaces.dashboard.api import (
    app,
    logger,
    run_dashboard,
    run_dashboard_async,
    serve_setup_page,
    submit_setup_configuration,
    verify_api_key,
)

__all__ = ['app', 'logger', 'run_dashboard', 'run_dashboard_async', 'serve_setup_page', 'submit_setup_configuration', 'verify_api_key']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
