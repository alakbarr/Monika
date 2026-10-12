"""
Compatibility facade shim for legacy __init__.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.macro.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.macro as _canonical

__all__: list[str] = getattr(_canonical, '__all__', [a for a in dir(_canonical) if not a.startswith('_')])

# Preserve package __path__ so submodule shims can be resolved
if hasattr(_canonical, '__path__'):
    for _p in _canonical.__path__:
        if _p not in __path__:
            __path__.append(_p)

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
