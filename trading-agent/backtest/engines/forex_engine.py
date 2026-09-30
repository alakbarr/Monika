# ==============================================================================
# File: backtest/engines/forex_engine.py
# Monika Institutional Forex Exchange & Market Simulation Engine
# ==============================================================================

"""
Foreign Exchange (FX) Simulation Engine:
Accurately models real interbank and retail broker market mechanics:
  1. Micro-lot granularity (0.01 = 1,000 base currency units).
  2. Dynamic session spread multipliers (Asian session 1.4x, 17:00 NY Rollover 3.5x widening).
  3. Triple swap Wednesday financing rollover accounting.
  4. Currency-specific pip dimensions (0.01 for JPY, 0.0001 standard).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True, slots=True)
class ForexMarketRules:
    base_spread_pips: float = 1.2
    rollover_hour_utc: int = 21       # 17:00 NY / 21:00 UTC
    rollover_spread_mult: float = 3.5 # Widens 3.5x during illiquid rollover
    asian_session_spread_mult: float = 1.4
    long_swap_rate_annual: float = -0.015  # -1.5% annual financing drag
    short_swap_rate_annual: float = 0.005  # +0.5% annual carry yield
    lot_contract_size: float = 100000.0


class ForexEngine:
    """Calculates realistic execution costs and fills for currency pairs."""

    @classmethod
    def get_pip_size(cls, symbol: str) -> float:
        norm = symbol.upper()
        if "JPY" in norm:
            return 0.01
        elif "XAU" in norm:
            return 0.10
        return 0.0001

    @classmethod
    def calculate_effective_spread(cls, symbol: str, timestamp: datetime, base_pips: float = 1.2) -> float:
        hour = timestamp.hour
        weekday = timestamp.weekday()

        mult = 1.0
        # Daily Rollover liquidity vacuum (21:00 - 22:00 UTC)
        if hour == 21:
            mult = 3.5
        # Friday market close liquidity drain
        elif weekday == 4 and hour >= 20:
            mult = 4.0
        # Asian session (22:00 - 06:00 UTC)
        elif hour >= 22 or hour <= 6:
            mult = 1.4
        # London / NY overlap (12:00 - 16:00 UTC): deepest liquidity
        elif 12 <= hour <= 16:
            mult = 0.9

        pip_size = cls.get_pip_size(symbol)
        return float(base_pips * mult * pip_size)

    @classmethod
    def calculate_swap_cost(
        cls,
        action: str,
        price: float,
        lots: float,
        days_held: float,
        is_wednesday_rollover: bool = False,
    ) -> float:
        """Calculates overnight rollover financing charges (with triple swap on Wednesday)."""
        contract_val = price * lots * 100000.0
        rate = -0.018 if action.lower() == "buy" else 0.002
        mult = 3.0 if is_wednesday_rollover else 1.0
        daily_rate = rate / 365.0
        return float(contract_val * daily_rate * days_held * mult)
