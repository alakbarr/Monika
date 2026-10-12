# ==============================================================================
# File: backtest/engines/futures_engine.py
# Monika Commodity & Index Futures Simulation Engine
# ==============================================================================

"""
Futures Exchange Simulation Engine:
  1. Contract point multiplier scaling (ES $50, MES $5, GC $100, CL $1,000).
  2. Initial and Maintenance Margin requirements.
  3. Exchange clearing fees per contract (CME/NYMEX/COMEX schedules).
  4. Daily mark-to-market variation margin settlement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True, slots=True)
class FuturesContractSpec:
    symbol: str
    multiplier: float
    tick_size: float
    initial_margin: float
    maint_margin: float
    exchange_fee_per_side: float


class FuturesEngine:
    """Calculates contract multipliers, margin requirements, and mark-to-market PnL."""

    CONTRACT_SPECS: Dict[str, FuturesContractSpec] = {
        "ES": FuturesContractSpec(symbol="ES", multiplier=50.0, tick_size=0.25, initial_margin=12500.0, maint_margin=11500.0, exchange_fee_per_side=2.25),
        "MES": FuturesContractSpec(symbol="MES", multiplier=5.0, tick_size=0.25, initial_margin=1250.0, maint_margin=1150.0, exchange_fee_per_side=0.55),
        "GC": FuturesContractSpec(symbol="GC", multiplier=100.0, tick_size=0.10, initial_margin=11000.0, maint_margin=10000.0, exchange_fee_per_side=2.40),
        "CL": FuturesContractSpec(symbol="CL", multiplier=1000.0, tick_size=0.01, initial_margin=7500.0, maint_margin=6800.0, exchange_fee_per_side=2.15),
    }

    @classmethod
    def get_spec(cls, symbol: str) -> FuturesContractSpec:
        norm = symbol.upper().replace("/", "")
        for k, spec in cls.CONTRACT_SPECS.items():
            if norm.startswith(k):
                return spec
        return FuturesContractSpec(symbol=symbol, multiplier=1.0, tick_size=0.01, initial_margin=5000.0, maint_margin=4500.0, exchange_fee_per_side=2.0)

    @classmethod
    def calculate_dollar_pnl(
        cls,
        symbol: str,
        entry_price: float,
        exit_price: float,
        contracts: float,
        action: str,
    ) -> float:
        spec = cls.get_spec(symbol)
        price_diff = (exit_price - entry_price) if action.lower() == "buy" else (entry_price - exit_price)
        gross_pnl = price_diff * spec.multiplier * contracts
        fees = spec.exchange_fee_per_side * 2.0 * contracts  # Roundtrip fees
        return float(gross_pnl - fees)
