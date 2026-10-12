"""
Compatibility facade shim for legacy model_capabilities.py.
Re-exports from canonical monika.infrastructure.llm.model_capabilities.
"""

from __future__ import annotations

import monika.infrastructure.llm.model_capabilities as _canonical

from monika.infrastructure.llm.model_capabilities import (
    ModelCapabilities,
    get_capabilities,
)

__all__ = ['ModelCapabilities', 'get_capabilities']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
