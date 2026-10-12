"""
Compatibility facade shim for legacy worktree.py.
Re-exports from canonical monika.core.primitives.worktree.
"""

from __future__ import annotations

import monika.core.primitives.worktree as _canonical

from monika.core.primitives.worktree import (
    SubagentWorktree,
    logger,
)

__all__ = ['SubagentWorktree', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
