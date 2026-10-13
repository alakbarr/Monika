"""Market, price, technical, macroeconomic, and SMC models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from monika.infrastructure.database.domain_models.base import Base, _utcnow


class TreasuryYield(Base):
    """Yield obligasi pemerintah AS (dari FRED)."""

    __tablename__ = "treasury_yields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenor: Mapped[str] = mapped_column(String(32))  # 2Y, 5Y, 10Y, 30Y, 10Y_INFLATION, 10Y_REAL
    yield_percent: Mapped[float] = mapped_column(Float)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("idx_treasury_tenor_date", "tenor", "date"),)


class InterestRate(Base):
    """Suku bunga bank sentral (FED, ECB, BOE, BOJ, RBA)."""

    __tablename__ = "interest_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank: Mapped[str] = mapped_column(String(20))  # FED, ECB, BOE, BOJ, RBA
    rate_percent: Mapped[float] = mapped_column(Float)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_meeting_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class FedWatchProbability(Base):
    """Probabilitas keputusan The Fed (dari CME FedWatch)."""

    __tablename__ = "fedwatch_probabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_date: Mapped[str] = mapped_column(String(20))
    probabilities_json: Mapped[str] = mapped_column(Text)  # JSON: {"hold": 85.2, "cut_25": 14.8, ...}
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CentralBankRateExpectation(Base):
    """Ekspektasi keputusan suku bunga bank sentral (FED, ECB, BOE, BOJ, RBA)."""

    __tablename__ = "central_bank_rate_expectations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank: Mapped[str] = mapped_column(String(20), index=True)  # FED, ECB, BOE, BOJ, RBA
    meeting_date: Mapped[str] = mapped_column(String(30))
    current_rate: Mapped[float] = mapped_column(Float, default=0.0)
    prob_hike: Mapped[float] = mapped_column(Float, default=0.0)
    prob_hold: Mapped[float] = mapped_column(Float, default=0.0)
    prob_cut: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(50), default="centralbank.watch")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("idx_cb_rate_exp_bank_date", "bank", "meeting_date"),)


class COTReport(Base):
    """COT Report — positioning institusional (dari CFTC API)."""

    __tablename__ = "cot_report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    market_code: Mapped[str] = mapped_column(String(20), index=True)
    dealer_long: Mapped[int] = mapped_column(Integer)
    dealer_short: Mapped[int] = mapped_column(Integer)
    asset_mgr_long: Mapped[int] = mapped_column(Integer)
    asset_mgr_short: Mapped[int] = mapped_column(Integer)
    leveraged_long: Mapped[int] = mapped_column(Integer)
    leveraged_short: Mapped[int] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("idx_cot_market_date", "market_code", "report_date"),)


class VIXData(Base):
    """Indeks volatilitas VIX (dari yfinance)."""

    __tablename__ = "vix_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True)
    close: Mapped[float] = mapped_column(Float)


class DXYData(Base):
    """US Dollar Index (DXY) harian dari Yahoo Finance."""

    __tablename__ = "dxy_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True)
    close: Mapped[float] = mapped_column(Float)


class BondYieldData(Base):
    """Yield obligasi pemerintah internasional harian (yfinance + ECB fallback)."""

    __tablename__ = "bond_yield_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_tenor: Mapped[str] = mapped_column(String(20))  # DE_10Y, UK_10Y, JP_10Y, AU_10Y
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    yield_percent: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        Index("idx_bond_yield_ct_date", "country_tenor", "date"),
        UniqueConstraint("country_tenor", "date", name="uq_bond_yield_country_date"),
    )


class EconomicReportDecomposition(Base):
    """Universal granular sub-component storage for all macroeconomic releases (US & G10)."""

    __tablename__ = "economic_report_decompositions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_type: Mapped[str] = mapped_column(
        String(30), index=True
    )  # CPI, PPI, PCE, NFP, JOLTS, RETAIL_SALES, GDP, PMI, ECI, UMICH
    country: Mapped[str] = mapped_column(String(10), default="US", index=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", index=True)
    period: Mapped[str] = mapped_column(String(20), index=True)  # e.g. "2026-09", "2026-Q3"
    release_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    component_name: Mapped[str] = mapped_column(
        String(120)
    )  # e.g. "Shelter", "Supercore Services", "Private Payrolls", "ISM Prices Paid"
    category: Mapped[str] = mapped_column(
        String(50)
    )  # "headline", "core", "sticky", "transitory", "leading", "revision"
    weight_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_actual: Mapped[float] = mapped_column(Float)
    value_forecast: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_previous: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mom_change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    yoy_change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    contribution_bps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_noise: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("report_type", "country", "period", "component_name", name="uq_report_decomp"),
        Index("idx_report_lookup", "report_type", "currency", "period"),
    )


class CentralBankDocument(Base):
    """Full-text repository for central bank monetary policy statements, minutes, and projections."""

    __tablename__ = "central_bank_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank: Mapped[str] = mapped_column(String(20), index=True)  # FED, ECB, BOE, BOJ, SNB, RBA, BOC
    doc_type: Mapped[str] = mapped_column(
        String(30), index=True
    )  # STATEMENT, MINUTES, DOT_PLOT, BEIGE_BOOK, PRESS_CONF
    meeting_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    title: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str] = mapped_column(String(1000))
    full_text: Mapped[str] = mapped_column(Text)
    paragraphs_json: Mapped[str] = mapped_column(Text)  # JSON array of paragraphs
    hawkish_dovish_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # -1.0 (dovish) to +1.0 (hawkish)
    key_phrases_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("bank", "doc_type", "meeting_date", name="uq_cb_doc_record"),
        Index("idx_cb_doc_bank_type_date", "bank", "doc_type", "meeting_date"),
    )


class MacroLiquidityCreditMetric(Base):
    """Storage for central bank balance sheets, systemic liquidity, debt auctions, and credit stress metrics."""

    __tablename__ = "macro_liquidity_credit_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # FED_NET_LIQUIDITY, WALCL, TGA, ON_RRP, TREASURY_AUCTION_10Y, HY_OAS, SOFR, TIC_FLOWS
    country: Mapped[str] = mapped_column(String(10), default="US", index=True)
    record_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    value: Mapped[float] = mapped_column(Float)
    previous_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="USD_BILLIONS")
    regime: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )  # EXPANSIONARY, CONTRACTIONARY, STRESS, BENIGN
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("metric_type", "country", "record_date", name="uq_macro_liq_metric"),
        Index("idx_liq_lookup", "metric_type", "record_date"),
    )


class PriceOHLCV(Base):
    """Data harga OHLCV dari MT5."""

    __tablename__ = "price_ohlcv"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(10))  # H1, H4, D1
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)

    # Numeric expanded columns (Phase 5 dual-read)
    open_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    high_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    low_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    close_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    volume_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)

    __table_args__ = (
        Index("idx_price_sym_tf_ts", "symbol", "timeframe", "timestamp"),
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_price_sym_tf_ts"),
    )


class TechnicalIndicator(Base):
    """Indikator teknikal terhitung (MA, RSI, MACD, dll)."""

    __tablename__ = "technical_indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(10))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    indicator_name: Mapped[str] = mapped_column(String(50))  # MA_20, RSI_14, MACD, etc.
    value_json: Mapped[str] = mapped_column(Text)  # JSON value(s)

    __table_args__ = (Index("idx_indicator_sym_tf_ts", "symbol", "timeframe", "timestamp", "indicator_name"),)


class SwingPoint(Base):
    """Swing high/low yang terdeteksi dari data harga."""

    __tablename__ = "swing_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(10))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    type: Mapped[str] = mapped_column(String(10))  # high, low
    price: Mapped[float] = mapped_column(Float)

    __table_args__ = (Index("idx_swing_sym_tf", "symbol", "timeframe"),)


class SRZone(Base):
    """Support & Resistance zone dari klaster swing points."""

    __tablename__ = "sr_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(10))
    price_high: Mapped[float] = mapped_column(Float)
    price_low: Mapped[float] = mapped_column(Float)
    strength: Mapped[int] = mapped_column(Integer)  # touch count
    last_touched: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_sr_sym_tf", "symbol", "timeframe"),)


class LiquidityZone(Base):
    """Zona likuiditas di atas/bawah swing points signifikan."""

    __tablename__ = "liquidity_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(10))
    zone_high: Mapped[float] = mapped_column(Float)
    zone_low: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String(20))  # above_swing_high, below_swing_low
    identified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("idx_liq_sym_tf", "symbol", "timeframe"),)


class FVGZone(Base):
    """Fair Value Gap (ICT/SMC concept)."""

    __tablename__ = "fvg_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(10))
    gap_high: Mapped[float] = mapped_column(Float)
    gap_low: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(10))  # bullish, bearish
    formed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_fvg_sym_tf", "symbol", "timeframe"),)


class OrderBlock(Base):
    """Order Block (SMC concept) — candle terakhir sebelum pergerakan impulsif."""

    __tablename__ = "order_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(10))
    direction: Mapped[str] = mapped_column(String(10))  # bullish, bearish
    price_high: Mapped[float] = mapped_column(Float)
    price_low: Mapped[float] = mapped_column(Float)
    formed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mitigated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_ob_sym_tf", "symbol", "timeframe"),)


class StructureBreak(Base):
    """Break of Structure (BOS) / Change of Character (ChoCH)."""

    __tablename__ = "structure_breaks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(10))
    type: Mapped[str] = mapped_column(String(10))  # BOS, ChoCH
    direction: Mapped[str] = mapped_column(String(10))  # bullish, bearish
    price: Mapped[float] = mapped_column(Float)
    formed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("idx_sb_sym_tf", "symbol", "timeframe"),)


class PatternScreeningCache(Base):
    """Cache for multi-timeframe historical chart pattern similarity screening results."""

    __tablename__ = "pattern_screening_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    screened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    overall_bias: Mapped[str] = mapped_column(String(10), nullable=False)  # bullish, bearish, neutral
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)  # high, medium, low, none
    consensus_bullish_pct: Mapped[float] = mapped_column(Float, default=0.5)
    consensus_bearish_pct: Mapped[float] = mapped_column(Float, default=0.5)
    has_timeframe_conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    significant_timeframes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    per_timeframe_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    full_result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("idx_pattern_cache_sym_at", "symbol", "screened_at"),)


__all__ = [
    "TreasuryYield",
    "InterestRate",
    "FedWatchProbability",
    "CentralBankRateExpectation",
    "COTReport",
    "VIXData",
    "DXYData",
    "BondYieldData",
    "EconomicReportDecomposition",
    "CentralBankDocument",
    "MacroLiquidityCreditMetric",
    "PriceOHLCV",
    "TechnicalIndicator",
    "SwingPoint",
    "SRZone",
    "LiquidityZone",
    "FVGZone",
    "OrderBlock",
    "StructureBreak",
    "PatternScreeningCache",
]
