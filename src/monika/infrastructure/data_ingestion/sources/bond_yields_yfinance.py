# ==============================================================================
# File: data_sources/bond_yields_yfinance.py
# ==============================================================================
"""
Backward-compatible shim for data_sources.bond_yields_fetcher.
Renamed in Phase 4 Polish (L-6).
"""

from monika.infrastructure.data_ingestion.sources.bond_yields_fetcher import (
    ECB_AAA_YIELD_URL,
    FRED_BASE_URL,
    FRED_BOND_SERIES,
    BondYieldFetcher,
    logger,
)

__all__ = [
    "BondYieldFetcher",
    "ECB_AAA_YIELD_URL",
    "FRED_BASE_URL",
    "FRED_BOND_SERIES",
    "logger",
]
