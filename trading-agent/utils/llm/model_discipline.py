"""
Compatibility facade shim for legacy model_discipline.py.
Re-exports from canonical monika.infrastructure.llm.model_discipline.
"""

from __future__ import annotations

import monika.infrastructure.llm.model_discipline as _canonical

from monika.infrastructure.llm.model_discipline import (
    TOOL_USE_ENFORCEMENT_GUIDANCE,
    TOOL_USE_ENFORCEMENT_MODELS,
    TRADING_VERIFICATION_GUIDANCE,
    TRADING_VERIFICATION_MODELS,
    get_model_discipline,
)

__all__ = ['TOOL_USE_ENFORCEMENT_GUIDANCE', 'TOOL_USE_ENFORCEMENT_MODELS', 'TRADING_VERIFICATION_GUIDANCE', 'TRADING_VERIFICATION_MODELS', 'get_model_discipline']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
