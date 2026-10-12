"""
Compatibility facade shim for legacy prompt_disciplines.py.
Re-exports from canonical monika.infrastructure.llm.prompt_disciplines.
"""

from __future__ import annotations

import monika.infrastructure.llm.prompt_disciplines as _canonical

from monika.infrastructure.llm.prompt_disciplines import (
    UNIVERSAL_EXECUTION_DISCIPLINE,
    get_universal_execution_discipline,
)

__all__ = ['UNIVERSAL_EXECUTION_DISCIPLINE', 'get_universal_execution_discipline']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
