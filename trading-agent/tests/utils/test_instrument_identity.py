# ==============================================================================
# File: tests/utils/test_instrument_identity.py
# ==============================================================================

import pytest
from utils.market.instrument_identity import resolve_instrument_identity


def test_resolve_instrument_identity_known_commodities():
    """Verify alias mapping and canonical resolution for commodities."""
    gold1 = resolve_instrument_identity("GOLD")
    gold2 = resolve_instrument_identity("XAUUSD")
    gold3 = resolve_instrument_identity("xau/usd")

    assert gold1.canonical_symbol == "XAUUSD"
    assert gold2.canonical_symbol == "XAUUSD"
    assert gold3.canonical_symbol == "XAUUSD"
    assert gold1.asset_class == "COMMODITY"
    assert gold1.cot_code == "088691"
    assert gold1.pip_size == 0.01

    oil = resolve_instrument_identity("WTI")
    assert oil.canonical_symbol == "XTIUSD"
    assert oil.asset_class == "COMMODITY"
    assert oil.cot_code == "067651"


def test_resolve_instrument_identity_forex():
    """Verify forex pairs resolution, base/quote extraction, and pip sizes."""
    eur = resolve_instrument_identity("EURUSD")
    assert eur.canonical_symbol == "EURUSD"
    assert eur.asset_class == "FOREX"
    assert eur.base_currency == "EUR"
    assert eur.quote_currency == "USD"
    assert eur.pip_size == 0.0001

    jpy = resolve_instrument_identity("USDJPY")
    assert jpy.canonical_symbol == "USDJPY"
    assert jpy.pip_size == 0.01


def test_resolve_instrument_identity_crypto():
    """Verify crypto identity and 24/7 session flag."""
    btc = resolve_instrument_identity("btc")
    assert btc.canonical_symbol == "BTCUSD"
    assert btc.asset_class == "CRYPTO"
    assert btc.is_24_7 is True
