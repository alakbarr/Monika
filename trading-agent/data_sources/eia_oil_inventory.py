"""
Compatibility facade shim for legacy eia_oil_inventory.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.eia_oil_inventory.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.eia_oil_inventory as _canonical

from monika.infrastructure.data_ingestion.sources.eia_oil_inventory import (
    EIAInventoryFetcher,
    EIA_URL,
    logger,
)

__all__ = ['EIAInventoryFetcher', 'EIA_URL', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
