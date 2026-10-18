"""Analysis, fundamental briefs, and prescreen models."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monika.infrastructure.database.domain_models.base import Base, _utcnow


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
    analyses = relationship("AssetAnalysis", back_populates="brief", lazy="raise")

    @property
    def currency_bias(self) -> dict:
        if self.structured_json:
            try:
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
    brief_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("fundamental_briefs.id", ondelete="SET NULL"), nullable=True, index=True
    )
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
    confluence_factors_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON list of active factor names
    specialist_biases_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invalidation_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    invalidation_direction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # 'above' or 'below'
    execution_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Values: None (not yet processed), 'approved', 'rejected', 'executed', 'blocked'
    execution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    market_regime_at_analysis: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    risk_multiplier: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=1.0)

    # Numeric expanded columns (Phase 5 dual-read)
    confidence_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    stop_loss_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    take_profit_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    invalidation_price_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    risk_multiplier_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)

    # Debate Results
    debate_bull_thesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    debate_bear_dissent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    debate_verdict: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    debate_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Phase 3 Context tracking
    decision_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    arbitration_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_strategy_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    pair_group_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    was_debate_modified: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    was_ssvp_suppressed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)

    # Context tracking
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
    brief = relationship("FundamentalBrief", back_populates="analyses", lazy="raise")
    triggers = relationship("TradeTrigger", back_populates="analysis", lazy="raise")

    @property
    def entry_price(self) -> Optional[float]:
        """Ekstrak harga entry dari field entry_zone JSON secara aman."""
        if not self.entry_zone:
            return None
        if isinstance(self.entry_zone, dict):
            try:
                p = float(self.entry_zone.get("price", 0.0))
                return p if p > 0 else None
            except TypeError, ValueError:
                return None
        try:
            data = json.loads(self.entry_zone)
            if isinstance(data, dict):
                p = float(data.get("price", 0.0))
                return p if p > 0 else None
        except Exception:
            pass
        return None

    @entry_price.setter
    def entry_price(self, value: Optional[float]) -> None:
        """Set harga entry ke dalam field entry_zone JSON secara aman."""
        ez: dict[str, Any] = {}
        if self.entry_zone:
            if isinstance(self.entry_zone, dict):
                ez = dict(self.entry_zone)
            else:
                try:
                    loaded = json.loads(self.entry_zone)
                    if isinstance(loaded, dict):
                        ez = loaded
                except Exception:
                    ez = {}
        if value is None:
            ez.pop("price", None)
        else:
            try:
                ez["price"] = float(value)
            except ValueError, TypeError:
                pass
        self.entry_zone = json.dumps(ez)

    @property
    def invalidation_condition(self) -> Optional[str]:
        """Alias property untuk invalidation text."""
        return self.invalidation

    @invalidation_condition.setter
    def invalidation_condition(self, value: Optional[str]) -> None:
        self.invalidation = value

    __table_args__ = (Index("idx_analysis_sym_date", "symbol", "generated_at"),)


class PrescreenLog(Base):
    """Log hasil haiku prescreen untuk evaluasi (blind spot analysis)."""

    __tablename__ = "prescreen_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    decision: Mapped[str] = mapped_column(String(10))  # 'analyze' or 'skip'
    reason: Mapped[str] = mapped_column(Text)
    price_at_check: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    price_4h_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (Index("idx_prescreen_symbol_time", "symbol", "checked_at"),)


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

    __tablename__ = "confluence_factor_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_trade_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("paper_trade_records.id", ondelete="CASCADE"), nullable=True, index=True
    )
    analysis_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("asset_analysis.id", ondelete="CASCADE"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20))
    factor_name: Mapped[str] = mapped_column(String(50))
    was_present: Mapped[bool] = mapped_column(Boolean, default=False)  # True if factor was active
    trade_outcome: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 'tp_hit' or 'sl_hit'
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("idx_cfo_symbol", "symbol"),
        Index("idx_cfo_factor", "factor_name"),
        Index("idx_cfo_outcome", "trade_outcome"),
    )


class PlaybookRuleAttribution(Base):
    """Playbook rule outcome attribution and closed-loop evolution tracking (SOTA Phase 4)."""

    __tablename__ = "playbook_rule_attributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_hash: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    rule_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30), default="active", index=True
    )  # active, golden, deprecated, candidate
    times_triggered: Mapped[int] = mapped_column(Integer, default=0)
    wins_count: Mapped[int] = mapped_column(Integer, default=0)
    losses_count: Mapped[int] = mapped_column(Integer, default=0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (Index("idx_playbook_rule_sym_stat", "symbol", "status"),)


class TimesFMForecast(Base):
    """Proyeksi probabilistik kuantil dan metrik dispersi dari Google TimesFM 3.0."""

    __tablename__ = "timesfm_forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    timeframe: Mapped[str] = mapped_column(String(10), default="H1")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    horizon_steps: Mapped[int] = mapped_column(Integer, default=24)
    quantiles_json: Mapped[str] = mapped_column(Text)  # JSON serialisasi 9 kuantil (Q10..Q90)
    expected_range: Mapped[float] = mapped_column(Float)  # Q90 - Q10 pada step terakhir
    quantile_skew: Mapped[float] = mapped_column(Float)  # ((Q90 - Q50) - (Q50 - Q10)) / max(1e-6, Q90 - Q10)
    volatility_expansion_ratio: Mapped[float] = mapped_column(Float)  # expected_range / baseline_atr
    reachability_envelope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON envelope per horizon step
    model_backend: Mapped[str] = mapped_column(String(50), default="neural_timesfm_3.0")
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (Index("idx_timesfm_sym_time", "symbol", "timeframe", "generated_at"),)


class DebateTranscript(Base):
    """Multi-round Bull/Bear debate arguments, cross-examinations, and judge verdicts (PRD.md §237)."""

    __tablename__ = "debate_transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    timeframe: Mapped[Optional[str]] = mapped_column(String(10), default="H1", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    bull_perspective: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    bear_perspective: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    judge_adjudication: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    final_decision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confluence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_multiplier: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("idx_debate_transcript_sym_created", "symbol", "created_at"),)


__all__ = [
    "FundamentalBrief",
    "AssetAnalysis",
    "PrescreenLog",
    "CyclePerformance",
    "ConfluenceFactorOutcome",
    "PlaybookRuleAttribution",
    "TimesFMForecast",
    "DebateTranscript",
]
