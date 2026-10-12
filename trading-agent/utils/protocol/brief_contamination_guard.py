"""
Compatibility facade shim for legacy brief_contamination_guard.py.
Re-exports from canonical monika.application.protocol.brief_contamination_guard.
"""

from __future__ import annotations

import monika.application.protocol.brief_contamination_guard as _canonical

from monika.application.protocol.brief_contamination_guard import (
    BriefContaminationGuard,
    func_abs,
)

__all__ = ['BriefContaminationGuard', 'func_abs']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
