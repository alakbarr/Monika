import pytest
from utils.market.currency_utils import get_symbol_currencies, SYMBOL_CURRENCIES

def test_get_symbol_currencies_known_symbols():
    assert get_symbol_currencies("GBPUSD") == ("GBP", "USD")
    assert get_symbol_currencies("EURUSD") == ("EUR", "USD")
    assert get_symbol_currencies("XAUUSD") == ("XAU", "USD")
    assert get_symbol_currencies("USDJPY") == ("USD", "JPY")
    assert get_symbol_currencies("AUDUSD") == ("AUD", "USD")
    assert get_symbol_currencies("XTIUSD") == ("OIL", "USD")
    assert get_symbol_currencies("XBRUSD") == ("OIL", "USD")
    assert get_symbol_currencies("BTCUSD") == ("BTC", "USD")

def test_get_symbol_currencies_case_insensitive_and_whitespace():
    assert get_symbol_currencies("  gbpusd  ") == ("GBP", "USD")
    assert get_symbol_currencies("eurusd") == ("EUR", "USD")
    assert get_symbol_currencies("xbrusd") == ("OIL", "USD")

def test_get_symbol_currencies_heuristic_fallback():
    assert get_symbol_currencies("USDCAD") == ("USD", "CAD")
    assert get_symbol_currencies("NZDUSD") == ("NZD", "USD")
    assert get_symbol_currencies("UNKNOWN_SYMBOL") == ("USD",)
    assert get_symbol_currencies("") == ("USD",)
    assert get_symbol_currencies(None) == ("USD",)
