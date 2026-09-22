# ==============================================================================
# File: database/models.py
# ==============================================================================

"""
Model Database untuk AI Trading Agent.
Semua 22 tabel dari spesifikasi §6, ditambah model Trade legacy.
Menggunakan SQLAlchemy 2.0 DeclarativeBase dengan pola async.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional, Union, Dict, Set, Any

from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, DateTime, Boolean, Text,
    Index, ForeignKey, UniqueConstraint, JSON, text, func, ARRAY, Enum as SQLAlchemyEnum
)
try:
    from sqlalchemy.dialects.postgresql import TSVECTOR
    TSVECTOR_TYPE = TSVECTOR().with_variant(Text, "sqlite")
except ImportError:
    TSVECTOR_TYPE = Text
TSVECTOR = TSVECTOR_TYPE
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column, synonym, validates


from utils.clock import now as _clock_now

def _utcnow() -> datetime:
    """Mengembalikan waktu saat ini dalam UTC (timezone-aware)."""
    return _clock_now()


class Base(DeclarativeBase):
    pass


# =============================================================================
# Model legacy (kompatibilitas ke belakang)
# =============================================================================

class Trade(Base):
    """Model trade lama (dipertahankan untuk kompatibilitas)."""
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # BUY or SELL
    entry_price: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))  # PENDING, OPEN, CLOSED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# =============================================================================
# 1-7: Data Mentah & Fundamental
# =============================================================================

class NewsItem(Base):
    """Berita dari semua sumber (scraper & RSS)."""
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)  # tradingview, kitco, rss_bloomberg, twitter, etc.
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(1000))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    currency_tags: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # comma-separated: "USD,EUR,XAU"
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    impact: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # BREAKING, HIGH, MEDIUM, LOW, NONE
    sentiment: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    prefilter_flags: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # IRRELEVANT, DUPLICATE
    key_data_point: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # Backward compatibility synonyms
    gemini_impact = synonym("impact")
    gemini_sentiment = synonym("sentiment")

    __table_args__ = (
        Index('idx_news_source_fetched', 'source', 'fetched_at'),
        Index('idx_news_url', 'url'),
    )


class NewsDigest(Base):
    """Digest berita yang dikompres model LLM untuk efisiensi token."""
    __tablename__ = "news_digest"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    period_hours: Mapped[int] = mapped_column(Integer)
    digest_text: Mapped[str] = mapped_column(Text)
    items_processed: Mapped[int] = mapped_column(Integer, default=0)


class NewsDigestSlice(Base):
    """Rolling 2-hour digest snapshot per currency."""
    __tablename__ = "news_digest_slices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    trigger: Mapped[str] = mapped_column(String(20), default='scheduled')  # 'scheduled' | 'breaking' | 'manual'
    period_hours: Mapped[float] = mapped_column(Float, default=2.0)
    items_processed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    breaking_count: Mapped[int] = mapped_column(Integer, default=0)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    currency_sections: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON dict per currency
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index('ix_news_digest_slices_period', 'period_start', 'period_end'),
    )


class MarketChronicle(Base):
    """
    Kronologi peristiwa makro signifikan yang persisten.
    Dikurasi secara otomatis dari BREAKING/HIGH news + FundamentalBrief.
    """
    __tablename__ = "market_chronicle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)  # policy_change | geopolitical | data_shock | regime_shift | institutional
    headline: Mapped[str] = mapped_column(String(300), nullable=False)
    narrative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    currencies_affected: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    severity: Mapped[str] = mapped_column(String(10), default='medium')  # low | medium | high | critical
    source_news_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_brief_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_ongoing: Mapped[bool] = mapped_column(Boolean, default=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    search_vector: Mapped[Optional[Any]] = mapped_column(TSVECTOR, nullable=True)

    __table_args__ = (
        Index('idx_chronicle_fts', 'search_vector', postgresql_using='gin'),
    )



class EconomicCalendar(Base):
    """Kalender ekonomi (rilis data makro)."""
    __tablename__ = "economic_calendar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_name: Mapped[str] = mapped_column(String(200))
    country: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), index=True)
    impact: Mapped[str] = mapped_column(String(10))  # high, medium, low
    actual: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    forecast: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    previous: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    event_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    surprise_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint('currency', 'event_name', 'event_time', name='uq_calendar_event'),
    )


class TreasuryYield(Base):
    """Yield obligasi pemerintah AS (dari FRED)."""
    __tablename__ = "treasury_yields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenor: Mapped[str] = mapped_column(String(32))  # 2Y, 5Y, 10Y, 30Y, 10Y_INFLATION, 10Y_REAL
    yield_percent: Mapped[float] = mapped_column(Float)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index('idx_treasury_tenor_date', 'tenor', 'date'),
    )


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

    __table_args__ = (
        Index('idx_cb_rate_exp_bank_date', 'bank', 'meeting_date'),
    )


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

    __table_args__ = (
        Index('idx_cot_market_date', 'market_code', 'report_date'),
    )


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
        Index('idx_bond_yield_ct_date', 'country_tenor', 'date'),
        UniqueConstraint('country_tenor', 'date', name='uq_bond_yield_country_date'),
    )


# =============================================================================
# 8-13: Data Harga & Teknikal
# =============================================================================

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

    __table_args__ = (
        Index('idx_price_sym_tf_ts', 'symbol', 'timeframe', 'timestamp'),
        UniqueConstraint('symbol', 'timeframe', 'timestamp', name='uq_price_sym_tf_ts'),
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

    __table_args__ = (
        Index('idx_indicator_sym_tf_ts', 'symbol', 'timeframe', 'timestamp', 'indicator_name'),
    )


class SwingPoint(Base):
    """Swing high/low yang terdeteksi dari data harga."""
    __tablename__ = "swing_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(10))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    type: Mapped[str] = mapped_column(String(10))  # high, low
    price: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        Index('idx_swing_sym_tf', 'symbol', 'timeframe'),
    )


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

    __table_args__ = (
        Index('idx_sr_sym_tf', 'symbol', 'timeframe'),
    )


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

    __table_args__ = (
        Index('idx_liq_sym_tf', 'symbol', 'timeframe'),
    )


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

    __table_args__ = (
        Index('idx_fvg_sym_tf', 'symbol', 'timeframe'),
    )


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

    __table_args__ = (
        Index('idx_ob_sym_tf', 'symbol', 'timeframe'),
    )


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

    __table_args__ = (
        Index('idx_sb_sym_tf', 'symbol', 'timeframe'),
    )


# =============================================================================
# 14-16: Hasil Analisis AI
# =============================================================================

class FundamentalBrief(Base):
    """Brief fundamental makro dari AI Tahap 1."""
    __tablename__ = "fundamental_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    content_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    structured_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON sesuai spec §7.1
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_sentiment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Debate Phase
    debate_bull_thesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    debate_bear_thesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    debate_winner: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    debate_escalation_required: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Relationship
    analyses = relationship("AssetAnalysis", back_populates="brief", lazy="noload")

    @property
    def currency_bias(self) -> dict:
        if self.structured_json:
            try:
                import json
                parsed = json.loads(self.structured_json)
                if isinstance(parsed, dict):
                    return parsed.get("currency_bias", {})
            except Exception:
                return {}
        return {}

    @property
    def macro_regime(self) -> str:
        if self.structured_json:
            try:
                import json
                parsed = json.loads(self.structured_json)
                if isinstance(parsed, dict):
                    return parsed.get("macro_regime", "") or ""
            except Exception:
                return ""
        return ""

    @property
    def macro_narrative(self) -> str:
        if self.structured_json:
            try:
                import json
                parsed = json.loads(self.structured_json)
                if isinstance(parsed, dict):
                    return parsed.get("macro_narrative", "") or ""
            except Exception:
                return ""
        return ""


class AssetAnalysis(Base):
    """Keputusan analisis per-aset dari AI Tahap 2."""
    __tablename__ = "asset_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    brief_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('fundamental_briefs.id'), nullable=True)
    decision: Mapped[str] = mapped_column(String(10))  # buy, sell, avoid, wait
    confidence: Mapped[float] = mapped_column(Float)
    entry_zone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON entry condition
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    invalidation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reevaluation_trigger: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priced_in_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    priced_in_override_justification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confluence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confluence_factors_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list of active factor names
    specialist_biases_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invalidation_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    invalidation_direction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # 'above' or 'below'
    execution_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Values: None (not yet processed), 'approved', 'rejected', 'executed', 'blocked'
    execution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    market_regime_at_analysis: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    risk_multiplier: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=1.0)

    # Debate Results
    debate_bull_thesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    debate_bear_dissent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    debate_verdict: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    debate_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Phase 3 Context tracking
    decision_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_strategy_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    pair_group_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    was_debate_modified: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    was_ssvp_suppressed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)

    # NEW: Context tracking
    context_snapshot_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    brief_age_at_analysis_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ssvp_cds_score_at_analysis: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Intraday Range Awareness
    adr_at_analysis: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    adr_tp_pct_used: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    adr_sl_pct_used: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Ground truth validation fields
    price_at_analysis: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_4h_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_24h_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    direction_correct_4h: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    direction_correct_24h: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Relationships
    brief = relationship("FundamentalBrief", back_populates="analyses", lazy="noload")
    triggers = relationship("TradeTrigger", back_populates="analysis", lazy="noload")

    @property
    def entry_price(self) -> Optional[float]:
        """Ekstrak harga entry dari field entry_zone JSON secara aman."""
        if not self.entry_zone:
            return None
        if isinstance(self.entry_zone, dict):
            try:
                p = float(self.entry_zone.get("price", 0.0))
                return p if p > 0 else None
            except (TypeError, ValueError):
                return None
        try:
            import json
            data = json.loads(self.entry_zone)
            if isinstance(data, dict):
                p = float(data.get("price", 0.0))
                return p if p > 0 else None
        except Exception:
            pass
        return None

    @property
    def invalidation_condition(self) -> Optional[str]:
        """Alias property untuk invalidation text."""
        return self.invalidation

    __table_args__ = (
        Index('idx_analysis_sym_date', 'symbol', 'generated_at'),
    )


class TradeTrigger(Base):
    """Trigger kondisional untuk re-evaluasi atau eksekusi."""
    __tablename__ = "trade_triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_analysis_id: Mapped[int] = mapped_column(Integer, ForeignKey('asset_analysis.id'), index=True)
    trigger_type: Mapped[str] = mapped_column(String(20))  # price_level, indicator, time, news
    condition_json: Mapped[str] = mapped_column(Text)  # JSON condition detail
    status: Mapped[str] = mapped_column(String(10), default='pending')  # pending, fired, cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    fired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship
    analysis = relationship("AssetAnalysis", back_populates="triggers", lazy="noload")

    __table_args__ = (
        Index('idx_trigger_status', 'status'),
    )


class MT5Signal(Base):
    """Korelasi antara hasil analisis AI dan eksekusi MT5."""
    __tablename__ = "mt5_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_analysis_id: Mapped[int] = mapped_column(Integer, ForeignKey('asset_analysis.id'), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(10)) # buy, sell
    status: Mapped[str] = mapped_column(String(20), default="pending") # pending, sent, executed, failed
    mt5_ticket: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    analysis = relationship("AssetAnalysis", backref="mt5_signals", lazy="noload")


# =============================================================================
# 17-19: Eksekusi & Risiko
# =============================================================================

class InvalidOrderStateTransitionError(ValueError):
    """Raised when an illegal order lifecycle state transition is attempted."""
    pass


class OrderStatus(str, PyEnum):
    """Order lifecycle status model."""
    PENDING_SUBMIT = "pending_submit"
    INTENT_COMMITTED = "intent_committed"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    ABORT_REQUESTED = "abort_requested"

    @property
    def is_terminal(self) -> bool:
        """Returns True if state is terminal and cannot transition further."""
        return self in (
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.CANCELLED,
            OrderStatus.INTERRUPTED,
            OrderStatus.ABORT_REQUESTED,
        )

    def can_transition_to(self, target: Union["OrderStatus", str]) -> bool:
        """Check if target state is a valid transition from current state."""
        if isinstance(target, str):
            try:
                target = OrderStatus(target)
            except ValueError:
                return False
        if self == target:
            return True
        return target in VALID_ORDER_TRANSITIONS.get(self, set())


# Valid state machine transition graph
VALID_ORDER_TRANSITIONS: Dict[OrderStatus, Set[OrderStatus]] = {
    OrderStatus.PENDING_SUBMIT: {
        OrderStatus.PENDING_SUBMIT,
        OrderStatus.INTENT_COMMITTED,
        OrderStatus.SUBMITTED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.ABORT_REQUESTED,
    },
    OrderStatus.INTENT_COMMITTED: {
        OrderStatus.INTENT_COMMITTED,
        OrderStatus.SUBMITTED,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.ABORT_REQUESTED,
        OrderStatus.INTERRUPTED,
    },
    OrderStatus.SUBMITTED: {
        OrderStatus.SUBMITTED,
        OrderStatus.ACCEPTED,
        OrderStatus.FILLED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
        OrderStatus.INTERRUPTED,
        OrderStatus.ABORT_REQUESTED,
    },
    OrderStatus.ACCEPTED: {
        OrderStatus.ACCEPTED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
        OrderStatus.REJECTED,
        OrderStatus.INTERRUPTED,
        OrderStatus.ABORT_REQUESTED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
        OrderStatus.INTERRUPTED,
    },
    OrderStatus.FILLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.EXPIRED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.INTERRUPTED: set(),
    OrderStatus.ABORT_REQUESTED: set(),
}


class Order(Base):
    """
    Model Order untuk pelacakan lifecycle order yang strongly typed.
    Mencakup status transisi formal, slippage, dan foreign key ke analisis.
    """
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_order_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, default=lambda: f"ORD_{uuid.uuid4().hex[:12]}"
    )
    analysis_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("asset_analysis.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)  # MARKET, LIMIT, STOP
    direction: Mapped[str] = mapped_column(String(10), nullable=False)   # BUY, SELL
    requested_price: Mapped[float] = mapped_column(Float, nullable=False)
    executed_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slippage_pips: Mapped[float] = mapped_column(Float, default=0.0)
    requested_volume: Mapped[float] = mapped_column(Float, nullable=False)
    filled_volume: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[OrderStatus] = mapped_column(
        SQLAlchemyEnum(OrderStatus, native_enum=False, length=30),
        default=OrderStatus.PENDING_SUBMIT,
        index=True
    )
    replay_policy: Mapped[str] = mapped_column(String(20), default="never", nullable=False)
    intent_committed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    settlement_committed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mt5_ticket: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    analysis = relationship("AssetAnalysis", backref="orders", lazy="noload")
    events = relationship("OrderEvent", back_populates="order", cascade="all, delete-orphan", lazy="selectin")

    def __init__(self, **kwargs):
        if "id" not in kwargs or kwargs["id"] is None:
            kwargs["id"] = str(uuid.uuid4())
        if "client_order_id" not in kwargs or kwargs["client_order_id"] is None:
            kwargs["client_order_id"] = f"ORD_{uuid.uuid4().hex[:12]}"
        if "status" not in kwargs or kwargs["status"] is None:
            kwargs["status"] = OrderStatus.PENDING_SUBMIT
        if "replay_policy" not in kwargs or kwargs["replay_policy"] is None:
            kwargs["replay_policy"] = "never"
        if "slippage_pips" not in kwargs or kwargs["slippage_pips"] is None:
            kwargs["slippage_pips"] = 0.0
        if "filled_volume" not in kwargs or kwargs["filled_volume"] is None:
            kwargs["filled_volume"] = 0.0
        super().__init__(**kwargs)

    @property
    def is_terminal(self) -> bool:
        curr = self.status if isinstance(self.status, OrderStatus) else OrderStatus(self.status)
        return curr.is_terminal

    def can_transition_to(self, target: Union[OrderStatus, str]) -> bool:
        curr = self.status if isinstance(self.status, OrderStatus) else OrderStatus(self.status)
        return curr.can_transition_to(target)

    def transition_to(
        self,
        new_status: Union[OrderStatus, str],
        reason: Optional[str] = None,
        executed_price: Optional[float] = None,
        ticket: Optional[int] = None,
        slippage_pips: Optional[float] = None,
        filled_volume: Optional[float] = None,
        allow_same_state: bool = True,
    ) -> "OrderEvent":
        """
        Transition order to a new status according to state machine rules.
        Raises InvalidOrderStateTransitionError if transition is illegal.
        """
        target = new_status if isinstance(new_status, OrderStatus) else OrderStatus(new_status)
        curr = self.status if isinstance(self.status, OrderStatus) else OrderStatus(self.status)

        if curr == target and not allow_same_state:
            raise InvalidOrderStateTransitionError(
                f"Cannot transition order {self.id} from {curr.value} to same state {target.value}"
            )

        if curr != target and not curr.can_transition_to(target):
            raise InvalidOrderStateTransitionError(
                f"Illegal order state transition for order {self.id}: {curr.value} -> {target.value}"
            )

        old_status_val = curr.value
        new_status_val = target.value

        self.status = target
        self.updated_at = _utcnow()
        if target == OrderStatus.INTENT_COMMITTED and not self.intent_committed_at:
            self.intent_committed_at = _utcnow()
        elif target == OrderStatus.FILLED and not self.settlement_committed_at:
            self.settlement_committed_at = _utcnow()

        if executed_price is not None:
            self.executed_price = executed_price
        if ticket is not None:
            self.mt5_ticket = ticket
        if slippage_pips is not None:
            self.slippage_pips = slippage_pips
        if filled_volume is not None:
            self.filled_volume = filled_volume
        elif target == OrderStatus.FILLED:
            self.filled_volume = self.requested_volume

        evt = OrderEvent(
            order_id=self.id,
            from_status=old_status_val,
            to_status=new_status_val,
            reason=reason,
            timestamp=_utcnow(),
        )
        return evt


class OrderEvent(Base):
    """Audit trail histori transisi state lifecycle order."""
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.id"), nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(30), nullable=False)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationship
    order = relationship("Order", back_populates="events", lazy="noload")


class Position(Base):
    """Posisi trading yang terbuka/tertutup."""
    __tablename__ = "positions"
    __allow_unmapped__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey('orders.id'), nullable=True, index=True)
    analysis_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('asset_analysis.id'), nullable=True, index=True)
    mt5_ticket: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # buy, sell
    volume: Mapped[float] = mapped_column(Float)
    initial_volume: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    requested_volume: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_price: Mapped[float] = mapped_column(Float)
    sl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slippage_pips: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    partially_filled: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default='open')  # open, closed
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=False)
    pair_group_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    # Relationship
    order = relationship("Order", backref="positions", lazy="noload")

    # Transient runtime attributes (set dynamically by MT5 client / execution service)
    _mt5_close_reason: Optional[int] = None
    _mt5_exit_price: Optional[float] = None

    __table_args__ = (
        Index('idx_position_status', 'status'),
        Index('uq_position_analysis_open', 'analysis_id', 'mt5_ticket', unique=True,
              postgresql_where=text("status = 'open' AND analysis_id IS NOT NULL"),
              sqlite_where=text("status = 'open' AND analysis_id IS NOT NULL")),
        Index('uq_position_symbol_open', 'symbol', unique=True,
              postgresql_where=text("status = 'open' AND pair_group_id IS NULL"),
              sqlite_where=text("status = 'open' AND pair_group_id IS NULL")),
    )


class TradeOutcome(Base):
    """Link antara AssetAnalysis → Position → actual P&L outcome."""
    __tablename__ = "trade_outcomes"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('asset_analysis.id'), nullable=True, index=True)
    position_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('positions.id'), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10))
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # sl_hit, tp_hit, manual_close, system_exit
    confluence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    priced_in_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    analysis_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    holding_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    was_profitable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    was_debate_modified: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)
    decision_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    __table_args__ = (
        Index('idx_trade_outcome_symbol', 'symbol'),
        Index('idx_trade_outcome_closed', 'closed_at'),
        Index('idx_trade_outcome_profitable', 'was_profitable'),
    )


class PaperTradeRecord(Base):
    """Pelacakan paper trade persisten untuk mode dry-run."""
    __tablename__ = "paper_trade_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('asset_analysis.id'), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10))  # buy, sell
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # sl_hit, tp_hit, manual, etc.
    detection_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default='close_price')
    risk_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.75)
    entry_condition_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default='market')  # 'market', 'limit', 'trigger'
    stated_entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # AI's stated entry price
    is_pending_fill: Mapped[bool] = mapped_column(Boolean, default=False)  # True = limit order awaiting fill
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    holding_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slippage_applied: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    partially_filled: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_lot: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default='open')  # open, closed

    # Phase 3 Context tracking
    decision_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    was_debate_modified: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    was_ssvp_suppressed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)

    __table_args__ = (
        Index('idx_paper_trade_status', 'status'),
        Index('idx_paper_trade_symbol', 'symbol'),
    )


class TradePlan(Base):
    """
    Rencana eksekusi multi-phase / milestone state machine:
    - PENDING_PROBE: Probe leg (30%) menunggu eksekusi
    - PROBE_FILLED: Probe leg terisi, menunggu konfirmasi scale-in
    - CONFIRMED_SCALE_IN: Scale-in runner leg (70%) diaktifkan
    - PARTIAL_TP1_HIT: TP1 (+1.0x ATR) tercapai, SL runner dipindah ke Breakeven
    - COMPLETED: Semua leg selesai atau ditutup
    - CANCELLED: Rencana dibatalkan
    """
    __tablename__ = "trade_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('asset_analysis.id'), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # buy, sell
    status: Mapped[str] = mapped_column(String(30), default="PENDING_PROBE", index=True)  # PENDING_PROBE, PROBE_FILLED, CONFIRMED_SCALE_IN, PARTIAL_TP1_HIT, COMPLETED, CANCELLED
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_volume: Mapped[float] = mapped_column(Float, default=0.0)
    atr_at_creation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    legs: Mapped[list["TradePlanLeg"]] = relationship("TradePlanLeg", back_populates="plan", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index('idx_trade_plan_symbol_status', 'symbol', 'status'),
    )


class TradePlanLeg(Base):
    """
    Leg spesifik dalam TradePlan (Probe 30%, Runner 70%):
    - leg_type: 'probe' atau 'runner'
    - status: 'pending', 'filled', 'tp_hit', 'sl_hit', 'closed', 'cancelled'
    """
    __tablename__ = "trade_plan_legs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("trade_plans.id"), index=True)
    leg_type: Mapped[str] = mapped_column(String(20))  # probe, runner
    volume: Mapped[float] = mapped_column(Float)
    target_entry: Mapped[float] = mapped_column(Float)
    actual_entry: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    position_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('positions.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, filled, tp_hit, sl_hit, closed, cancelled
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    plan: Mapped["TradePlan"] = relationship("TradePlan", back_populates="legs")

    __table_args__ = (
        Index('idx_trade_plan_leg_plan_status', 'plan_id', 'status'),
    )


class OrderLog(Base):
    """Log setiap order yang dicoba (berhasil maupun gagal)."""
    __tablename__ = "orders_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(20))  # place, modify, close
    symbol: Mapped[str] = mapped_column(String(20))
    params_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON parameters
    requested_by: Mapped[str] = mapped_column(String(50))  # system, telegram_user, ai_agent
    approved_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # risk_gate, manual
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RiskState(Base):
    """Status risk harian — drawdown, PnL, pause status."""
    __tablename__ = "risk_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    daily_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    current_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    trading_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# =============================================================================
# 20-22: Interaksi & Memori
# =============================================================================

class TelegramConversation(Base):
    """Riwayat chat Telegram untuk konteks AI."""
    __tablename__ = "telegram_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user, assistant
    message: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index('idx_tg_user_timestamp', 'telegram_user_id', 'timestamp'),
    )


class TelegramTopicBinding(Base):
    """Pemetaan forum topic Telegram ke session ChatAgent."""
    __tablename__ = "telegram_topic_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    topic_id: Mapped[int] = mapped_column(Integer, index=True)
    topic_name: Mapped[str] = mapped_column(String(255), default="")
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint('chat_id', 'topic_id', name='uq_telegram_topic_chat_topic'),
        Index('idx_tg_topic_chat_topic', 'chat_id', 'topic_id'),
    )


class ActivityLog(Base):
    """Log semua aktivitas sistem untuk audit."""
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    category: Mapped[str] = mapped_column(String(30))  # scraping, analysis, trading, risk, telegram, system
    description: Mapped[str] = mapped_column(Text)
    related_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actor: Mapped[str] = mapped_column(String(50))  # system, ai_agent, telegram_user

    @validates("related_id")
    def validate_related_id(self, key: str, value: Any) -> Optional[int]:
        """Ensures related_id is always an integer or None, preventing asyncpg DataError."""
        if value is None:
            return None
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None


class TradingEvent(Base):
    """Append-only immutable event store for decision audit trail."""
    __tablename__ = "trading_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    seq: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    causation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    actor: Mapped[str] = mapped_column(String(50), default="system")
    ts_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class TokenUsageLog(Base):
    """Log konsumsi token API AI komprehensif untuk audit performa & biaya."""
    __tablename__ = "token_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    provider: Mapped[str] = mapped_column(String(20))  # claude, gemini, openrouter, openai, deepseek, groq, ollama
    model_name: Mapped[str] = mapped_column(String(50))
    task_name: Mapped[str] = mapped_column(String(100))
    task_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)  # 32 task roles dari settings.yaml
    subsystem: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # stage1, stage2, debate, news, risk_gate, etc.
    symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)  # BTCUSD, XAUUSD, EURUSD, dll.
    cycle_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)  # trace correlation per cycle
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    thinking_tokens: Mapped[int] = mapped_column(Integer, default=0, index=True)  # reasoning / chain-of-thought tokens
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)  # prompt cache hits
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, default=0)  # prompt cache write
    cost_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # latency ms
    status: Mapped[str] = mapped_column(String(20), default="success", index=True)  # success, fallback, error, rate_limited
    slot_name: Mapped[str] = mapped_column(String(20), default="primary")  # primary, fallback_1, etc.



class SystemConfig(Base):
    """Key-value store untuk konfigurasi runtime."""
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    @classmethod
    async def upsert(cls, session, key: str, value: Optional[str] = None, description: Optional[str] = None) -> "SystemConfig":
        """Upsert key-value record safely."""
        from sqlalchemy import select
        cfg = (await session.execute(select(cls).where(cls.key == key))).scalar_one_or_none()
        if cfg:
            if value is not None:
                cfg.value = value
            if description is not None:
                cfg.description = description
            cfg.updated_at = _utcnow()
        else:
            cfg = cls(key=key, value=value, description=description, updated_at=_utcnow())
            session.add(cfg)
        return cfg

class CyclePerformance(Base):
    """Track setiap siklus analisis untuk pemantauan performa."""
    __tablename__ = "cycle_performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    elapsed_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Scraping
    news_scraped: Mapped[int] = mapped_column(Integer, default=0)
    calendar_scraped: Mapped[int] = mapped_column(Integer, default=0)
    
    # Analysis
    stage1_success: Mapped[bool] = mapped_column(Boolean, default=False)
    stage1_tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    stage1_tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    
    assets_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    assets_skipped: Mapped[int] = mapped_column(Integer, default=0)
    decisions_buy: Mapped[int] = mapped_column(Integer, default=0)
    decisions_sell: Mapped[int] = mapped_column(Integer, default=0)
    decisions_wait: Mapped[int] = mapped_column(Integer, default=0)
    decisions_avoid: Mapped[int] = mapped_column(Integer, default=0)
    
    stage2_tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    stage2_tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    
    # Execution
    trades_proposed: Mapped[int] = mapped_column(Integer, default=0)
    trades_executed: Mapped[int] = mapped_column(Integer, default=0)
    trades_blocked: Mapped[int] = mapped_column(Integer, default=0)
    
    # Cost
    api_cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Health & Diagnostics
    health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data_completeness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tool_success_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class ConfluenceFactorOutcome(Base):
    """IMP-11: Track individual confluence factor contribution per trade outcome."""
    __tablename__ = 'confluence_factor_outcomes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_trade_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey('paper_trade_records.id'), nullable=True
    )
    analysis_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey('asset_analysis.id'), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String(20))
    factor_name: Mapped[str] = mapped_column(String(50))
    was_present: Mapped[bool] = mapped_column(Boolean, default=False)  # True if factor was active
    trade_outcome: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 'tp_hit' or 'sl_hit'
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index('idx_cfo_symbol', 'symbol'),
        Index('idx_cfo_factor', 'factor_name'),
        Index('idx_cfo_outcome', 'trade_outcome'),
    )


class PrescreenLog(Base):
    """Log hasil haiku prescreen untuk evaluasi (blind spot analysis)."""
    __tablename__ = 'prescreen_log'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    decision: Mapped[str] = mapped_column(String(10))       # 'analyze' or 'skip'
    reason: Mapped[str] = mapped_column(Text)
    price_at_check: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    price_4h_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (Index('idx_prescreen_symbol_time', 'symbol', 'checked_at'),)


class DecisionReflection(Base):
    """Decision Memory: Refleksi AI untuk setiap trade real maupun paper what-ifs."""
    __tablename__ = "decision_reflections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey('asset_analysis.id'), nullable=True
    )
    position_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Foreign key not strictly enforced here to avoid circular dep issues in legacy code
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    decision: Mapped[str] = mapped_column(String(10))  # buy, sell
    confidence: Mapped[float] = mapped_column(Float)
    confluence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- Original Thesis ---
    rationale_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # --- Actual/Hypothetical Outcome ---
    outcome_pnl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    holding_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    was_profitable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    @property
    def pnl(self) -> Optional[float]:
        """Alias for outcome_pnl_usd to maintain compatibility with analysis and memory components."""
        return self.outcome_pnl_usd

    @pnl.setter
    def pnl(self, value: Optional[float]) -> None:
        self.outcome_pnl_usd = value

    # --- AI Reflection ---
    reflection_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_trade_adjustment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    specific_lesson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lesson_tags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # JSON array
    embedding: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )  # JSON representation of float array for hybrid semantic retrieval (Phase 2)

    # --- Alpha-Based Reflection ---
    alpha_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    benchmark_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    benchmark_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    alpha_lesson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    process_was_sound: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    outcome_process_classification: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    macro_thesis_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # --- Debate Result (dari debate node, jika aktif) ---
    debate_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    debate_verdict: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # confirmed, downgraded, rejected
    pre_debate_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- Paper What-If Tracking (Q4) ---
    is_paper_whatif: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # True = trade tidak dieksekusi, outcome hipotetis
    whatif_reason: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # risk_gate_rejected, below_threshold, debate_rejected, not_auto_executed
    whatif_entry_price: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # Harga saat analisis dibuat (dari AssetAnalysis.price_at_analysis)
    whatif_price_24h: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # Harga 24h setelah analisis (dari AssetAnalysis.price_24h_after)
    whatif_hypothetical_pnl_pips: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # P&L hipotetis jika trade dieksekusi
    whatif_sl_would_hit: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )  # Apakah SL akan terkena dalam 24h?
    whatif_tp_would_hit: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )  # Apakah TP akan terkena dalam 24h?
    whatif_direction_correct: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )  # Apakah arah prediksi benar (harga bergerak sesuai direction)?

    # NEW: Context quality tracking
    context_cds_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    context_snapshot_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_context_contaminated: Mapped[bool] = mapped_column(Boolean, default=False)
    contamination_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # --- Metadata ---
    status: Mapped[str] = mapped_column(
        String(20), default='pending'
    )  # pending | pending_whatif | resolved
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    search_vector: Mapped[Optional[Any]] = mapped_column(TSVECTOR, nullable=True)

    __table_args__ = (
        Index('idx_drefl_symbol_status', 'symbol', 'status'),
        Index('idx_drefl_created', 'created_at'),
        Index('idx_drefl_paper', 'is_paper_whatif', 'status'),
        Index('idx_drefl_fts', 'search_vector', postgresql_using='gin'),
    )


class TradingStateLog(Base):
    """Snapshot log of trading agent state, cycle context, and market observations."""
    __tablename__ = "trading_state_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[str] = mapped_column(String(64), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    summary_text: Mapped[str] = mapped_column(Text)
    state_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    search_vector: Mapped[Optional[Any]] = mapped_column(TSVECTOR, nullable=True)

    __table_args__ = (
        Index('idx_tslog_cycle', 'cycle_id'),
        Index('idx_tslog_fts', 'search_vector', postgresql_using='gin'),
    )



# =============================================================================
# 23-25: Backtest Engine
# =============================================================================

class BacktestRun(Base):
    __tablename__ = "backtest_run"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)  # "full" | "replay"
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    step_hours: Mapped[int] = mapped_column(Integer, default=6)
    initial_equity: Mapped[float] = mapped_column(Float, default=10000.0)
    final_equity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_trades: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_drawdown_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    settings_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BacktestTrade(Base):
    __tablename__ = "backtest_trade"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_run.id"))
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confluence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # tp_hit, sl_hit, timeout, manual
    pnl_pips: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    executed_lots: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class DecisionMemory(Base):
    __tablename__ = "decision_memory_backtest"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rationale_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    holding_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    outcome_status: Mapped[str] = mapped_column(String(20), default="pending")
    reflection: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class NewsClassificationOutcome(Base):
    __tablename__ = 'news_classification_outcomes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    news_item_id: Mapped[int] = mapped_column(Integer, ForeignKey('news_items.id'))
    symbol_checked: Mapped[str] = mapped_column(String(20))
    classified_impact: Mapped[str] = mapped_column(String(20))
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    price_at_classification: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_2h_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    move_pct_2h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outcome_matched_classification: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index('idx_ncls_outcome_pending', 'checked_at', 'classified_at'),)


class CandidateLesson(Base):
    """Candidate empirical trading lesson pending out-of-sample shadow validation."""
    __tablename__ = 'candidate_lessons'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    lesson_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default='shadow', index=True)  # shadow, promoted, rejected
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    evaluated_trades_count: Mapped[int] = mapped_column(Integer, default=0)
    win_rate_delta: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_delta: Mapped[float] = mapped_column(Float, default=0.0)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    condition_tags: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )  # JSON representation of float array for dense semantic retrieval (Phase 2)


class TimesFMForecast(Base):
    """Proyeksi probabilistik kuantil dan metrik dispersi dari Google TimesFM 3.0."""
    __tablename__ = 'timesfm_forecasts'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    timeframe: Mapped[str] = mapped_column(String(10), default='H1')
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    horizon_steps: Mapped[int] = mapped_column(Integer, default=24)
    quantiles_json: Mapped[str] = mapped_column(Text)  # JSON serialisasi 9 kuantil (Q10..Q90)
    expected_range: Mapped[float] = mapped_column(Float)  # Q90 - Q10 pada step terakhir
    quantile_skew: Mapped[float] = mapped_column(Float)  # ((Q90 - Q50) - (Q50 - Q10)) / max(1e-6, Q90 - Q10)
    volatility_expansion_ratio: Mapped[float] = mapped_column(Float)  # expected_range / baseline_atr
    reachability_envelope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON envelope per horizon step
    model_backend: Mapped[str] = mapped_column(String(50), default="neural_timesfm_3.0")
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index('idx_timesfm_sym_time', 'symbol', 'timeframe', 'generated_at'),
    )


class ContextSpillBlob(Base):
    """PostgreSQL storage for spilled tool observation payloads."""
    __tablename__ = "context_spill_blobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blob_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cycle_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    tool_name: Mapped[str] = mapped_column(String(100), index=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    __table_args__ = (
        Index('idx_spill_cycle_tool', 'cycle_id', 'tool_name'),
    )


class PlaybookRuleAttribution(Base):
    """Playbook rule outcome attribution and closed-loop evolution tracking (SOTA Phase 4)."""
    __tablename__ = "playbook_rule_attributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_hash: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    rule_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default='active', index=True)  # active, golden, deprecated, candidate
    times_triggered: Mapped[int] = mapped_column(Integer, default=0)
    wins_count: Mapped[int] = mapped_column(Integer, default=0)
    losses_count: Mapped[int] = mapped_column(Integer, default=0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index('idx_playbook_rule_sym_stat', 'symbol', 'status'),
    )


class UserMarketIntel(Base):
    """Intelijen pasar dan arahan khusus yang diberikan oleh operator melalui Telegram."""
    __tablename__ = "user_market_intel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[str] = mapped_column(String(50), default="0", index=True)
    intel_type: Mapped[str] = mapped_column(String(30), default="tactical_directive")  # deep_research | breaking_news | scenario_watch | operator_directive | tactical_directive | macro_structural
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    full_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    affected_symbols: Mapped[str] = mapped_column(String(100), default="ALL")  # misal: "XAUUSD,EURUSD" atau "ALL"
    directive: Mapped[str] = mapped_column(String(30), default="neutral")  # caution | scenario_watch | bias_override | informational | neutral | favor_buy | favor_sell | avoid_trade
    target_cycle: Mapped[str] = mapped_column(String(30), default="next_cycle_only")  # next_cycle_only | persistent | continuous | until_event
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by_cycle_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index('ix_user_market_intel_active_exp', 'is_active', 'expires_at'),
    )

    def __init__(self, **kwargs):
        if "affected_symbols" in kwargs:
            val = kwargs["affected_symbols"]
            if isinstance(val, (list, tuple, set)):
                kwargs["affected_symbols"] = ",".join(str(s) for s in val)
        if "metadata_json" in kwargs:
            val = kwargs["metadata_json"]
            if isinstance(val, dict):
                import json
                kwargs["metadata_json"] = json.dumps(val)
        if "telegram_user_id" in kwargs:
            kwargs["telegram_user_id"] = str(kwargs["telegram_user_id"])
        elif "telegram_user_id" not in kwargs:
            kwargs["telegram_user_id"] = "0"
        if "directive" not in kwargs:
            kwargs["directive"] = "neutral"
        if "target_cycle" not in kwargs:
            kwargs["target_cycle"] = "next_cycle_only"
        if "is_active" not in kwargs:
            kwargs["is_active"] = True
        if "affected_symbols" not in kwargs:
            kwargs["affected_symbols"] = "ALL"
        super().__init__(**kwargs)

    @property
    def affected_symbols_list(self) -> list[str]:
        if not self.affected_symbols:
            return []
        if self.affected_symbols == "ALL":
            return ["ALL"]
        return [s.strip() for s in self.affected_symbols.split(",") if s.strip()]

    @property
    def metadata_dict(self) -> dict:
        if not self.metadata_json:
            return {}
        try:
            import json
            return json.loads(self.metadata_json)
        except Exception:
            return {}


# =============================================================================
# Event-Sourced Decision Ledger
# =============================================================================

class CycleEvent(Base):
    """Event-sourced analytical and execution decision ledger for quantitative audit trails."""
    __tablename__ = "cycle_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("cycle_id", "sequence", name="uq_cycle_event_seq"),
        Index("idx_cycle_event_type", "event_type"),
    )

