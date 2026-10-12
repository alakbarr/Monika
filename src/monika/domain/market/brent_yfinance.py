"""
Backward-compatibility re-export shim for brent_yfinance.
Canonical location: data_sources.brent_yfinance
"""

from data_sources.brent_yfinance import get_brent_price

__all__ = ["get_brent_price"]
