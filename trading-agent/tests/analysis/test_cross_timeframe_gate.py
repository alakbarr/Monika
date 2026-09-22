"""
Tests for CrossTimeframeConfirmationGate (HTF Alignment Sentinel - PR-11).
Verifies directional alignment across H4, H1, and M15 entry decisions.
"""

import pytest
from analysis.validators.cross_timeframe_gate import CrossTimeframeConfirmationGate


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
        "get_structure_breaks_H4": {
            "breaks": [{"type": "BOS", "direction": "bullish"}]
        },
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
