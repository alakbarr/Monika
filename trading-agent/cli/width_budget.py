"""
Compatibility facade shim for legacy width_budget.py.
Re-exports from canonical monika.interfaces.cli.width_budget.
"""

from __future__ import annotations

import monika.interfaces.cli.width_budget as _canonical

from monika.interfaces.cli.width_budget import (
    ColumnSpec,
    compute_progressive_width_budget,
)

__all__ = ['ColumnSpec', 'compute_progressive_width_budget']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
