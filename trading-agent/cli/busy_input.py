"""
Compatibility facade shim for legacy busy_input.py.
Re-exports from canonical monika.interfaces.cli.busy_input.
"""

from __future__ import annotations

import monika.interfaces.cli.busy_input as _canonical

from monika.interfaces.cli.busy_input import (
    BusyInputBuffer,
    InputDelivery,
)

__all__ = ['BusyInputBuffer', 'InputDelivery']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
