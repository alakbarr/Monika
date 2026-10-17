# ==============================================================================
# File: tests/utils/test_instrument_identity.py
# ==============================================================================

import pytest
from monika.domain.market.instrument_identity import resolve_instrument_identity


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
    """Verify crypto identity, 24/7 session flag, and CME COT code."""
    btc = resolve_instrument_identity("btc")
    assert btc.canonical_symbol == "BTCUSD"
    assert btc.asset_class == "CRYPTO"
    assert btc.is_24_7 is True
    assert btc.cot_code == "133741"


def test_cot_code_helpers_and_mappings():
    """Verify single-source-of-truth COT code helpers and alias mappings."""
    from monika.domain.market.instrument_identity import (
        COT_CODE_TO_SYMBOL_MAP,
        SYMBOL_TO_COT_MAP,
        get_cot_code_for_symbol,
        get_symbol_for_cot_code,
    )

    assert get_cot_code_for_symbol("GOLD") == "088691"
    assert get_cot_code_for_symbol("XAUUSD") == "088691"
    assert get_cot_code_for_symbol("WTI") == "067651"
    assert get_cot_code_for_symbol("UKOIL") == "067651"
    assert get_cot_code_for_symbol("BTC") == "133741"
    assert get_cot_code_for_symbol("BTCUSD") == "133741"
    assert get_cot_code_for_symbol("UNKNOWN_COIN") is None

    assert get_symbol_for_cot_code("088691") == "XAUUSD"
    assert get_symbol_for_cot_code("067651") == "XTIUSD"
    assert get_symbol_for_cot_code("133741") == "BTCUSD"
    assert get_symbol_for_cot_code("099741") == "EURUSD"

    assert SYMBOL_TO_COT_MAP["BTCUSD"] == "133741"
    assert SYMBOL_TO_COT_MAP["XBRUSD"] == "067651"
    assert COT_CODE_TO_SYMBOL_MAP["133741"] == "BTCUSD"
