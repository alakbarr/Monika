# ==============================================================================
# File: utils/market/instrument_identity.py
# ==============================================================================

from dataclasses import dataclass
import functools
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger("TradingAgent.InstrumentIdentity")


@dataclass(frozen=True)
class InstrumentIdentity:
    """Canonical, deterministic identity of a traded instrument (H-4)."""
    symbol: str
    canonical_symbol: str
    official_name: str
    asset_class: str  # "FOREX", "COMMODITY", "CRYPTO", "INDEX"
    base_currency: str
    quote_currency: str
    pip_size: float
    point_size: float
    cot_code: Optional[str] = None
    trading_sessions: Tuple[str, ...] = ("London", "New York")
    is_24_7: bool = False

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "canonical_symbol": self.canonical_symbol,
            "official_name": self.official_name,
            "asset_class": self.asset_class,
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
            "pip_size": self.pip_size,
            "point_size": self.point_size,
            "cot_code": self.cot_code,
            "trading_sessions": list(self.trading_sessions),
            "is_24_7": self.is_24_7,
        }


KNOWN_INSTRUMENTS: Dict[str, InstrumentIdentity] = {
    "XAUUSD": InstrumentIdentity(
        symbol="XAUUSD",
        canonical_symbol="XAUUSD",
        official_name="Gold / US Dollar",
        asset_class="COMMODITY",
        base_currency="XAU",
        quote_currency="USD",
        pip_size=0.01,
        point_size=0.01,
        cot_code="088691",
        trading_sessions=("London", "New York"),
        is_24_7=False,
    ),
    "XTIUSD": InstrumentIdentity(
        symbol="XTIUSD",
        canonical_symbol="XTIUSD",
        official_name="WTI Crude Oil / US Dollar",
        asset_class="COMMODITY",
        base_currency="XTI",
        quote_currency="USD",
        pip_size=0.01,
        point_size=0.01,
        cot_code="067651",
        trading_sessions=("London", "New York"),
        is_24_7=False,
    ),
    "EURUSD": InstrumentIdentity(
        symbol="EURUSD",
        canonical_symbol="EURUSD",
        official_name="Euro / US Dollar",
        asset_class="FOREX",
        base_currency="EUR",
        quote_currency="USD",
        pip_size=0.0001,
        point_size=0.00001,
        cot_code="099741",
        trading_sessions=("London", "New York"),
        is_24_7=False,
    ),
    "GBPUSD": InstrumentIdentity(
        symbol="GBPUSD",
        canonical_symbol="GBPUSD",
        official_name="British Pound / US Dollar",
        asset_class="FOREX",
        base_currency="GBP",
        quote_currency="USD",
        pip_size=0.0001,
        point_size=0.00001,
        cot_code="096742",
        trading_sessions=("London", "New York"),
        is_24_7=False,
    ),
    "USDJPY": InstrumentIdentity(
        symbol="USDJPY",
        canonical_symbol="USDJPY",
        official_name="US Dollar / Japanese Yen",
        asset_class="FOREX",
        base_currency="USD",
        quote_currency="JPY",
        pip_size=0.01,
        point_size=0.001,
        cot_code="097741",
        trading_sessions=("Tokyo", "London", "New York"),
        is_24_7=False,
    ),
    "AUDUSD": InstrumentIdentity(
        symbol="AUDUSD",
        canonical_symbol="AUDUSD",
        official_name="Australian Dollar / US Dollar",
        asset_class="FOREX",
        base_currency="AUD",
        quote_currency="USD",
        pip_size=0.0001,
        point_size=0.00001,
        cot_code="232741",
        trading_sessions=("Sydney", "Tokyo", "London", "New York"),
        is_24_7=False,
    ),
    "USDCAD": InstrumentIdentity(
        symbol="USDCAD",
        canonical_symbol="USDCAD",
        official_name="US Dollar / Canadian Dollar",
        asset_class="FOREX",
        base_currency="USD",
        quote_currency="CAD",
        pip_size=0.0001,
        point_size=0.00001,
        cot_code="090741",
        trading_sessions=("New York",),
        is_24_7=False,
    ),
    "USDCHF": InstrumentIdentity(
        symbol="USDCHF",
        canonical_symbol="USDCHF",
        official_name="US Dollar / Swiss Franc",
        asset_class="FOREX",
        base_currency="USD",
        quote_currency="CHF",
        pip_size=0.0001,
        point_size=0.00001,
        cot_code="092741",
        trading_sessions=("London", "New York"),
        is_24_7=False,
    ),
    "BTCUSD": InstrumentIdentity(
        symbol="BTCUSD",
        canonical_symbol="BTCUSD",
        official_name="Bitcoin / US Dollar",
        asset_class="CRYPTO",
        base_currency="BTC",
        quote_currency="USD",
        pip_size=1.0,
        point_size=0.01,
        cot_code=None,
        trading_sessions=("Global 24/7",),
        is_24_7=True,
    ),
    "XBRUSD": InstrumentIdentity(
        symbol="XBRUSD",
        canonical_symbol="XBRUSD",
        official_name="Brent Crude Oil / US Dollar",
        asset_class="COMMODITY",
        base_currency="XBR",
        quote_currency="USD",
        pip_size=0.01,
        point_size=0.01,
        cot_code=None,
        trading_sessions=("London", "New York"),
        is_24_7=False,
    ),
    "ETHUSD": InstrumentIdentity(
        symbol="ETHUSD",
        canonical_symbol="ETHUSD",
        official_name="Ethereum / US Dollar",
        asset_class="CRYPTO",
        base_currency="ETH",
        quote_currency="USD",
        pip_size=0.1,
        point_size=0.01,
        cot_code=None,
        trading_sessions=("Global 24/7",),
        is_24_7=True,
    ),
}

