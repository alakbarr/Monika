# ==============================================================================
# File: backtest/engines/equity_engine.py
# Monika Institutional Equity Settlement & Exchange Simulation Engine
# ==============================================================================

"""
Cash Equity Simulation Engine:
  1. T+1 settlement rules (positions purchased today cannot be liquidated before next calendar trading day).
  2. 100-share round-lot quantization.
  3. Short-selling borrow fee deduction (borrow cost drag for short legs).
  4. Regulatory transaction fees (SEC Section 31 + FINRA TAF modeling).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True, slots=True)
class EquityMarketRules:
    round_lot_size: int = 100
    settlement_days: int = 1         # T+1 US equities settlement regime
    sec_fee_rate: float = 0.0000278  # $27.80 per million dollars of principal
    finra_taf_per_share: float = 0.000166 # $0.000166 per share sold (max $8.30)
    hard_to_borrow_rate_annual: float = 0.03 # 3% annual short borrow fee


class EquityEngine:
    """Calculates exchange execution constraints and settlement rules for stocks."""

    @classmethod
    def quantize_shares(cls, requested_shares: float, allow_odd_lots: bool = False) -> int:
        if allow_odd_lots:
            return max(int(requested_shares), 0)
        # Round down to nearest 100-share round lot
        return max(int(requested_shares // 100) * 100, 0)

    @classmethod
    def can_liquidate_under_t1(cls, purchase_date: date, current_date: date) -> bool:
        """Enforces T+1 settlement hold."""
        return current_date > purchase_date

    @classmethod
    def calculate_regulatory_fees(cls, notional_usd: float, shares: int, is_sell: bool) -> float:
        """Calculates SEC Section 31 and FINRA TAF transaction fees upon sale."""
        if not is_sell:
            return 0.0
        sec_fee = notional_usd * 0.0000278
        finra_fee = min(shares * 0.000166, 8.30)
        return float(sec_fee + finra_fee)

    @classmethod
    def calculate_short_borrow_cost(
        cls,
        notional_usd: float,
        days_held: float,
        annual_borrow_rate: float = 0.03,
    ) -> float:
        """Calculates short borrow fee charged against overnight short positions."""
        daily_rate = annual_borrow_rate / 365.0
        return float(notional_usd * daily_rate * days_held)
