# ==============================================================================
# File: utils/market/direction.py
# ==============================================================================

"""
Market Direction Normalization Utility.
Enforces strict lowercase ('buy' | 'sell') representation across the entire system.
"""

from typing import Optional


def normalize_direction(direction: Optional[str]) -> str:
    """
    Normalize trade direction string to lowercase ('buy' or 'sell').
    Raises ValueError if input is invalid or cannot be recognized.
    """
    d = (direction or "").strip().lower()
    if d in ("buy", "long"):
        return "buy"
    if d in ("sell", "short"):
        return "sell"
    raise ValueError(f"Invalid market direction: {direction!r}. Expected 'buy' or 'sell'.")


def is_valid_direction(direction: Optional[str]) -> bool:
    """Check if direction is a valid trade direction without raising an exception."""
    try:
        normalize_direction(direction)
        return True
    except (ValueError, TypeError):
        return False
