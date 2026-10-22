"""Trading, order, position, outcome, execution plan, and backtest models."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, Union

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SQLAlchemyEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monika.domain.entities.order_status import (
    VALID_ORDER_TRANSITIONS,
    InvalidOrderStateTransitionError,
    OrderStatus,
)
from monika.infrastructure.database.domain_models.base import Base, TSVECTOR, _utcnow


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

    # Numeric expanded columns (Phase 5 dual-read)
    entry_price_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    take_profit_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    stop_loss_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    volume_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    pnl_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)


class TradeTrigger(Base):
    """Trigger kondisional untuk re-evaluasi atau eksekusi."""

    __tablename__ = "trade_triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_analysis_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("asset_analysis.id", ondelete="CASCADE"), nullable=True, index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(20))  # price_level, indicator, time, news
    condition_json: Mapped[str] = mapped_column(Text)  # JSON condition detail
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending, fired, cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    fired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship
    analysis = relationship("AssetAnalysis", back_populates="triggers", lazy="raise")

    __table_args__ = (Index("idx_trigger_status", "status"),)


class MT5Signal(Base):
    """Korelasi antara hasil analisis AI dan eksekusi MT5."""

    __tablename__ = "mt5_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_analysis_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asset_analysis.id", ondelete="CASCADE"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(10))  # buy, sell
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, sent, executed, failed
    mt5_ticket: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    analysis = relationship("AssetAnalysis", backref="mt5_signals", lazy="raise")


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
    analysis_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("asset_analysis.id", ondelete="SET NULL"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)  # MARKET, LIMIT, STOP
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY, SELL
    requested_price: Mapped[float] = mapped_column(Float, nullable=False)
    executed_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slippage_pips: Mapped[float] = mapped_column(Float, default=0.0)
    requested_volume: Mapped[float] = mapped_column(Float, nullable=False)
    filled_volume: Mapped[float] = mapped_column(Float, default=0.0)

    # Numeric expanded columns (Phase 5 dual-read)
    requested_price_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    executed_price_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    slippage_pips_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    requested_volume_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    filled_volume_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        SQLAlchemyEnum(OrderStatus, native_enum=False, length=30), default=OrderStatus.PENDING_SUBMIT, index=True
    )
    replay_policy: Mapped[str] = mapped_column(String(20), default="never", nullable=False)
    intent_committed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    settlement_committed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mt5_ticket: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    analysis = relationship("AssetAnalysis", backref="orders", lazy="raise")
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
    order_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str] = mapped_column(String(30), nullable=False)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationship
    order = relationship("Order", back_populates="events", lazy="raise")


class Position(Base):
    """Posisi trading yang terbuka/tertutup."""

    __tablename__ = "positions"
    __allow_unmapped__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    analysis_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("asset_analysis.id", ondelete="SET NULL"), nullable=True, index=True
    )
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
    status: Mapped[str] = mapped_column(String(10), default="open")  # open, closed
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=False)
    pair_group_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    trailing_override_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mae_pips: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mfe_pips: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sl_slippage_pips: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    entry_session: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    market_regime: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Numeric expanded columns (Phase 5 dual-read)
    volume_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    initial_volume_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    entry_price_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    sl_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    tp_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    pnl_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    slippage_pips_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)

    # Relationship
    order = relationship("Order", backref="positions", lazy="raise")

    @property
    def lots(self) -> float:
        return self.volume

    @lots.setter
    def lots(self, val: float):
        self.volume = float(val)

    @property
    def stop_loss(self) -> Optional[float]:
        return self.sl

    @stop_loss.setter
    def stop_loss(self, val: Optional[float]):
        self.sl = val

    @property
    def take_profit(self) -> Optional[float]:
        return self.tp

    @take_profit.setter
    def take_profit(self, val: Optional[float]):
        self.tp = val

    @property
    def side(self) -> str:
        return (self.direction or "").lower()

    @property
    def exit_price(self) -> Optional[float]:
        return self._mt5_exit_price if self._mt5_exit_price is not None else self.entry_price

    @property
    def exit_reason(self) -> str:
        return str(self._mt5_close_reason) if self._mt5_close_reason is not None else "closed"

    @exit_reason.setter
    def exit_reason(self, val: Any) -> None:
        self._mt5_close_reason = val

    @property
    def pnl_pct(self) -> float:
        notional = max(1.0, (self.entry_price or 1.0) * (self.volume or 0.01) * 100_000.0)
        return round(((self.pnl or 0.0) / notional) * 100.0, 2)

    # Transient runtime attributes (set dynamically by MT5 client / execution service)
    _mt5_close_reason: Optional[int] = None
    _mt5_exit_price: Optional[float] = None

    __table_args__ = (
        Index("idx_position_status", "status"),
        Index(
            "uq_position_analysis_open",
            "analysis_id",
            "mt5_ticket",
            unique=True,
            postgresql_where=text("status = 'open' AND analysis_id IS NOT NULL"),
            sqlite_where=text("status = 'open' AND analysis_id IS NOT NULL"),
        ),
        Index(
            "uq_position_symbol_open",
            "symbol",
            unique=True,
            postgresql_where=text("status = 'open' AND pair_group_id IS NULL"),
            sqlite_where=text("status = 'open' AND pair_group_id IS NULL"),
        ),
    )


class TradeOutcome(Base):
    """Link antara AssetAnalysis -> Position -> actual P&L outcome."""

    __tablename__ = "trade_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("asset_analysis.id", ondelete="SET NULL"), nullable=True, index=True
    )
    position_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("positions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10))
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )  # sl_hit, tp_hit, manual_close, system_exit
    confluence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    priced_in_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    analysis_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    holding_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    was_profitable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    was_debate_modified: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)
    decision_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mae_pips: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mfe_pips: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sl_slippage_pips: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    entry_session: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    market_regime: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("idx_trade_outcome_symbol", "symbol"),
        Index("idx_trade_outcome_closed", "closed_at"),
        Index("idx_trade_outcome_profitable", "was_profitable"),
    )


class PaperTradeRecord(Base):
    """Pelacakan paper trade persisten untuk mode dry-run."""

    __tablename__ = "paper_trade_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("asset_analysis.id", ondelete="SET NULL"), nullable=True, index=True
    )
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
    detection_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="close_price")
    risk_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.75)
    # Phase 0 accounting truth: immutable entry-time risk anchor.
    # `stop_loss` above keeps moving with trailing; these never change after open,
    # so realized R is always measured against the risk actually taken at entry.
    initial_stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    initial_risk_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accounting_status: Mapped[str] = mapped_column(String(30), nullable=False, default="ok", server_default="ok")
    entry_condition_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default="market"
    )  # 'market', 'limit', 'trigger'
    stated_entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # AI's stated entry price
    is_pending_fill: Mapped[bool] = mapped_column(Boolean, default=False)  # True = limit order awaiting fill
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    holding_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slippage_applied: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    partially_filled: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_lot: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open, closed

    # Phase 3 Context tracking
    decision_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    was_debate_modified: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    was_ssvp_suppressed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    mae_pips: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mfe_pips: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sl_slippage_pips: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    entry_session: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    market_regime: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Numeric expanded columns (Phase 5 dual-read)
    entry_price_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    stop_loss_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    take_profit_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    exit_price_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    risk_pct_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    pnl_pct_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    requested_lot_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)

    __table_args__ = (
        Index("idx_paper_trade_status", "status"),
        Index("idx_paper_trade_symbol", "symbol"),
    )

    @property
    def lot_size(self) -> float:
        return self.requested_lot or 0.01

    @lot_size.setter
    def lot_size(self, val: float):
        self.requested_lot = float(val)

    @property
    def volume(self) -> float:
        return self.requested_lot or 0.01

    @volume.setter
    def volume(self, val: float):
        self.requested_lot = float(val)

    @property
    def pnl_usd(self) -> float:
        return round(10_000.0 * ((self.pnl_pct or 0.0) / 100.0), 2)


class EquityDrawdownSnapshot(Base):
    """Historical equity, balance, and drawdown telemetry snapshot."""

    __tablename__ = "equity_drawdown_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    balance: Mapped[float] = mapped_column(Float)
    equity: Mapped[float] = mapped_column(Float)
    floating_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    margin_level_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    drawdown_usd: Mapped[float] = mapped_column(Float, default=0.0)
    drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    peak_equity: Mapped[float] = mapped_column(Float, default=0.0)
    open_positions_count: Mapped[int] = mapped_column(Integer, default=0)

    # Numeric expanded columns (Phase 5 dual-read)
    balance_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    equity_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    floating_pnl_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    drawdown_usd_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    drawdown_pct_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    peak_equity_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)

    __table_args__ = (Index("idx_equity_snapshot_ts", "timestamp"),)


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
    analysis_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("asset_analysis.id", ondelete="SET NULL"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # buy, sell
    status: Mapped[str] = mapped_column(
        String(30), default="PENDING_PROBE", index=True
    )  # PENDING_PROBE, PROBE_FILLED, CONFIRMED_SCALE_IN, PARTIAL_TP1_HIT, COMPLETED, CANCELLED
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

    legs: Mapped[list["TradePlanLeg"]] = relationship(
        "TradePlanLeg", back_populates="plan", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("idx_trade_plan_symbol_status", "symbol", "status"),)


class TradePlanLeg(Base):
    """
    Leg spesifik dalam TradePlan (Probe 30%, Runner 70%):
    - leg_type: 'probe' atau 'runner'
    - status: 'pending', 'filled', 'tp_hit', 'sl_hit', 'closed', 'cancelled'
    """

    __tablename__ = "trade_plan_legs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("trade_plans.id", ondelete="CASCADE"), index=True)
    leg_type: Mapped[str] = mapped_column(String(20))  # probe, runner
    volume: Mapped[float] = mapped_column(Float)
    target_entry: Mapped[float] = mapped_column(Float)
    actual_entry: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    position_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("positions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, filled, tp_hit, sl_hit, closed, cancelled
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    plan: Mapped["TradePlan"] = relationship("TradePlan", back_populates="legs")

    __table_args__ = (Index("idx_trade_plan_leg_plan_status", "plan_id", "status"),)


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
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


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
        Index("idx_tslog_cycle", "cycle_id"),
        Index("idx_tslog_fts", "search_vector", postgresql_using="gin"),
    )


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
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_run.id", ondelete="CASCADE"), index=True)
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


__all__ = [
    "Trade",
    "TradeTrigger",
    "MT5Signal",
    "Order",
    "OrderEvent",
    "Position",
    "TradeOutcome",
    "PaperTradeRecord",
    "EquityDrawdownSnapshot",
    "TradePlan",
    "TradePlanLeg",
    "OrderLog",
    "TradingStateLog",
    "BacktestRun",
    "BacktestTrade",
    "OrderStatus",
    "VALID_ORDER_TRANSITIONS",
    "InvalidOrderStateTransitionError",
]
