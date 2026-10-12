"""
Compatibility facade shim for legacy sparklines.py.
Re-exports from canonical monika.interfaces.cli.sparklines.
"""

from __future__ import annotations

import monika.interfaces.cli.sparklines as _canonical

from monika.interfaces.cli.sparklines import (
    BRAILLE_BASE,
    bar_gauge,
    braille_sparkline,
)

__all__ = ['BRAILLE_BASE', 'bar_gauge', 'braille_sparkline']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
