"""
Compatibility facade shim for legacy data_temporal_validator.py.
Re-exports from canonical monika.core.validation.data_temporal_validator.
"""

from __future__ import annotations

import monika.core.validation.data_temporal_validator as _canonical

from monika.core.validation.data_temporal_validator import (
    DataTemporalValidator,
)

__all__ = ['DataTemporalValidator']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
