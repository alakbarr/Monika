# ==============================================================================
# File: execution/service/sizing_calculator.py
# ==============================================================================

"""
Sizing calculation, slippage calculation, and price drift validation helpers.
"""

import logging
import math
from typing import Optional, Tuple

logger = logging.getLogger("TradingAgent.ExecutionService.SizingCalculator")


class SizingCalculator:
    """Helper for sizing validations, pip values, and price drift checks."""

    @staticmethod
    def validate_price_drift(
        current_market_price: float,
        reference_price: float,
        max_drift_pct: float = 1.0,
    ) -> Tuple[bool, float]:
        """
        Validates if current market price has drifted beyond max_drift_pct
        from reference_price (price_at_analysis).
        Returns (is_valid, drift_percentage).
        """
        if reference_price <= 0:
            return True, 0.0

        drift_pct = abs(current_market_price - reference_price) / reference_price * 100.0
        is_valid = drift_pct <= max_drift_pct
        return is_valid, drift_pct

    @staticmethod
    def compute_slippage_pips(
        expected_price: float,
        executed_price: float,
        pip_size: Optional[float] = None,
        point_size: Optional[float] = None,
    ) -> float:
        """Computes slippage in pips between expected entry and filled price."""
        sz = pip_size if pip_size is not None else (point_size if point_size is not None else 0.0001)
        if sz <= 0:
            sz = 0.0001
        diff = abs(executed_price - expected_price)
        return round(diff / sz, 2)

