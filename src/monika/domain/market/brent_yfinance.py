"""
Backward-compatibility re-export shim for brent_yfinance.
Canonical location: monika.infrastructure.data_ingestion.sources.brent_yfinance
"""

from typing import Any

get_brent_price: Any


def __getattr__(name: str) -> Any:
    if name == "get_brent_price":
        import importlib

        mod = importlib.import_module("monika.infrastructure.data_ingestion.sources.brent_yfinance")
        return getattr(mod, "get_brent_price")
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = ["get_brent_price"]
