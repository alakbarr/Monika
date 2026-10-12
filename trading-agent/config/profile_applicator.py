"""
Compatibility facade shim for legacy profile_applicator.py.
Re-exports from canonical monika.core.config.profile_applicator.
"""

from __future__ import annotations

import monika.core.config.profile_applicator as _canonical

from monika.core.config.profile_applicator import (
    ALL_49_ROLES,
    ALL_TASK_ROLES,
    PROFILE_METADATA,
    ProfileApplicator,
    logger,
)

__all__ = ['ALL_49_ROLES', 'ALL_TASK_ROLES', 'PROFILE_METADATA', 'ProfileApplicator', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
