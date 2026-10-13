"""
Risk Domain Entities - Pure mathematical definitions and instrument specifications.
Independent from broker infrastructure and database models.
"""

from dataclasses import dataclass


@dataclass
class InstrumentSpec:
    """Spesifikasi instrumen trading."""

    symbol: str
    pip_size: float  # size of 1 pip (e.g. 0.0001 for EURUSD, 0.01 for XAUUSD)
    pip_value_usd: float  # USD value of 1 pip per 1 standard lot
    contract_size: float  # units per lot (100 for gold oz, 100_000 for FX)
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    digits: int = 5
    stops_level_pips: float = 0.0
    _source: str = "default"

    @property
    def pip_value_per_lot(self) -> float:
        """Alias: Nilai USD dari 1 pip per 1 lot."""
        return self.pip_value_usd


# Spesifikasi default saat MT5 offline
DEFAULT_INSTRUMENTS: dict[str, InstrumentSpec] = {
    "XAUUSD": InstrumentSpec(
        symbol="XAUUSD",
        pip_size=0.01,
        pip_value_usd=1.0,  # $1 per 0.01 pip per lot (100 oz * $0.01)
        contract_size=100,
        digits=2,
    ),
    "EURUSD": InstrumentSpec(
        symbol="EURUSD",
        pip_size=0.0001,
        pip_value_usd=10.0,
        contract_size=100_000,
        digits=5,
    ),
    "GBPUSD": InstrumentSpec(
        symbol="GBPUSD",
        pip_size=0.0001,
        pip_value_usd=10.0,
        contract_size=100_000,
        digits=5,
    ),
    "USDJPY": InstrumentSpec(
        symbol="USDJPY",
        pip_size=0.01,
        pip_value_usd=6.67,  # fallback only - akan di-override dynamically
        contract_size=100_000,
        digits=3,
    ),
    "AUDUSD": InstrumentSpec(
        symbol="AUDUSD",
        pip_size=0.0001,
        pip_value_usd=10.0,
        contract_size=100_000,
        digits=5,
    ),
    "XTIUSD": InstrumentSpec(
        symbol="XTIUSD",
        pip_size=0.01,
        pip_value_usd=10.0,  # Verified live MT5: 1000 bbl/contract * $0.01 = $10.0/pip
        contract_size=1000,
        digits=2,
    ),
    "BTCUSD": InstrumentSpec(
        symbol="BTCUSD",
        pip_size=1.0,  # 1 USD = 1 pip
        pip_value_usd=1.0,  # 1 BTC * $1 = $1/pip
        contract_size=1,
        min_lot=0.01,
        max_lot=10.0,  # cap at 10 BTC
        lot_step=0.01,
        digits=2,
    ),
    "XBRUSD": InstrumentSpec(
        symbol="XBRUSD",
        pip_size=0.01,
        pip_value_usd=10.0,  # Verified live MT5: 1000 bbl/contract * $0.01 = $10.0/pip
        contract_size=1000,
        digits=2,
    ),
    "USDCAD": InstrumentSpec(
        symbol="USDCAD",
        pip_size=0.0001,
        pip_value_usd=10.0,
        contract_size=100_000,
        digits=5,
    ),
    "USDCHF": InstrumentSpec(
        symbol="USDCHF",
        pip_size=0.0001,
        pip_value_usd=10.0,
        contract_size=100_000,
        digits=5,
    ),
    "ETHUSD": InstrumentSpec(
        symbol="ETHUSD",
        pip_size=0.1,
        pip_value_usd=1.0,  # Verified live MT5: 10 ETH/contract * $0.10 = $1.0/pip
        contract_size=10,  # Verified live MT5: 1 lot = 10 ETH
        min_lot=0.01,
        max_lot=50.0,
        lot_step=0.01,
        digits=2,
    ),
}
