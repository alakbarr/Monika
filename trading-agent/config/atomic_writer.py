"""
Compatibility facade shim for legacy atomic_writer.py.
Re-exports from canonical monika.core.config.atomic_writer.
"""

from __future__ import annotations

import monika.core.config.atomic_writer as _canonical

from monika.core.config.atomic_writer import (
    AtomicConfigWriter,
    RE_LEADING_ZERO,
    RE_SEXAGESIMAL,
    RE_YAML_SPECIAL,
    logger,
)

__all__ = ['AtomicConfigWriter', 'RE_LEADING_ZERO', 'RE_SEXAGESIMAL', 'RE_YAML_SPECIAL', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
