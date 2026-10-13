"""Memory, reflection, chronicle, user market intel, and cycle event models."""

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from monika.infrastructure.database.domain_models.base import Base, TSVECTOR, _utcnow


class MarketChronicle(Base):
    """
    Kronologi peristiwa makro signifikan yang persisten.
    Dikurasi secara otomatis dari BREAKING/HIGH news + FundamentalBrief.
    """

    __tablename__ = "market_chronicle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    category: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # policy_change | geopolitical | data_shock | regime_shift | institutional
    headline: Mapped[str] = mapped_column(String(300), nullable=False)
    narrative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    currencies_affected: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    severity: Mapped[str] = mapped_column(String(10), default="medium")  # low | medium | high | critical
    source_news_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_brief_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_ongoing: Mapped[bool] = mapped_column(Boolean, default=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    search_vector: Mapped[Optional[Any]] = mapped_column(TSVECTOR, nullable=True)

    __table_args__ = (Index("idx_chronicle_fts", "search_vector", postgresql_using="gin"),)


class DecisionReflection(Base):
    """Decision Memory: Refleksi AI untuk setiap trade real maupun paper what-ifs."""

    __tablename__ = "decision_reflections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("asset_analysis.id", ondelete="SET NULL"), nullable=True, index=True
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
    debate_verdict: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # confirmed, downgraded, rejected
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

    # Context quality tracking
    context_cds_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    context_snapshot_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_context_contaminated: Mapped[bool] = mapped_column(Boolean, default=False)
    contamination_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # --- Metadata ---
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | pending_whatif | resolved
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    search_vector: Mapped[Optional[Any]] = mapped_column(TSVECTOR, nullable=True)

    __table_args__ = (
        Index("idx_drefl_symbol_status", "symbol", "status"),
        Index("idx_drefl_created", "created_at"),
        Index("idx_drefl_paper", "is_paper_whatif", "status"),
        Index("idx_drefl_fts", "search_vector", postgresql_using="gin"),
    )


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


class CandidateLesson(Base):
    """Candidate empirical trading lesson pending out-of-sample shadow validation."""

    __tablename__ = "candidate_lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    lesson_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="shadow", index=True)  # shadow, promoted, rejected
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

    __table_args__ = (Index("idx_spill_cycle_tool", "cycle_id", "tool_name"),)


class UserMarketIntel(Base):
    """Intelijen pasar dan arahan khusus yang diberikan oleh operator melalui Telegram."""

    __tablename__ = "user_market_intel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[str] = mapped_column(String(50), default="0", index=True)
    intel_type: Mapped[str] = mapped_column(
        String(30), default="tactical_directive"
    )  # deep_research | breaking_news | scenario_watch | operator_directive | tactical_directive | macro_structural
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    full_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    affected_symbols: Mapped[str] = mapped_column(String(100), default="ALL")  # misal: "XAUUSD,EURUSD" atau "ALL"
    directive: Mapped[str] = mapped_column(
        String(30), default="neutral"
    )  # caution | scenario_watch | bias_override | informational | neutral | favor_buy | favor_sell | avoid_trade
    target_cycle: Mapped[str] = mapped_column(
        String(30), default="next_cycle_only"
    )  # next_cycle_only | persistent | continuous | until_event
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by_cycle_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_user_market_intel_active_exp", "is_active", "expires_at"),)

    def __init__(self, **kwargs):
        if "affected_symbols" in kwargs:
            val = kwargs["affected_symbols"]
            if isinstance(val, (list, tuple, set)):
                kwargs["affected_symbols"] = ",".join(str(s) for s in val)
        if "metadata_json" in kwargs:
            val = kwargs["metadata_json"]
            if isinstance(val, dict):
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
            return json.loads(self.metadata_json)
        except Exception:
            return {}


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


__all__ = [
    "MarketChronicle",
    "DecisionReflection",
    "DecisionMemory",
    "CandidateLesson",
    "ContextSpillBlob",
    "UserMarketIntel",
    "CycleEvent",
]
