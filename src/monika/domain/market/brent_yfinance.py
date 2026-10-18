"""
Backward-compatibility re-export shim for brent_yfinance.
Canonical location: monika.infrastructure.data_ingestion.sources.brent_yfinance
"""

from typing import Any, Callable, Optional

_brent_price_fn: Optional[Callable[..., Any]] = None


def register_brent_price_fn(fn: Callable[..., Any]) -> None:
    global _brent_price_fn, get_brent_price
    _brent_price_fn = fn
    get_brent_price = fn


def get_brent_price(*args: Any, **kwargs: Any) -> Any:
    """Fetch Brent crude price using registered provider or loaded module."""
    if _brent_price_fn is not None:
        return _brent_price_fn(*args, **kwargs)
    import sys

    mod = sys.modules.get("monika.infrastructure.data_ingestion.sources.brent_yfinance")
    if mod and hasattr(mod, "get_brent_price"):
        fn = getattr(mod, "get_brent_price")
        register_brent_price_fn(fn)
        return fn(*args, **kwargs)
    raise RuntimeError("No brent price function registered")


__all__ = ["get_brent_price", "register_brent_price_fn"]
