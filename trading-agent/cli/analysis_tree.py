"""
Compatibility facade shim for legacy analysis_tree.py.
Re-exports from canonical monika.interfaces.cli.analysis_tree.
"""

from __future__ import annotations

import monika.interfaces.cli.analysis_tree as _canonical

from monika.interfaces.cli.analysis_tree import (
    AnalysisCycleTree,
)

__all__ = ['AnalysisCycleTree']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
