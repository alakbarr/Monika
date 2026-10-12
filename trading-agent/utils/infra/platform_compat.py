"""
Compatibility facade shim for legacy platform_compat.py.
Re-exports from canonical monika.infrastructure.infra.platform_compat.
"""

from __future__ import annotations

import monika.infrastructure.infra.platform_compat as _canonical

from monika.infrastructure.infra.platform_compat import (
    configure_event_loop,
    get_loop_factory,
    normalize_path,
    safe_subprocess_run,
)

__all__ = ['configure_event_loop', 'get_loop_factory', 'normalize_path', 'safe_subprocess_run']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
