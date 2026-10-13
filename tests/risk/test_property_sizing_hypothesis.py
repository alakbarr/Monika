"""
Property-based tests for financial position sizing invariants using Hypothesis.
Ensures mathematical safety bounds hold across arbitrary input distributions.
"""

import math
from hypothesis import given, strategies as st
from monika.domain.risk.position_sizing import PositionSizer


@given(
    equity=st.floats(min_value=100.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
    entry=st.floats(min_value=10.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    sl_offset=st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
    rr=st.floats(min_value=2.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
def test_hypothesis_buy_sizing_invariants(equity: float, entry: float, sl_offset: float, rr: float):
    settings = {
        "trading": {
            "risk": {
                "risk_percent_per_trade": 1.0,
                "max_lot_size": 10.0,
                "min_rr_ratio": 2.0,
                "vix_risk_adjustment": False,
            }
        }
    }
    sizer = PositionSizer(settings)
    sl = entry - sl_offset
    tp = entry + (sl_offset * rr)

    res = sizer.calculate(
        symbol="XAUUSD",
        direction="buy",
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        account_equity=equity,
    )

    if res.is_valid:
        # Invariant 1: Recommended lot is strictly positive and finite
        assert res.recommended_lots > 0
        assert not math.isnan(res.recommended_lots)
        assert not math.isinf(res.recommended_lots)

        # Invariant 2: Lot size must not exceed hard ceiling
        assert res.recommended_lots <= 10.0

        # Invariant 3: RR ratio meets or exceeds threshold
        assert res.rr_ratio >= 2.0 - 1e-4

        # Invariant 4: Risk amount does not exceed equity
        assert res.risk_amount_usd <= equity


@given(
    equity=st.floats(min_value=-1000.0, max_value=0.0, allow_nan=False, allow_infinity=False),
    entry=st.floats(min_value=10.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    sl_offset=st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False),
)
def test_hypothesis_nonpositive_equity_rejected(equity: float, entry: float, sl_offset: float):
    settings = {
        "trading": {
            "risk": {
                "risk_percent_per_trade": 1.0,
                "max_lot_size": 10.0,
                "min_rr_ratio": 2.0,
                "vix_risk_adjustment": False,
            }
        }
    }
    sizer = PositionSizer(settings)
    res = sizer.calculate(
        symbol="XAUUSD",
        direction="buy",
        entry_price=entry,
        stop_loss=entry - sl_offset,
        take_profit=entry + (sl_offset * 2.0),
        account_equity=equity,
    )
    # Must fail-closed on non-positive equity
    assert not res.is_valid or res.recommended_lots == 0.0
