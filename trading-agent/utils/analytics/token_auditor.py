"""
Compatibility facade shim for legacy token_auditor.py.
Re-exports from canonical monika.core.analytics.token_auditor.
"""

from __future__ import annotations

import monika.core.analytics.token_auditor as _canonical

from monika.core.analytics.token_auditor import (
    TokenAuditor,
)

__all__ = ['TokenAuditor']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
