"""News and economic calendar models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, synonym

from monika.infrastructure.database.domain_models.base import Base, _utcnow


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
        Index("idx_news_source_fetched", "source", "fetched_at"),
        Index("idx_news_url", "url"),
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
    trigger: Mapped[str] = mapped_column(String(20), default="scheduled")  # 'scheduled' | 'breaking' | 'manual'
    period_hours: Mapped[float] = mapped_column(Float, default=2.0)
    items_processed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    breaking_count: Mapped[int] = mapped_column(Integer, default=0)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    currency_sections: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON dict per currency
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_news_digest_slices_period", "period_start", "period_end"),)


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

    __table_args__ = (UniqueConstraint("currency", "event_name", "event_time", name="uq_calendar_event"),)


class NewsClassificationOutcome(Base):
    """Hasil verifikasi dan evaluasi klasifikasi dampak berita terhadap price action."""

    __tablename__ = "news_classification_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    news_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("news_items.id", ondelete="CASCADE"))
    symbol_checked: Mapped[str] = mapped_column(String(20))
    classified_impact: Mapped[str] = mapped_column(String(20))
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    price_at_classification: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_2h_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    move_pct_2h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outcome_matched_classification: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_ncls_outcome_pending", "checked_at", "classified_at"),)


__all__ = [
    "NewsItem",
    "NewsDigest",
    "NewsDigestSlice",
    "EconomicCalendar",
    "NewsClassificationOutcome",
]
