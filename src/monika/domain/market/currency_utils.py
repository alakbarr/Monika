# ==============================================================================
# File: utils/market/currency_utils.py
# ==============================================================================

"""
Utilitas pemetaan simbol instrumen trading ke mata uang terkait.
Digunakan secara terpusat oleh RiskGate, ExecutionService, Schedulers, dan Analysis Stages.
"""

from typing import Tuple

SYMBOL_CURRENCIES: dict[str, Tuple[str, ...]] = {
    "XAUUSD": ("XAU", "USD"),
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "USDJPY": ("USD", "JPY"),
    "AUDUSD": ("AUD", "USD"),
    "XTIUSD": ("OIL", "USD"),
    "XBRUSD": ("OIL", "USD"),
    "BTCUSD": ("BTC", "USD"),
}


def get_symbol_currencies(symbol: str) -> Tuple[str, ...]:
    """
    Mengembalikan tuple kode mata uang atau komoditas terkait untuk simbol yang diberikan.

    Contoh:
        get_symbol_currencies("GBPUSD") -> ("GBP", "USD")
        get_symbol_currencies("XTIUSD") -> ("OIL", "USD")
        get_symbol_currencies("GOLD")   -> ("XAU", "USD")
        get_symbol_currencies("USDCAD") -> ("USD", "CAD")
    """
    sym = (symbol or "").strip().upper().replace("/", "").replace("_", "").replace(".", "").replace("-", "")
    if not sym:
        return ("USD",)

    from monika.domain.market.instrument_identity import ALIAS_MAP

    canonical = ALIAS_MAP.get(sym, sym)
    if canonical in SYMBOL_CURRENCIES:
        return SYMBOL_CURRENCIES[canonical]
    if len(canonical) == 6 and canonical.isalpha():
        return (canonical[:3], canonical[3:])
    return ("USD",)
