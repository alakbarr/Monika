# ==============================================================================
# File: backtest/engines/crypto_engine.py
# Monika Institutional Crypto Derivatives Simulation Engine
# ==============================================================================

"""
Crypto Spot & Perpetual Derivatives Simulation Engine:
  1. 24/7 continuous calendar trading without weekend market closures.
  2. Maker / Taker fee schedule modeling (default: 2 bps maker, 5 bps taker).
  3. 8-hour perpetual funding rate cashflow settlement (00:00, 08:00, 16:00 UTC).
  4. Dynamic maintenance margin and liquidation threshold calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True, slots=True)
class CryptoMarketRules:
    maker_fee_bps: float = 2.0   # 0.02%
    taker_fee_bps: float = 5.0   # 0.05%
    default_funding_rate_8h: float = 0.0001  # +0.01% baseline
    maintenance_margin_pct: float = 0.02    # 2% maintenance margin (50x leverage cap)


class CryptoEngine:
    """Calculates crypto perpetual execution costs, funding fees, and liquidation."""

    @classmethod
    def calculate_commission(cls, notional_usd: float, is_taker: bool = True) -> float:
        fee_bps = 5.0 if is_taker else 2.0
        return float(notional_usd * (fee_bps * 1e-4))

    @classmethod
    def calculate_funding_payment(
        cls,
        notional_usd: float,
        action: str,
        funding_rate: float = 0.0001,
    ) -> float:
        """
        Calculates 8-hour funding cashflow settlement.
        Positive funding rate: Longs pay Shorts.
        Negative funding rate: Shorts pay Longs.
        """
        if action.lower() == "buy":
            # Long pays when funding > 0, receives when funding < 0
            return float(- notional_usd * funding_rate)
        else:
            # Short receives when funding > 0, pays when funding < 0
            return float(notional_usd * funding_rate)

    @classmethod
    def check_liquidation(
        cls,
        entry_price: float,
        current_price: float,
        action: str,
        leverage: float = 20.0,
        maintenance_margin_pct: float = 0.02,
    ) -> bool:
        """Returns True if position has breached maintenance margin boundary."""
        initial_margin = 1.0 / max(leverage, 1.0)
        max_loss_pct = initial_margin - maintenance_margin_pct

        if action.lower() == "buy":
            price_drop = (entry_price - current_price) / entry_price
            return price_drop >= max_loss_pct
        else:
            price_rise = (current_price - entry_price) / entry_price
            return price_rise >= max_loss_pct
