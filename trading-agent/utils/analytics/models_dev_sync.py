"""
Compatibility facade shim for legacy models_dev_sync.py.
Re-exports from canonical monika.core.analytics.models_dev_sync.
"""

from __future__ import annotations

import monika.core.analytics.models_dev_sync as _canonical

from monika.core.analytics.models_dev_sync import (
    API_URL,
    CACHE_PATH,
    CACHE_TTL_SECONDS,
    ModelsDevSync,
)

__all__ = ['API_URL', 'CACHE_PATH', 'CACHE_TTL_SECONDS', 'ModelsDevSync']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