ALIAS_MAP: Dict[str, str] = {
    "GOLD": "XAUUSD",
    "XAU": "XAUUSD",
    "SPOTGOLD": "XAUUSD",
    "OIL": "XTIUSD",
    "CRUDE": "XTIUSD",
    "WTI": "XTIUSD",
    "USOIL": "XTIUSD",
    "CL": "XTIUSD",
    "BRENT": "XBRUSD",
    "UKOIL": "XBRUSD",
    "BRENTCRUDE": "XBRUSD",
    "BRN": "XBRUSD",
    "BITCOIN": "BTCUSD",
    "BTC": "BTCUSD",
    "ETHEREUM": "ETHUSD",
    "ETH": "ETHUSD",
    "DOW": "US30",
    "DJI": "US30",
    "SPX": "US500",
    "SP500": "US500",
    "NAS100": "USTEC",
    "NASDAQ": "USTEC",
}


@functools.lru_cache(maxsize=256)
def resolve_instrument_identity(raw_symbol: str) -> InstrumentIdentity:
    """Deterministically resolves any ticker, symbol, or alias into an immutable InstrumentIdentity."""
    if not raw_symbol or not isinstance(raw_symbol, str):
        raw_symbol = "UNKNOWN"

    clean = raw_symbol.strip().upper().replace("/", "").replace("_", "").replace(".", "").replace("-", "")

    # Alias check
    canonical = ALIAS_MAP.get(clean, clean)

    if canonical in KNOWN_INSTRUMENTS:
        return KNOWN_INSTRUMENTS[canonical]

    # Heuristic fallback for unlisted FX or Crypto pairs
    if len(canonical) == 6:
        base = canonical[:3]
        quote = canonical[3:]
        is_jpy = quote == "JPY"
        return InstrumentIdentity(
            symbol=canonical,
            canonical_symbol=canonical,
            official_name=f"{base} / {quote}",
            asset_class="FOREX",
            base_currency=base,
            quote_currency=quote,
            pip_size=0.01 if is_jpy else 0.0001,
            point_size=0.001 if is_jpy else 0.00001,
            is_24_7=False,
        )

    # Generic fallback
    return InstrumentIdentity(
        symbol=canonical,
        canonical_symbol=canonical,
        official_name=canonical,
        asset_class="UNKNOWN",
        base_currency=canonical[:3] if len(canonical) >= 3 else canonical,
        quote_currency="USD",
        pip_size=0.0001,
        point_size=0.00001,
        is_24_7=False,
    )
