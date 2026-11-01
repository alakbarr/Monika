"""
Tests for CrossTimeframeConfirmationGate (HTF Alignment Sentinel - PR-11).
Verifies directional alignment across H4, H1, and M15 entry decisions.
"""

import pytest
from monika.application.analysis.validators.cross_timeframe_gate import CrossTimeframeConfirmationGate


def test_non_directional_decision_passes():
    is_aligned, reason, meta = CrossTimeframeConfirmationGate.verify_htf_alignment(
        decision="wait",
        data_bundle={},
        symbol="EURUSD",
    )
    assert is_aligned is True
    assert "Non-directional" in reason


def test_buy_rejected_on_dual_bearish():
    # H4 bearish (close < ema50), H1 bearish (trend down)
    bundle = {
        "get_technical_indicators_H4": {
            "close": 1.0500,
            "ema50": 1.0600,
            "ema20": 1.0550,
        },
        "get_technical_indicators_H1": {
            "trend": "downtrend",
        },
    }
    is_aligned, reason, meta = CrossTimeframeConfirmationGate.verify_htf_alignment(
        decision="buy",
        data_bundle=bundle,
        symbol="EURUSD",
    )
    assert is_aligned is False
    assert "Dual HTF conflict" in reason
    assert meta["h4_bias"] == "bearish"
    assert meta["h1_bias"] == "bearish"


def test_sell_rejected_on_dual_bullish():
    # H4 bullish (structure break bull), H1 bullish (trend uptrend)
    bundle = {
        "get_structure_breaks_H4": {"breaks": [{"type": "BOS", "direction": "bullish"}]},
        "get_technical_indicators_H1": {
            "trend": "bullish strong",
        },
    }
    is_aligned, reason, meta = CrossTimeframeConfirmationGate.verify_htf_alignment(
        decision="sell",
        data_bundle=bundle,
        symbol="XAUUSD",
    )
    assert is_aligned is False
    assert "Dual HTF conflict" in reason
    assert meta["h4_bias"] == "bullish"
    assert meta["h1_bias"] == "bullish"


def test_buy_permitted_on_aligned_or_neutral():
    # H4 bullish, H1 neutral
    bundle = {
        "get_technical_indicators_H4": {
            "trend": "bullish",
        },
        "get_technical_indicators_H1": {
            "trend": "ranging",
        },
    }
    is_aligned, reason, meta = CrossTimeframeConfirmationGate.verify_htf_alignment(
        decision="buy",
        data_bundle=bundle,
        symbol="GBPUSD",
    )
    assert is_aligned is True
    assert "HTF confirmation passed" in reason
    assert meta["h4_bias"] == "bullish"
    assert meta["h1_bias"] == "neutral"


def test_sell_permitted_on_aligned_or_neutral():
    # H4 bearish, H1 bearish
    bundle = {
        "get_technical_indicators_H4": {
            "trend": "bearish",
        },
        "get_technical_indicators_H1": {
            "trend": "bearish",
        },
    }
    is_aligned, reason, meta = CrossTimeframeConfirmationGate.verify_htf_alignment(
        decision="sell",
        data_bundle=bundle,
        symbol="USDJPY",
    )
    assert is_aligned is True
    assert "HTF confirmation passed" in reason


def test_price_history_momentum_extraction():
    # 10 bars momentum > +0.8% -> bullish
    bars = [{"close": 100.0}] * 9 + [{"close": 102.0}]
    bundle = {
        "get_price_history_H4": {
            "bars": bars,
        },
        "get_price_history_H1": {
            "bars": bars,
        },
    }
    bias = CrossTimeframeConfirmationGate._extract_timeframe_bias(bundle, "H4")
    assert bias == "bullish"


def test_single_tf_pullback_disallowed():
    # H4 bearish, H1 neutral, BUY decision, allow_single_tf_pullback=False -> Reject
    bundle = {
        "get_technical_indicators_H4": {
            "trend": "bearish",
        },
    }
    is_aligned, reason, meta = CrossTimeframeConfirmationGate.verify_htf_alignment(
        decision="buy",
        data_bundle=bundle,
        symbol="BTCUSD",
        allow_single_tf_pullback=False,
    )
    assert is_aligned is False
    assert "conflicts with H4 bearish" in reason


