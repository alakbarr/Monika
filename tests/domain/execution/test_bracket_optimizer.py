"""Unit tests for deterministic BracketOptimizer."""

import pytest
from monika.domain.execution.bracket_optimizer import BracketOptimizer, get_symbol_decimals


def test_symbol_decimals_resolution():
    assert get_symbol_decimals("EURUSD") == 5
    assert get_symbol_decimals("GBPUSD") == 5
    assert get_symbol_decimals("USDJPY") == 3
    assert get_symbol_decimals("XAUUSD") == 2
    assert get_symbol_decimals("BTCUSD") == 2
    assert get_symbol_decimals("XTIUSD") == 2


def test_bracket_optimizer_expands_tight_sl_to_atr_floor():
    optimizer = BracketOptimizer(default_min_rr=1.5)
    # Entry 1.1000, proposed SL 1.0990 (10 pips), ATR = 0.0025 (25 pips)
    opt = optimizer.optimize(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0990,
        take_profit=1.1040,
        atr=0.0025,
        min_sl_atr_multiplier=1.0,
    )
    assert opt.stop_loss == 1.0975
    assert opt.risk_distance == pytest.approx(0.0025, abs=1e-5)
    # TP must be >= entry + 1.5 * 0.0025 = 1.10375
    assert opt.take_profit >= 1.10375
    assert opt.rr_ratio >= 1.5
    assert opt.adjusted is True


def test_bracket_optimizer_corrects_inverted_sl():
    optimizer = BracketOptimizer(default_min_rr=1.3)
    # BUY with inverted SL (SL > entry)
    opt = optimizer.optimize(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.1050,  # Inverted!
        take_profit=1.1080,
        atr=0.0020,
    )
    assert opt.stop_loss < opt.entry_price
    assert opt.take_profit > opt.entry_price
    assert opt.rr_ratio >= 1.3
    assert opt.adjusted is True


def test_bracket_optimizer_for_crypto_btcusd():
    optimizer = BracketOptimizer(default_min_rr=1.5)
    # BTCUSD Entry 65000.0, SL 64500.0 (risk 500), TP 66000.0 (reward 1000)
    opt = optimizer.optimize(
        symbol="BTCUSD",
        direction="buy",
        entry_price=65000.0,
        stop_loss=64500.0,
        take_profit=66000.0,
        atr=400.0,
    )
    assert opt.stop_loss == 64500.0
    assert opt.take_profit == 66000.0
    assert opt.rr_ratio == 2.0


def test_bracket_optimizer_snaps_tp_to_adr_band():
    optimizer = BracketOptimizer(default_min_rr=1.3)
    adr_ctx = {
        "adr": 0.0080,
        "target_tp_min_distance": 0.0040,
        "target_tp_max_distance": 0.0064,
        "target_sl_max_distance": 0.0028,
        "band_tolerance_pct": 0.10,
    }
    # BUY entry 1.1000, SL 1.0980 (dist 0.0020), TP 1.1025 (dist 0.0025, below ADR min of 0.0036)
    opt = optimizer.optimize(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        take_profit=1.1025,
        atr=0.0020,
        adr_ctx=adr_ctx,
    )
    # TP must be expanded to meet ADR min of 0.0036
    assert opt.reward_distance >= 0.0036
    assert opt.take_profit >= 1.1036
    assert opt.rr_ratio >= 1.3
