import pytest
from monika.application.analysis.calculators.invariant_calculator import (
    compute_trade_invariants,
    format_invariants_for_prompt,
    extract_price_precision,
    resolve_bracket_choice,
    generate_concrete_bracket_options,
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


def test_resolve_bracket_choice():
    bracket_options = {
        "long_option_a": {
            "name": "LONG_OPTION_A",
            "direction": "buy",
            "entry": 1.09800,
            "stop_loss": 1.09500,
            "take_profit": 1.10340,
            "rr_ratio": 1.80,
            "sl_distance_atr": 1.5,
        },
        "short_option_b": {
            "name": "SHORT_OPTION_B",
            "direction": "sell",
            "entry": 1.10200,
            "stop_loss": 1.10500,
            "take_profit": 1.09660,
            "rr_ratio": 1.80,
            "sl_distance_atr": 1.5,
        },
    }

    assert resolve_bracket_choice("LONG_OPTION_A", bracket_options)["direction"] == "buy"
    assert resolve_bracket_choice("option_a", bracket_options)["direction"] == "buy"
    assert resolve_bracket_choice("A", bracket_options)["direction"] == "buy"
    assert resolve_bracket_choice("SHORT_OPTION_B", bracket_options)["direction"] == "sell"
    assert resolve_bracket_choice("option_b", bracket_options)["direction"] == "sell"
    assert resolve_bracket_choice("B", bracket_options)["direction"] == "sell"
    assert resolve_bracket_choice("INVALID", bracket_options) is None
    assert resolve_bracket_choice(None, bracket_options) is None


def test_real_smc_order_blocks_and_fvg_extraction():
    smc_payload = {
        "order_blocks": [
            {"direction": "bullish", "price_low": 1.09650, "price_high": 1.09850, "mitigated": False},
            {"direction": "bearish", "price_low": 1.10180, "price_high": 1.10380, "mitigated": False},
        ],
        "fair_value_gaps": [
            {"direction": "bullish", "gap_low": 1.09700, "gap_high": 1.09900, "filled": False},
            {"direction": "bearish", "gap_low": 1.10120, "gap_high": 1.10250, "filled": False},
        ],
    }
    sr_zones = [
        {"price_low": 1.09500, "price_high": 1.09600},
        {"price_low": 1.10400, "price_high": 1.10500},
    ]

    inv = compute_trade_invariants(
        symbol="EURUSD",
        current_price=1.10000,
        atr=0.00200,
        adr_5d=0.00600,
        smc_zones=smc_payload,
        sr_zones=sr_zones,
    )
    anchor_prices = [a["price"] for a in inv["structural_anchors"]]
    assert 1.09900 in anchor_prices and 1.09850 in anchor_prices
    assert 1.10120 in anchor_prices and 1.10180 in anchor_prices

    long_b = inv["bracket_options"]["long_option_a"]
    short_b = inv["bracket_options"]["short_option_b"]
    # Closest bullish anchor below 1.10000 is FVG gap_high 1.09900
    assert long_b["entry"] == 1.09900
    assert long_b["entry_type"] == "limit"
    # Closest bearish anchor above 1.10000 is FVG gap_low 1.10120
    assert short_b["entry"] == 1.10120
    assert short_b["entry_type"] == "limit"
    assert long_b["rr_ratio"] >= 1.50
    assert short_b["rr_ratio"] >= 1.50


def test_impulse_breakout_market_entry():
    """Verify that impulse breakout regimes trigger market entries instead of unfilled limit orders."""
    from monika.application.analysis.calculators.invariant_calculator import generate_concrete_bracket_options

    # 1. Bullish impulse
    bull_brackets = generate_concrete_bracket_options(
        symbol="EURUSD",
        current_price=1.10000,
        atr=0.00200,
        adr_5d=0.00800,
        regime_classification="BULLISH_IMPULSE_BREAKOUT",
        h4_impulse_atr=1.45,
    )
    long_b = bull_brackets["long_option_a"]
    assert long_b["entry"] == 1.10000
    assert long_b["entry_type"] == "market"
    assert "impulse breakout market entry" in long_b["description"].lower()
    assert long_b["rr_ratio"] >= 1.50
    assert long_b["stop_loss"] < 1.10000
    assert long_b["take_profit"] > 1.10000

    # 2. Bearish impulse
    bear_brackets = generate_concrete_bracket_options(
        symbol="EURUSD",
        current_price=1.10000,
        atr=0.00200,
        adr_5d=0.00800,
        regime_classification="BEARISH_IMPULSE_BREAKOUT",
        h4_impulse_atr=-1.60,
    )
    short_b = bear_brackets["short_option_b"]
    assert short_b["entry"] == 1.10000
    assert short_b["entry_type"] == "market"
    assert "impulse breakout market entry" in short_b["description"].lower()
    assert short_b["rr_ratio"] >= 1.50
    assert short_b["stop_loss"] > 1.10000
    assert short_b["take_profit"] < 1.10000


def test_differentiated_asset_impulse_thresholds():
    """Verify FX Majors trigger breakout at 0.85x ATR, whereas Crypto/Commodities require 1.25x ATR."""
    # FX Major at 0.90x ATR -> Should be market breakout entry (threshold is 0.85x ATR)
    fx_brackets = generate_concrete_bracket_options(
        symbol="EURUSD",
        current_price=1.11000,
        atr=0.00200,
        adr_5d=0.00800,
        smc_zones=[{"price": 1.10700, "type": "demand"}],
        h4_impulse_atr=0.90,
    )
    assert fx_brackets["long_option_a"]["entry_type"] == "market"
    assert "impulse breakout market entry" in fx_brackets["long_option_a"]["description"].lower()

    # Crypto at 0.90x ATR -> Should NOT trigger breakout (threshold is 1.25x ATR, so stays limit order)
    crypto_moderate = generate_concrete_bracket_options(
        symbol="BTCUSD",
        current_price=80000.0,
        atr=800.0,
        adr_5d=2500.0,
        smc_zones=[{"price": 79600.0, "type": "demand"}],
        h4_impulse_atr=0.90,
    )
    assert crypto_moderate["long_option_a"]["entry_type"] == "limit"
    assert "demand poi limit entry" in crypto_moderate["long_option_a"]["description"].lower()

    # Crypto at 1.30x ATR -> Should trigger breakout market entry (1.30 >= 1.25)
    crypto_strong = generate_concrete_bracket_options(
        symbol="BTCUSD",
        current_price=80000.0,
        atr=800.0,
        adr_5d=2500.0,
        smc_zones=[{"price": 79600.0, "type": "demand"}],
        h4_impulse_atr=1.30,
    )
    assert crypto_strong["long_option_a"]["entry_type"] == "market"
    assert "impulse breakout market entry" in crypto_strong["long_option_a"]["description"].lower()


def test_dynamic_calibrated_noise_buffer_by_asset_class():
    """Verify that noise buffer defaults dynamically to 1.25x for FX and 1.35x for Crypto/Commodities."""
    # 1. FX Major defaults to 1.25x ATR
    fx_b = generate_concrete_bracket_options(
        symbol="EURUSD",
        current_price=1.10000,
        atr=0.00200,
        adr_5d=0.00800,
        target_rr=1.60,
    )
    long_fx = fx_b["long_option_a"]
    assert long_fx["sl_distance_atr"] == pytest.approx(1.25, abs=0.02)
    assert ">= 1.25x atr" in long_fx["description"].lower()

    # 2. Crypto defaults to 1.35x ATR
    btc_b = generate_concrete_bracket_options(
        symbol="BTCUSD",
        current_price=90000.0,
        atr=1000.0,
        adr_5d=3500.0,
        target_rr=1.60,
    )
    long_btc = btc_b["long_option_a"]
    assert long_btc["sl_distance_atr"] == pytest.approx(1.35, abs=0.02)
    assert ">= 1.35x atr" in long_btc["description"].lower()

    # 3. Commodity (XAUUSD) defaults to 1.35x ATR
    xau_b = generate_concrete_bracket_options(
        symbol="XAUUSD",
        current_price=2750.00,
        atr=25.00,
        adr_5d=90.00,
        target_rr=1.60,
    )
    long_xau = xau_b["long_option_a"]
    assert long_xau["sl_distance_atr"] == pytest.approx(1.35, abs=0.02)
    assert ">= 1.35x atr" in long_xau["description"].lower()

    # 4. Explicit override is respected
    override_b = generate_concrete_bracket_options(
        symbol="EURUSD",
        current_price=1.10000,
        atr=0.00200,
        adr_5d=0.00800,
        noise_buffer_atr=1.50,
        target_rr=1.60,
    )
    assert override_b["long_option_a"]["sl_distance_atr"] == pytest.approx(1.50, abs=0.02)
    assert ">= 1.50x atr" in override_b["long_option_a"]["description"].lower()
