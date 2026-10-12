"""
Compatibility facade shim for legacy deferred_dispatcher.py.
Re-exports from canonical monika.infrastructure.llm.deferred_dispatcher.
"""

from __future__ import annotations

import monika.infrastructure.llm.deferred_dispatcher as _canonical

from monika.infrastructure.llm.deferred_dispatcher import (
    DeferredLLMDispatcher,
    DeferredRequest,
    DeferredResult,
    DispatchMode,
)

__all__ = ['DeferredLLMDispatcher', 'DeferredRequest', 'DeferredResult', 'DispatchMode']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
