"""Unit tests for RegimeClassifier and cross-asset admissibility."""

from monika.domain.macro.regime_classifier import (
    MacroRegime,
    RegimeClassifier,
)


def test_regime_classifier_strong_dollar_blocks_commodity_and_crypto_longs():
    # DXY 101.48, 10Y Yield 1.58% (matching Iteration 3 & 4 data)
    env = RegimeClassifier.classify(dxy=101.48, us10y_yield=1.58)
    assert env.regime == MacroRegime.LIQUIDITY_CONTRACTION
    assert env.allowed_commodity_longs is False
    assert env.allowed_crypto_longs is False

    allowed_gold, reason_gold = RegimeClassifier.is_trade_allowed(
        symbol="XAUUSD", direction="buy", dxy=101.48, us10y_yield=1.58
    )
    assert allowed_gold is False
    assert "Macro Filter Blocked" in reason_gold

    allowed_oil, reason_oil = RegimeClassifier.is_trade_allowed(
        symbol="XTIUSD", direction="buy", dxy=101.48, us10y_yield=1.58
    )
    assert allowed_oil is False

    allowed_btc, reason_btc = RegimeClassifier.is_trade_allowed(
        symbol="BTCUSD", direction="buy", dxy=101.48, us10y_yield=1.58
    )
    assert allowed_btc is False

    # But shorting is allowed
    allowed_gold_sell, _ = RegimeClassifier.is_trade_allowed(
        symbol="XAUUSD", direction="sell", dxy=101.48, us10y_yield=1.58
    )
    assert allowed_gold_sell is True

    # FX trades are allowed
    allowed_eur_sell, _ = RegimeClassifier.is_trade_allowed(
        symbol="EURUSD", direction="sell", dxy=101.48, us10y_yield=1.58
    )
    assert allowed_eur_sell is True


def test_regime_classifier_risk_on_allows_longs():
    env = RegimeClassifier.classify(dxy=98.5, us10y_yield=1.20)
    assert env.regime == MacroRegime.RISK_ON_EXPANSION
    assert env.allowed_commodity_longs is True
    assert env.allowed_crypto_longs is True

    allowed_gold, _ = RegimeClassifier.is_trade_allowed(symbol="XAUUSD", direction="buy", dxy=98.5, us10y_yield=1.20)
    assert allowed_gold is True

    allowed_btc, _ = RegimeClassifier.is_trade_allowed(symbol="BTCUSD", direction="buy", dxy=98.5, us10y_yield=1.20)
    assert allowed_btc is True