def test_buy_permitted_on_dual_bearish_in_discount_accumulation():
    # H4 bearish, H1 bearish, but dealing_range_pos <= 0.38 (Institutional Discount)
    bundle = {
        "get_technical_indicators_H4": {"trend": "bearish"},
        "get_technical_indicators_H1": {"trend": "bearish"},
        "precomputed_invariants": {
            "dealing_range_pos": 0.22,
            "regime_classification": "DISCOUNT_ACCUMULATION_ZONE",
        },
    }
    is_aligned, reason, meta = CrossTimeframeConfirmationGate.verify_htf_alignment(
        decision="buy",
        data_bundle=bundle,
        symbol="BTCUSD",
    )
    assert is_aligned is True
    assert "Discount Accumulation protocol" in reason
    assert meta["dealing_range_pos"] == 0.22
    assert meta["h4_bias"] == "bearish"
    assert meta["h1_bias"] == "bearish"


def test_sell_permitted_on_dual_bullish_in_premium_distribution():
    # H4 bullish, H1 bullish, but dealing_range_pos >= 0.65 (Institutional Premium)
    bundle = {
        "get_technical_indicators_H4": {"trend": "bullish"},
        "get_technical_indicators_H1": {"trend": "bullish"},
        "precomputed_invariants": {
            "dealing_range_pos": 0.88,
            "regime_classification": "PREMIUM_DISTRIBUTION_ZONE",
        },
    }
    is_aligned, reason, meta = CrossTimeframeConfirmationGate.verify_htf_alignment(
        decision="sell",
        data_bundle=bundle,
        symbol="EURUSD",
    )
    assert is_aligned is True
    assert "Premium Distribution protocol" in reason
    assert meta["dealing_range_pos"] == 0.88


def test_buy_rejected_on_dual_bearish_in_mid_range():
    # H4 bearish, H1 bearish, dealing_range_pos = 0.52 (Mid-range equilibrium -> UNTETHERED KNIFE CATCH)
    bundle = {
        "get_technical_indicators_H4": {"trend": "bearish"},
        "get_technical_indicators_H1": {"trend": "bearish"},
        "precomputed_invariants": {
            "dealing_range_pos": 0.52,
            "regime_classification": "MID_RANGE_DIRECTIONAL_FLOW",
        },
    }
    is_aligned, reason, meta = CrossTimeframeConfirmationGate.verify_htf_alignment(
        decision="buy",
        data_bundle=bundle,
        symbol="GBPUSD",
    )
    assert is_aligned is False
    assert "outside discount" in reason


def test_counter_trend_permitted_on_liquidity_sweep():
    # H4 bearish, H1 bearish, but liquidity sweep confirmed -> Turtle soup reversal allowed
    bundle = {
        "get_technical_indicators_H4": {"trend": "bearish"},
        "get_technical_indicators_H1": {"trend": "bearish"},
        "precomputed_invariants": {
            "dealing_range_pos": 0.45,
            "liquidity_sweep_detected": True,
        },
    }
    is_aligned, reason, meta = CrossTimeframeConfirmationGate.verify_htf_alignment(
        decision="buy",
        data_bundle=bundle,
        symbol="XAUUSD",
    )
    assert is_aligned is True
    assert "Discount Accumulation protocol" in reason
    assert meta["has_liquidity_sweep"] is True


def test_bracket_options_impulse_propagation_to_market_order():
    from monika.application.analysis.calculators.invariant_calculator import generate_concrete_bracket_options

    # FX Major with impulse >= 0.85x ATR -> Market order breakout
    opts_fx = generate_concrete_bracket_options(
        symbol="EURUSD",
        current_price=1.1000,
        atr=0.0050,
        adr_5d=0.0110,
        regime_classification="BULLISH_IMPULSE_BREAKOUT",
        h4_impulse_atr=1.10,
    )
    assert opts_fx["long_option_a"]["entry_type"] == "market"
    assert opts_fx["long_option_a"]["entry"] == 1.1000

    # Bearish impulse -> Short option B is market order breakout
    opts_short = generate_concrete_bracket_options(
        symbol="BTCUSD",
        current_price=65000.0,
        atr=1200.0,
        adr_5d=2800.0,
        regime_classification="BEARISH_IMPULSE_BREAKOUT",
        h4_impulse_atr=-1.45,
    )
    assert opts_short["short_option_b"]["entry_type"] == "market"
    assert opts_short["short_option_b"]["entry"] == 65000.0
