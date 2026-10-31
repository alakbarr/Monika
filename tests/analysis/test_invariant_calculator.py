import pytest
from monika.application.analysis.calculators.invariant_calculator import (
    compute_trade_invariants,
    format_invariants_for_prompt,
    extract_price_precision,
)


def test_extract_price_precision():
    assert extract_price_precision("EURUSD") == 5
    assert extract_price_precision("USDJPY") == 3
    assert extract_price_precision("XAUUSD") == 2
    assert extract_price_precision("BTCUSD") == 1


def test_compute_trade_invariants_buy():
    # Current EURUSD = 1.1000, ATR = 0.0020, ADR = 0.0080
    res = compute_trade_invariants(
        symbol="EURUSD",
        current_price=1.1000,
        atr=0.0020,
        adr_5d=0.0080,
        smc_zones=[{"price": 1.0975, "type": "FVG"}],
        sr_zones=[1.1060],
        min_rr=1.5,
    )

    buy_sl = res["buy_bounds"]["sl_range"]
    buy_tp = res["buy_bounds"]["tp_range"]

    # SL max is entry - 1.0 * ATR = 1.1000 - 0.0020 = 1.0980
    assert buy_sl[1] == 1.0980
    # SL min is entry - min(2.5 * ATR, 0.35 * ADR) = 1.1000 - min(0.0050, 0.0028) = 1.0972
    assert buy_sl[0] == 1.0972

    # TP min is entry + 0.5 * ADR = 1.1000 + 0.0040 = 1.1040
    assert buy_tp[0] == 1.1040
    # TP max is entry + 0.8 * ADR = 1.1000 + 0.0064 = 1.1064
    assert buy_tp[1] == 1.1064

    # Anchors detected
    assert len(res["structural_anchors"]) >= 1
    assert any(a["type"] == "FVG" for a in res["structural_anchors"])


def test_compute_trade_invariants_timesfm_capping():
    # Gold: current 2900, ATR=10, ADR=40, TimesFM Q90=2925
    res = compute_trade_invariants(
        symbol="XAUUSD", current_price=2900.0, atr=10.0, adr_5d=40.0, timesfm_envelope={"q10": 2870.0, "q90": 2925.0}
    )

    # Standard TP max would be 2900 + 0.8*40 = 2932. But TimesFM Q90 is 2925.
    # Must cap TP max at 2925.
    assert res["buy_bounds"]["tp_range"][1] == 2925.0

    # For SELL, standard TP min would be 2900 - 0.8*40 = 2868. TimesFM Q10 is 2870.
    # Must cap SELL TP min at 2870.
    assert res["sell_bounds"]["tp_range"][0] == 2870.0


def test_format_invariants_for_prompt():
    res = compute_trade_invariants(
        symbol="BTCUSD",
        current_price=90000.0,
        atr=1000.0,
        adr_5d=3000.0,
        smc_zones=[{"price": 89200.0, "type": "ORDER_BLOCK"}],
    )
    formatted = format_invariants_for_prompt(res)
    assert "=== PRE-COMPUTED TRADE INVARIANTS (BTCUSD @ 90000.0) ===" in formatted
    assert "BUY INVARIANTS" in formatted
    assert "SELL INVARIANTS" in formatted
    assert "ORDER_BLOCK" in formatted
    assert "LONG_OPTION_A" in formatted
    assert "SHORT_OPTION_B" in formatted


def test_generate_concrete_bracket_options_math_precision():
    from monika.application.analysis.calculators.invariant_calculator import generate_concrete_bracket_options

    brackets = generate_concrete_bracket_options(
        symbol="EURUSD",
        current_price=1.10000,
        atr=0.00200,
        adr_5d=0.00800,
        smc_zones=[
            {"price": 1.09700, "type": "FVG_BULL"},
            {"price": 1.10400, "type": "OB_BEAR"},
        ],
        target_rr=1.80,
    )
    long_b = brackets["long_option_a"]
    short_b = brackets["short_option_b"]

    assert long_b["direction"] == "buy"
    assert short_b["direction"] == "sell"
    assert long_b["rr_ratio"] == 1.80
    assert short_b["rr_ratio"] == 1.80

    # Test exact mathematical R:R
    long_risk = abs(long_b["entry"] - long_b["stop_loss"])
    long_reward = abs(long_b["take_profit"] - long_b["entry"])
    assert round(long_reward / long_risk, 2) == 1.80

    short_risk = abs(short_b["stop_loss"] - short_b["entry"])
    short_reward = abs(short_b["entry"] - short_b["take_profit"])
    assert round(short_reward / short_risk, 2) == 1.80
