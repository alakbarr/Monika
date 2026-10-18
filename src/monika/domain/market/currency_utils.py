# ==============================================================================
# File: utils/market/currency_utils.py
# ==============================================================================

"""
Utilitas pemetaan simbol instrumen trading ke mata uang terkait.
Digunakan secara terpusat oleh RiskGate, ExecutionService, Schedulers, dan Analysis Stages.
"""

from typing import Tuple

SYMBOL_CURRENCIES: dict[str, Tuple[str, str]] = {
    "XAUUSD": ("XAU", "USD"),
    "XAGUSD": ("XAG", "USD"),
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "USDJPY": ("USD", "JPY"),
    "AUDUSD": ("AUD", "USD"),
    "NZDUSD": ("NZD", "USD"),
    "USDCAD": ("USD", "CAD"),
    "USDCHF": ("USD", "CHF"),
    "USDIDR": ("USD", "IDR"),
    "XTIUSD": ("OIL", "USD"),
    "XBRUSD": ("OIL", "USD"),
    "BTCUSD": ("BTC", "USD"),
    "ETHUSD": ("ETH", "USD"),
    "US30": ("USD", "USD"),
    "USTEC": ("USD", "USD"),
    "US500": ("USD", "USD"),
}


def get_symbol_currencies(symbol: str) -> Tuple[str, ...]:
    """
    Mengembalikan tuple kode mata uang atau komoditas terkait untuk simbol yang diberikan.
    Untuk simbol FX 6-huruf atau simbol terdaftar, mengembalikan (base_currency, quote_currency).
    Untuk simbol tidak dikenal atau kosong, fallback ke ('USD',).

    Contoh:
        get_symbol_currencies("GBPUSD") -> ("GBP", "USD")
        get_symbol_currencies("XTIUSD") -> ("OIL", "USD")
        get_symbol_currencies("GOLD")   -> ("XAU", "USD")
        get_symbol_currencies("USDCAD") -> ("USD", "CAD")
        get_symbol_currencies("USTEC")  -> ("USD", "USD")
        get_symbol_currencies("UNKNOWN")-> ("USD",)
    """
    sym = (symbol or "").strip().upper().replace("/", "").replace("_", "").replace(".", "").replace("-", "")
    if not sym:
        return ("USD",)

    from monika.domain.market.instrument_identity import ALIAS_MAP, KNOWN_INSTRUMENTS

    canonical = ALIAS_MAP.get(sym, sym)
    if canonical in SYMBOL_CURRENCIES:
        return SYMBOL_CURRENCIES[canonical]

    if canonical in KNOWN_INSTRUMENTS:
        ident = KNOWN_INSTRUMENTS[canonical]
        return (ident.base_currency, ident.quote_currency)

    if len(canonical) == 6 and canonical.isalpha():
        return (canonical[:3], canonical[3:])

    return ("USD",)
