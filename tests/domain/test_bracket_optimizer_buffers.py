"""Property-based and unit tests for BracketOptimizer structural buffers and fail-closed geometry."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from monika.domain.execution.bracket_optimizer import BracketOptimizer


def test_bracket_optimizer_applies_explicit_structural_buffer():
    optimizer = BracketOptimizer(default_min_rr=1.5)
    # BUY entry 1.1000, SL 1.0950 (raw dist 0.0050), TP 1.1150
    # Explicit buffer 0.0010 -> target SL dist becomes 0.0050 + 0.0010 = 0.0060 -> SL = 1.0940
    opt = optimizer.optimize(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1150,
        atr=0.0020,
        structural_buffer=0.0010,
    )
    assert opt.stop_loss == 1.0940
    assert opt.risk_distance == pytest.approx(0.0060, abs=1e-5)
    assert opt.take_profit >= 1.1090
    assert opt.rr_ratio >= 1.5


def test_bracket_optimizer_enforces_automatic_symbol_buffer_fx():
    optimizer = BracketOptimizer(default_min_rr=1.5)
    # FX default buffer = 0.35 * ATR (0.0020 * 0.35 = 0.00070)
    opt = optimizer.optimize(
        symbol="GBPUSD",
        direction="sell",
        entry_price=1.3000,
        stop_loss=1.3050,  # dist 0.0050 -> with buffer: 0.00570 -> SL = 1.30570
        take_profit=1.2900,
        atr=0.0020,
        enforce_structural_buffer=True,
    )
    assert opt.stop_loss == 1.30570
    assert opt.risk_distance == pytest.approx(0.00570, abs=1e-5)
    assert opt.take_profit <= 1.29145
    assert opt.rr_ratio >= 1.5


def test_bracket_optimizer_enforces_automatic_symbol_buffer_commodity():
    optimizer = BracketOptimizer(default_min_rr=1.5)
    # Commodity (XAUUSD) default buffer = 1.20 * ATR (10.0 * 1.20 = 12.0)
    opt = optimizer.optimize(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2600.0,
        stop_loss=2580.0,  # dist 20.0 -> with buffer: 32.0 -> SL = 2568.0
        take_profit=2650.0,
        atr=10.0,
        enforce_structural_buffer=True,
    )
    assert opt.stop_loss == 2568.0
    assert opt.risk_distance == pytest.approx(32.0, abs=1e-2)
    assert opt.take_profit >= 2648.0
    assert opt.rr_ratio >= 1.5


@settings(max_examples=50, deadline=None)
@given(
    entry=st.floats(min_value=1.0, max_value=2000.0),
    raw_sl=st.floats(min_value=0.1, max_value=3000.0),
    raw_tp=st.floats(min_value=0.1, max_value=3000.0),
    atr=st.floats(min_value=0.001, max_value=50.0),
    min_rr=st.floats(min_value=1.0, max_value=3.0),
    is_buy=st.booleans(),
)
def test_bracket_optimizer_geometry_invariants(entry, raw_sl, raw_tp, atr, min_rr, is_buy):
    """Property-based test: For any inputs, output geometry must satisfy strict directional invariants."""
    optimizer = BracketOptimizer(default_min_rr=min_rr)
    direction = "buy" if is_buy else "sell"

    opt = optimizer.optimize(
        symbol="EURUSD",
        direction=direction,
        entry_price=entry,
        stop_loss=raw_sl,
        take_profit=raw_tp,
        atr=atr,
        min_rr=min_rr,
        enforce_structural_buffer=True,
    )

    if is_buy:
        assert opt.stop_loss < opt.entry_price
        assert opt.take_profit > opt.entry_price
    else:
        assert opt.stop_loss > opt.entry_price
        assert opt.take_profit < opt.entry_price

    assert opt.risk_distance > 0.0
    assert opt.reward_distance > 0.0
    assert opt.rr_ratio >= round(min_rr * 0.95, 2)
