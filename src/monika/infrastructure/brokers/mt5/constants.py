"""
Constants, priority levels, error classes, and symbol/timeframe utilities for MT5.
"""

import logging
from typing import Any

from monika.core.exceptions import BrokerConnectionError

logger = logging.getLogger("TradingAgent.MT5")

# Priority constants for asyncio PriorityQueue worker pattern
PRIORITY_CRITICAL = 0  # Emergency, kill-switch, order execution (place, modify, close)
PRIORITY_STANDARD = 5  # Ticks, account info, open positions, spread
PRIORITY_NORMAL = PRIORITY_STANDARD  # Alias for standard priority tasks
PRIORITY_BACKGROUND = 10  # Bulk historical rates (get_rates, copy_rates_range)

# MT5 timeframe string -> MT5 constant mapping
# Populated lazily on first connect to avoid import-time mt5 init
TIMEFRAME_MAP: dict[str, int] = {}


class MT5ProfileMismatchError(BrokerConnectionError):
    """Raised when the connected MT5 terminal login or trade mode does not match configured expectations."""

    pass


_BROKER_SYMBOL_CACHE: dict[str, str] = {}


def _resolve_broker_symbol(symbol: str) -> str:
    """
    Resolves broker-specific symbol name with prefix/suffix handling.
    Example: EURUSD -> EURUSDm, EURUSD.pro, EURUSD.raw, EURUSD+
    Caches results in memory for high-frequency low-latency execution.
    """
    clean_sym = symbol.strip().upper()
    if clean_sym in _BROKER_SYMBOL_CACHE:
        return _BROKER_SYMBOL_CACHE[clean_sym]

    try:
        from monika.infrastructure.brokers.mt5_compat import ensure_mt5_module

        ensure_mt5_module()
        import MetaTrader5 as _mt5

        mt5: Any = _mt5

        # 1. Direct match check
        info = mt5.symbol_info(clean_sym)
        if info is not None:
            _BROKER_SYMBOL_CACHE[clean_sym] = clean_sym
            return clean_sym

        # 2. Check known common broker suffixes
        common_suffixes = ["m", ".pro", ".raw", "+", ".a", ".ecn", "_i", ".s", "c", ".c", "_c", "cent", ".cent"]
        for sfx in common_suffixes:
            candidate = f"{clean_sym}{sfx}"
            if mt5.symbol_info(candidate) is not None:
                logger.info(f"Resolved broker symbol: {clean_sym} -> {candidate}")
                _BROKER_SYMBOL_CACHE[clean_sym] = candidate
                return candidate

        # 3. Query symbols_get with group wildcard
        matches = mt5.symbols_get(group=f"*{clean_sym}*")
        if matches:
            for s in matches:
                name = getattr(s, "name", "")
                if clean_sym in name:
                    logger.info(f"Resolved broker symbol via wildcard match: {clean_sym} -> {name}")
                    _BROKER_SYMBOL_CACHE[clean_sym] = name
                    return name
    except Exception as e:
        logger.debug(f"Broker symbol resolution fallback for {clean_sym}: {e}")

    # Fallback to provided symbol
    _BROKER_SYMBOL_CACHE[clean_sym] = clean_sym
    return clean_sym


def _build_timeframe_map() -> dict[str, int]:
    """Membuat pemetaan timeframe string ke konstanta MT5. Dipanggil secara lazy (saat dibutuhkan)."""
    try:
        from monika.infrastructure.brokers.mt5_compat import ensure_mt5_module

        ensure_mt5_module()
        import MetaTrader5 as _mt5

        mt5: Any = _mt5
        return {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }
    except (ImportError, Exception):
        # Standard MT5 timeframe ENUM constants fallback for mock / Linux CI environments
        return {
            "M1": 1,
            "M5": 5,
            "M15": 15,
            "M30": 30,
            "H1": 16385,
            "H4": 16388,
            "D1": 16408,
            "W1": 32769,
            "MN1": 49153,
        }
