"""System, session lineage, telemetry, scheduler, and operational state models."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from monika.infrastructure.database.domain_models.base import Base, _utcnow


class RiskState(Base):
    """Status risk harian — drawdown, PnL, pause status."""

    __tablename__ = "risk_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    daily_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    current_drawdown: Mapped[float] = mapped_column(Float, default=0.0)

    # Numeric expanded columns (Phase 5 dual-read)
    daily_pnl_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    current_drawdown_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    trading_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unpause_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class TelegramConversation(Base):
    """Riwayat chat Telegram untuk konteks AI."""

    __tablename__ = "telegram_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user, assistant
    message: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("idx_tg_user_timestamp", "telegram_user_id", "timestamp"),)


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
        UniqueConstraint("chat_id", "topic_id", name="uq_telegram_topic_chat_topic"),
        Index("idx_tg_topic_chat_topic", "chat_id", "topic_id"),
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
    causation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    actor: Mapped[str] = mapped_column(String(50), default="system")
    ts_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class TokenUsageLog(Base):
    """Log konsumsi token API AI komprehensif untuk audit performa & biaya."""

    __tablename__ = "token_usage_log"

    __table_args__ = (Index("idx_token_usage_ts_subsys", "timestamp", "subsystem"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    provider: Mapped[str] = mapped_column(String(20))  # claude, gemini, openrouter, openai, deepseek, groq, ollama
    model_name: Mapped[str] = mapped_column(String(50))
    task_name: Mapped[str] = mapped_column(String(100))
    task_role: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )  # 32 task roles dari settings.yaml
    subsystem: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True
    )  # stage1, stage2, debate, news, risk_gate, etc.
    symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)  # BTCUSD, XAUUSD, EURUSD, dll.
    cycle_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )  # trace correlation per cycle
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    thinking_tokens: Mapped[int] = mapped_column(Integer, default=0, index=True)  # reasoning / chain-of-thought tokens
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)  # prompt cache hits
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, default=0)  # prompt cache write
    cost_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # latency ms
    status: Mapped[str] = mapped_column(
        String(20), default="success", index=True
    )  # success, fallback, error, rate_limited
    slot_name: Mapped[str] = mapped_column(String(20), default="primary")  # primary, fallback_1, etc.


class SystemConfig(Base):
    """Key-value store untuk konfigurasi runtime."""

    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    @classmethod
    async def upsert(
        cls, session, key: str, value: Optional[str] = None, description: Optional[str] = None
    ) -> "SystemConfig":
        """Upsert key-value record safely and atomically across concurrent transactions."""
        from sqlalchemy import select

        bind = session.bind
        dialect_name = bind.dialect.name if bind else "postgresql"
        if dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            now = _utcnow()
            update_dict: dict[str, Any] = {"updated_at": now}
            if value is not None:
                update_dict["value"] = value
            if description is not None:
                update_dict["description"] = description

            stmt = (
                pg_insert(cls)
                .values(key=key, value=value, description=description, updated_at=now)
                .on_conflict_do_update(index_elements=["key"], set_=update_dict)
            )
            await session.execute(stmt)
            res = await session.execute(select(cls).where(cls.key == key))
            cfg = res.scalar_one_or_none()
            if cfg is None:
                try:
                    cfg = res.scalar_one()
                except Exception:
                    pass
            if cfg is not None and value is not None:
                try:
                    cfg.value = value
                except Exception:
                    pass
            return cfg if cfg is not None else cls(key=key, value=value, description=description, updated_at=now)
        else:
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


class SystemPrompt(Base):
    """Content-addressable deduplicated system prompt storage."""

    __tablename__ = "system_prompts"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentSession(Base):
    """Institutional multi-tenant agent session tracking with parent-child lineage."""

    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    platform: Mapped[str] = mapped_column(String(32), default="telegram")
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    system_prompt_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (Index("idx_agent_sess_user_plat", "user_id", "platform"),)


class AgentSessionMessage(Base):
    """Granular turn and tool execution log supporting non-destructive compaction."""

    __tablename__ = "agent_session_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user, assistant, system, tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[int] = mapped_column(Integer, default=1, index=True)
    compacted: Mapped[int] = mapped_column(Integer, default=0, index=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    carrier_marker: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    __table_args__ = (
        Index("idx_asm_sess_active", "session_id", "active"),
        Index("idx_asm_sess_created", "session_id", "created_at"),
    )


class UserPreference(Base):
    """User-defined persistent constraints and preferences (e.g. event blacklists, risk caps)."""

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    category: Mapped[str] = mapped_column(String(32), index=True)  # event_blacklist, risk_cap, trading_hours
    key: Mapped[str] = mapped_column(String(64))  # blacklisted_events, max_risk_pct, etc.
    value_json: Mapped[str] = mapped_column(Text)  # Serialized JSON string/list
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (Index("idx_user_pref_lookup", "user_id", "category", "is_active"),)


class UserJournalEntry(Base):
    """Qualitative trader journal and psychology notes (FOMO, discipline, trade reflection)."""

    __tablename__ = "user_journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sentiment_tag: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True
    )  # fomo, revenge, discipline, patience
    content: Mapped[str] = mapped_column(Text)
    ticket_ref: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CronJob(Base):
    """Persistent job registry for UnifiedCronEngine."""

    __tablename__ = "cron_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    schedule_expression: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    target_delivery: Mapped[str] = mapped_column(String(64), nullable=False)
    target_destination: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    workdir: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    monitor_script: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_monitor_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    next_run_at: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    last_run_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1, index=True)
    no_agent: Mapped[int] = mapped_column(Integer, default=0)
    pending_slot: Mapped[int] = mapped_column(Integer, default=0)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=300.0)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class OutboxDelivery(Base):
    """Transactional outbox delivery tracking for outbound notifications."""

    __tablename__ = "outbox_deliveries"

    delivery_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    destination: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    lease_expires_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("idx_outbox_status_lease", "status", "lease_expires_at"),)


class DeliveryRecord(Base):
    """Idempotent delivery ledger for gateway and webhook platforms."""

    __tablename__ = "delivery_records"

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    delivered_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    flood_not_before: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    __table_args__ = (
        Index("idx_delivery_status", "status"),
        Index("idx_delivery_flood", "flood_not_before"),
    )


class SessionToolRecord(Base):
    """Detailed tool execution ledger accompanying session messages."""

    __tablename__ = "session_tool_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    turn_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_error: Mapped[int] = mapped_column(Integer, default=0)
    has_side_effects: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (Index("idx_str_lookup", "session_id", "turn_ordinal"),)


class RepairLedger(Base):
    """Audit trail for automatic schema, state, and database repair actions."""

    __tablename__ = "repair_ledger"

    repair_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_taken: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="RESOLVED")
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (Index("idx_repair_session", "session_id"),)


class ScheduledJob(Base):
    """Detached scheduler background job registration."""

    __tablename__ = "scheduled_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    schedule_expr: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    interval_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    handler_name: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_platform: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target_channel: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_run: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    next_run: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class JobDelivery(Base):
    """Detached scheduler execution delivery outcome."""

    __tablename__ = "job_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scheduled_jobs.job_id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    output_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[float] = mapped_column(Float, nullable=False)


__all__ = [
    "RiskState",
    "TelegramConversation",
    "TelegramTopicBinding",
    "ActivityLog",
    "TradingEvent",
    "TokenUsageLog",
    "SystemConfig",
    "SystemPrompt",
    "AgentSession",
    "AgentSessionMessage",
    "UserPreference",
    "UserJournalEntry",
    "CronJob",
    "OutboxDelivery",
    "DeliveryRecord",
    "SessionToolRecord",
    "RepairLedger",
    "ScheduledJob",
    "JobDelivery",
]
