"""
Compatibility facade shim for legacy bond_yields_yfinance.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.bond_yields_yfinance.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.bond_yields_yfinance as _canonical

__all__: list[str] = getattr(_canonical, '__all__', [a for a in dir(_canonical) if not a.startswith('_')])

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
