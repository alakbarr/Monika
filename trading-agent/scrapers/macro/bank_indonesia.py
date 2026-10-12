"""
Compatibility facade shim for legacy bank_indonesia.py.
Re-exports from canonical monika.infrastructure.data_ingestion.scrapers.macro.bank_indonesia.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.scrapers.macro.bank_indonesia as _canonical

from monika.infrastructure.data_ingestion.scrapers.macro.bank_indonesia import (
    BankIndonesiaFetcher,
    logger,
)

__all__ = ['BankIndonesiaFetcher', 'logger']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
