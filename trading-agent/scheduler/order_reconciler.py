# ==============================================================================
# File: scheduler/order_reconciler.py
# ==============================================================================

"""
Active Order & Position Reconciliation Worker.
Performs periodic reconciliation between MT5 / BrokerAdapter state
and local database records (orders and positions tables).

Responsibilities:
1. Fetch real-time active orders and positions from broker/MT5.
2. Reconcile DB orders:
   - If pending order is filled in terminal, transition local DB order state to FILLED,
     spawn position record, and publish OrderStateChangedEvent to EventBus.
   - If pending order is partially filled in terminal, transition local DB order state
     to PARTIALLY_FILLED, update filled_volume, and publish OrderStateChangedEvent.
   - If pending order is cancelled/expired externally in terminal, transition local DB
     order state to CANCELLED/EXPIRED and publish OrderStateChangedEvent.
3. Reconcile DB positions:
   - If position is closed externally in terminal, update local DB record to 'closed',
     record exit price and realized PnL, register TradeOutcome, and update risk gate.
   - If position SL/TP or volume is modified externally, sync changes to DB position.
   - If untracked position exists in terminal, adopt it into DB positions.
4. Background loop orchestration:
   - Configurable interval (15-30s, default 15s).
   - Clean startup, graceful shutdown via shutdown_event, and full exception isolation.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set, Tuple

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

import utils.clock as clock
from database.db import get_session
from database.models import (
    Order,
    OrderStatus,
    OrderEvent,
    Position,
    TradeOutcome,
    AssetAnalysis,
)
from utils.protocol.event_bus import get_event_bus, OrderStateChangedEvent

logger = logging.getLogger("TradingAgent.OrderReconciler")


class OrderReconciler:
    """
    Active Order and Position Reconciliation Worker.
    Synchronizes in-flight order state machines and open positions with broker terminal state.
    """

    def __init__(
        self,
        settings: Optional[dict] = None,
        mt5_client: Optional[Any] = None,
        execution_service: Optional[Any] = None,
        broker_adapter: Optional[Any] = None,
        interval_seconds: float = 10.0,
        recovery_event: Optional[asyncio.Event] = None,
        shutdown_event: Optional[asyncio.Event] = None,
    ):
        self.settings = settings or {}
        self.mt5_client = mt5_client
        self.execution_service = execution_service
        self.broker_adapter = broker_adapter
        self._recovery_event = recovery_event
        if self.broker_adapter is None and execution_service is not None:
            self.broker_adapter = getattr(execution_service, "broker_adapter", None)
        if self.mt5_client is None and execution_service is not None:
            self.mt5_client = getattr(execution_service, "mt5", None)

        reconcile_cfg = self.settings.get("execution", {}).get("reconciliation", {})
        cfg_interval = reconcile_cfg.get(
            "interval_seconds",
            self.settings.get("execution", {}).get("reconciliation_interval_seconds", interval_seconds),
        )
        self.interval_seconds = max(5.0, float(cfg_interval))
        self.submitted_grace_seconds = float(
            reconcile_cfg.get("submitted_grace_seconds", 45.0)
        )
        self._running = True
        self._stop_event = shutdown_event or asyncio.Event()
        self._running_task: Optional[asyncio.Task] = None
        self.dry_run = bool(self.settings.get("trading", {}).get("dry_run", False))

    @property
    def is_running(self) -> bool:
        """Indicates if reconciler worker is actively running."""
        return self._running and not self._stop_event.is_set()

    async def get_terminal_orders(self) -> Optional[List[dict]]:
        """Fetch active pending orders from broker adapter or MT5 client. Returns None if connection fails."""
        try:
            if self.broker_adapter and hasattr(self.broker_adapter, "get_orders"):
                return await self.broker_adapter.get_orders()
            if self.mt5_client and hasattr(self.mt5_client, "get_orders"):
                return await self.mt5_client.get_orders()
        except Exception as e:
            logger.error(f"[OrderReconciler] Failed to fetch terminal orders: {e}")
            return None
        return []

    async def get_terminal_positions(self) -> Optional[List[dict]]:
        """Fetch open positions from broker adapter or MT5 client. Returns None if connection fails."""
        try:
            if self.broker_adapter and hasattr(self.broker_adapter, "get_positions"):
                return await self.broker_adapter.get_positions()
            if self.mt5_client and hasattr(self.mt5_client, "get_open_positions"):
                return await self.mt5_client.get_open_positions()
        except Exception as e:
            logger.error(f"[OrderReconciler] Failed to fetch terminal positions: {e}")
            return None
        return []

    async def _publish_order_event(
        self,
        order: Order,
        old_state: str,
        new_state: str,
        details: Optional[dict] = None,
    ) -> None:
        """Publish strongly typed OrderStateChangedEvent to EventBus."""
        try:
            bus = get_event_bus()
            ev_details = details or {}
            await bus.publish(
                OrderStateChangedEvent(
                    order_id=order.id,
                    symbol=order.symbol,
                    old_state=old_state,
                    new_state=new_state,
                    details=ev_details,
                )
            )
        except Exception as eb_err:
            logger.debug(f"[OrderReconciler] EventBus publish error: {eb_err}")

    async def reconcile_orders(
        self,
        session: AsyncSession,
        terminal_orders: List[dict],
        terminal_positions: List[dict],
    ) -> dict:
        """
        Reconcile in-flight orders in local DB against terminal state.
        Transitions pending orders to ACCEPTED, PARTIALLY_FILLED, FILLED, or CANCELLED.
        """
        stats = {
            "orders_checked": 0,
            "orders_accepted": 0,
            "orders_filled": 0,
            "orders_partially_filled": 0,
            "orders_cancelled": 0,
        }

        # Index terminal orders by ticket and client_order_id
        term_orders_by_ticket: Dict[int, dict] = {}
        term_orders_by_cid: Dict[str, dict] = {}
        for o in terminal_orders:
            t = o.get("ticket")
            if t is not None:
                try:
                    term_orders_by_ticket[int(t)] = o
                except (ValueError, TypeError):
                    pass
            cid = o.get("client_order_id")
            if cid:
                term_orders_by_cid[str(cid)] = o

        # Index terminal positions by ticket, identifier, and comment
        term_positions_by_ticket: Dict[int, dict] = {}
        term_positions_by_identifier: Dict[int, dict] = {}
        term_positions_by_comment: Dict[str, dict] = {}
        for p in terminal_positions:
            t = p.get("ticket")
            if t is not None:
                try:
                    term_positions_by_ticket[int(t)] = p
                except (ValueError, TypeError):
                    pass
            ident = p.get("identifier")
            if ident is not None:
                try:
                    term_positions_by_identifier[int(ident)] = p
                except (ValueError, TypeError):
                    pass
            comm = p.get("comment")
            if comm:
                term_positions_by_comment[str(comm)] = p

        # Query in-flight orders from DB
        stmt = (
            select(Order)
            .where(
                Order.status.in_([
                    OrderStatus.SUBMITTED,
                    OrderStatus.ACCEPTED,
                    OrderStatus.PARTIALLY_FILLED,
                ])
            )
            .order_by(Order.created_at.asc())
        )
        db_orders = (await session.execute(stmt)).scalars().all()

        for order in db_orders:
            stats["orders_checked"] += 1
            t_ticket = int(order.mt5_ticket) if order.mt5_ticket is not None else None
            t_cid = str(order.client_order_id) if order.client_order_id else None

            matched_term_order = (
                term_orders_by_ticket.get(t_ticket)
                if t_ticket is not None
                else (term_orders_by_cid.get(t_cid) if t_cid is not None else None)
            )

            matched_term_pos = None
            if t_ticket is not None:
                matched_term_pos = term_positions_by_ticket.get(t_ticket) or term_positions_by_identifier.get(t_ticket)
            if matched_term_pos is None and t_cid:
                for c_str, p in term_positions_by_comment.items():
                    if t_cid in c_str:
                        matched_term_pos = p
                        break

            # -------------------------------------------------------------
            # Case 1: Order is currently still active in terminal orders
            # -------------------------------------------------------------
            if matched_term_order is not None:
                # Transition SUBMITTED -> ACCEPTED
                if order.status == OrderStatus.SUBMITTED:
                    old_st = order.status.value
                    term_ticket = matched_term_order.get("ticket")
                    term_price = matched_term_order.get("price_open")
                    evt = order.transition_to(
                        OrderStatus.ACCEPTED,
                        reason="Broker placement confirmed active in terminal",
                        ticket=term_ticket,
                        executed_price=term_price,
                        allow_same_state=True,
                    )
                    session.add(evt)
                    stats["orders_accepted"] += 1
                    await self._publish_order_event(
                        order, old_st, OrderStatus.ACCEPTED.value,
                        {"ticket": order.mt5_ticket, "price": term_price, "source": "reconciler"}
                    )

                # Check incremental / partial fill
                vol_init = float(matched_term_order.get("volume_initial", order.requested_volume))
                vol_curr = float(matched_term_order.get("volume_current", matched_term_order.get("volume", vol_init)))
                if vol_init > vol_curr:
                    filled_vol = round(vol_init - vol_curr, 4)
                    if 0 < filled_vol < vol_init and (
                        order.status != OrderStatus.PARTIALLY_FILLED or order.filled_volume != filled_vol
                    ):
                        old_st = order.status.value
                        evt = order.transition_to(
                            OrderStatus.PARTIALLY_FILLED,
                            reason=f"Partial fill detected in terminal: {filled_vol}/{vol_init} lots",
                            ticket=matched_term_order.get("ticket"),
                            executed_price=matched_term_order.get("price_open"),
                            filled_volume=filled_vol,
                            allow_same_state=True,
                        )
                        session.add(evt)
                        stats["orders_partially_filled"] += 1
                        await self._publish_order_event(
                            order, old_st, OrderStatus.PARTIALLY_FILLED.value,
                            {"ticket": order.mt5_ticket, "filled_volume": filled_vol, "source": "reconciler"}
                        )
                continue

            # -------------------------------------------------------------
            # Case 2: Order is no longer in pending orders, BUT exists in terminal positions (FILLED)
            # -------------------------------------------------------------
            if matched_term_pos is not None:
                old_st = order.status.value
                fill_price = float(
                    matched_term_pos.get("price_open")
                    or matched_term_pos.get("open_price")
                    or order.requested_price
                )
                fill_vol = float(matched_term_pos.get("volume") or order.requested_volume)
                pos_ticket = matched_term_pos.get("ticket") or t_ticket

                evt = order.transition_to(
                    OrderStatus.FILLED,
                    reason=f"Pending order filled into terminal position #{pos_ticket}",
                    executed_price=fill_price,
                    ticket=pos_ticket,
                    filled_volume=fill_vol,
                    allow_same_state=True,
                )
                session.add(evt)
                stats["orders_filled"] += 1

                # Spawn matching Position record if not already in DB
                pos_conds = [Position.order_id == order.id]
                if pos_ticket is not None:
                    pos_conds.append(Position.mt5_ticket == pos_ticket)
                if t_ticket is not None and t_ticket != pos_ticket:
                    pos_conds.append(Position.mt5_ticket == t_ticket)

                existing_pos = (
                    await session.execute(
                        select(Position).where(or_(*pos_conds))
                    )
                ).scalar_one_or_none()

                created_pos = None
                if existing_pos is None:
                    created_pos = Position(
                        order_id=order.id,
                        analysis_id=order.analysis_id,
                        mt5_ticket=pos_ticket,
                        symbol=order.symbol,
                        direction=order.direction.lower(),
                        volume=fill_vol,
                        entry_price=fill_price,
                        sl=matched_term_pos.get("sl"),
                        tp=matched_term_pos.get("tp"),
                        opened_at=matched_term_pos.get("time") or clock.now(),
                        status="open",
                        is_paper=self.dry_run,
                    )
                    session.add(created_pos)
                    await session.flush()
                    logger.info(
                        f"[OrderReconciler] Spawned Position #{pos_ticket} for filled Order {order.id} "
                        f"({order.symbol} {order.direction} {fill_vol} lots @ {fill_price})"
                    )

                target_pos_id = created_pos.id if created_pos else (existing_pos.id if existing_pos else None)

                # Sync TradePlan legs if associated with order / analysis
                if order.analysis_id:
                    try:
                        from database.models import TradePlan, TradePlanLeg
                        from sqlalchemy.orm import selectinload
                        plan_rec = (
                            await session.execute(
                                select(TradePlan)
                                .options(selectinload(TradePlan.legs))
                                .where(TradePlan.analysis_id == order.analysis_id)
                                .order_by(TradePlan.created_at.desc())
                                .limit(1)
                            )
                        ).scalar_one_or_none()
                        if plan_rec:
                            if plan_rec.status == "PENDING_PROBE":
                                plan_rec.status = "CONFIRMED_SCALE_IN"
                            for leg in plan_rec.legs:
                                if leg.status == "pending":
                                    leg.status = "filled"
                                    leg.position_id = target_pos_id
                                    leg.actual_entry = fill_price
                                    leg.filled_at = clock.now()
                    except Exception as tp_err:
                        logger.debug(f"[OrderReconciler] TradePlan sync note: {tp_err}")

                await self._publish_order_event(
                    order, old_st, OrderStatus.FILLED.value,
                    {"ticket": pos_ticket, "price": fill_price, "volume": fill_vol, "source": "reconciler"}
                )
                continue

            # -------------------------------------------------------------
            # Case 3: Order not in terminal orders and not in open positions
            # -------------------------------------------------------------
            # Check in-flight grace period for SUBMITTED orders
            now_dt = clock.now()
            order_created = order.created_at or order.updated_at or now_dt
            if order_created.tzinfo is None:
                order_created = order_created.replace(tzinfo=timezone.utc)
            if now_dt.tzinfo is None:
                now_dt = now_dt.replace(tzinfo=timezone.utc)
            order_age_sec = (now_dt - order_created).total_seconds()

            if order.status == OrderStatus.SUBMITTED and order_age_sec < self.submitted_grace_seconds:
                logger.debug(
                    f"[OrderReconciler] Order {order.id} ({order.symbol}) is SUBMITTED and within grace period "
                    f"({order_age_sec:.1f}s < {self.submitted_grace_seconds}s). Preserving."
                )
                continue

            # Check deals or order history
            deals = []
            if self.mt5_client and hasattr(self.mt5_client, "get_deal_history") and t_ticket:
                try:
                    deals = await self.mt5_client.get_deal_history(t_ticket)
                except Exception:
                    deals = []
            elif self.mt5_client and hasattr(self.mt5_client, "_run") and t_ticket:
                try:
                    from execution.mt5_client import _get_deal_history
                    deals = await self.mt5_client._run(_get_deal_history, t_ticket)
                except Exception:
                    deals = []

            if deals:
                old_st = order.status.value
                deal_price = getattr(deals[0], "price", order.requested_price)
                evt = order.transition_to(
                    OrderStatus.FILLED,
                    reason=f"Order confirmed filled via deal history #{t_ticket}",
                    executed_price=deal_price,
                    ticket=t_ticket,
                    allow_same_state=True,
                )
                session.add(evt)
                stats["orders_filled"] += 1

                # Spawn closed position and trade outcome so accounting is not lost!
                deal_pnl = sum(getattr(d, "profit", 0.0) for d in deals)
                exit_deal = deals[-1]
                pos_conds = [Position.order_id == order.id]
                if t_ticket is not None:
                    pos_conds.append(Position.mt5_ticket == t_ticket)
                existing_pos = (
                    await session.execute(
                        select(Position).where(or_(*pos_conds))
                    )
                ).scalar_one_or_none()

                if existing_pos is None:
                    closed_pos = Position(
                        order_id=order.id,
                        analysis_id=order.analysis_id,
                        mt5_ticket=t_ticket,
                        symbol=order.symbol,
                        direction=order.direction.lower(),
                        volume=float(getattr(deals[0], "volume", order.requested_volume)),
                        entry_price=deal_price,
                        sl=getattr(deals[0], "sl", None),
                        tp=getattr(deals[0], "tp", None),
                        opened_at=order.created_at or clock.now(),
                        closed_at=clock.now(),
                        status="closed",
                        pnl=deal_pnl,
                        is_paper=self.dry_run,
                    )
                    session.add(closed_pos)
                    await session.flush()

                    # Create TradeOutcome
                    try:
                        outcome = TradeOutcome(
                            analysis_id=order.analysis_id,
                            position_id=closed_pos.id,
                            symbol=order.symbol,
                            direction=order.direction.lower(),
                            entry_price=deal_price,
                            exit_price=getattr(exit_deal, "price", deal_price),
                            stop_loss=closed_pos.sl,
                            take_profit=closed_pos.tp,
                            pnl_usd=deal_pnl,
                            opened_at=closed_pos.opened_at,
                            closed_at=closed_pos.closed_at,
                            holding_hours=0.01,
                            was_profitable=deal_pnl > 0,
                            exit_reason="external_terminal_deal_close",
                        )
                        session.add(outcome)
                    except Exception as out_err:
                        logger.debug(f"[OrderReconciler] TradeOutcome creation note: {out_err}")

                    # Update RiskGate
                    if self.execution_service:
                        try:
                            gate = getattr(self.execution_service, "gate", None)
                            if gate and hasattr(gate, "update_risk_state"):
                                await gate.update_risk_state(session, pnl_delta=deal_pnl)
                        except Exception as gate_err:
                            logger.debug(f"[OrderReconciler] Risk state update note: {gate_err}")

                await self._publish_order_event(
                    order, old_st, OrderStatus.FILLED.value,
                    {"ticket": t_ticket, "price": deal_price, "source": "reconciler_deals"}
                )
            else:
                # Cancelled or expired externally in terminal
                old_st = order.status.value
                terminal_reason = "Order removed or cancelled externally in terminal"
                new_state = OrderStatus.CANCELLED

                # Check if MT5 order history indicates expired
                if self.mt5_client and hasattr(self.mt5_client, "get_order_history") and t_ticket:
                    try:
                        hist_orders = await self.mt5_client.get_order_history(t_ticket)
                        if hist_orders:
                            hist_state = getattr(hist_orders[0], "state", None)
                            if hist_state == 5 or str(hist_state).lower() == "expired":
                                new_state = OrderStatus.EXPIRED
                                terminal_reason = "Order expired externally in terminal"
                    except Exception:
                        pass

                evt = order.transition_to(
                    new_state,
                    reason=terminal_reason,
                    allow_same_state=True,
                )
                session.add(evt)
                stats["orders_cancelled"] += 1
                logger.info(
                    f"[OrderReconciler] Order {order.id} ({order.symbol} #{t_ticket}) "
                    f"transitioned to {new_state.value} (not found in terminal)"
                )
                await self._publish_order_event(
                    order, old_st, new_state.value,
                    {"ticket": t_ticket, "reason": terminal_reason, "source": "reconciler"}
                )

        return stats

    async def reconcile_positions(
        self,
        session: AsyncSession,
        terminal_positions: List[dict],
    ) -> dict:
        """
        Reconcile open positions in DB against active terminal positions.
        Detects position closures, external SL/TP/volume adjustments, and adopts untracked positions.
        """
        stats = {
            "positions_checked": 0,
            "positions_closed": 0,
            "positions_modified": 0,
            "untracked_adopted": 0,
        }

        term_positions_by_ticket: Dict[int, dict] = {}
        for p in terminal_positions:
            t = p.get("ticket")
            if t is not None:
                try:
                    term_positions_by_ticket[int(t)] = p
                except (ValueError, TypeError):
                    pass

        # Query all DB positions with status == 'open'
        stmt = select(Position).where(Position.status == "open")
        open_db_positions = (await session.execute(stmt)).scalars().all()

        for db_pos in open_db_positions:
            # Skip paper trade records if we are checking real MT5 positions
            if getattr(db_pos, "is_paper", False):
                continue

            stats["positions_checked"] += 1
            ticket = db_pos.mt5_ticket
            if ticket is None:
                continue

            # -------------------------------------------------------------
            # Position Closed Externally in Terminal
            # -------------------------------------------------------------
            if ticket not in term_positions_by_ticket:
                db_pos.status = "closed"
                db_pos.closed_at = clock.now()
                stats["positions_closed"] += 1

                deals = []
                if self.mt5_client and hasattr(self.mt5_client, "_run"):
                    try:
                        from execution.mt5_client import _get_deal_history
                        deals = await self.mt5_client._run(_get_deal_history, ticket)
                    except Exception:
                        deals = []

                if deals:
                    db_pos.pnl = sum(getattr(d, "profit", 0.0) for d in deals)
                    close_deal = deals[-1]
                    setattr(db_pos, "_mt5_close_reason", getattr(close_deal, "reason", None))
                    setattr(db_pos, "_mt5_exit_price", getattr(close_deal, "price", None))

                # Update RiskGate daily drawdown & PnL
                equity = None
                try:
                    if self.broker_adapter and hasattr(self.broker_adapter, "get_account_info"):
                        acct = await self.broker_adapter.get_account_info()
                        equity = acct.get("equity") if acct else None
                    elif self.mt5_client and hasattr(self.mt5_client, "get_account_info"):
                        acct = await self.mt5_client.get_account_info()
                        equity = acct.get("equity") if acct else None
                except Exception:
                    pass

                if db_pos.pnl is not None and self.execution_service:
                    try:
                        gate = getattr(self.execution_service, "gate", None)
                        if gate and hasattr(gate, "update_risk_state"):
                            await gate.update_risk_state(session, pnl_delta=db_pos.pnl, equity=equity)
                    except Exception as gate_err:
                        logger.debug(f"[OrderReconciler] Risk state update error: {gate_err}")

                # Create TradeOutcome for analytics & memory outcome linker
                try:
                    existing_outcome = (
                        await session.execute(
                            select(TradeOutcome).where(TradeOutcome.position_id == db_pos.id)
                        )
                    ).scalar_one_or_none()

                    if existing_outcome is None:
                        related_analysis = None
                        if db_pos.analysis_id:
                            related_analysis = (
                                await session.execute(
                                    select(AssetAnalysis).where(AssetAnalysis.id == db_pos.analysis_id)
                                )
                            ).scalar_one_or_none()

                        exit_price = getattr(db_pos, "_mt5_exit_price", None) or db_pos.entry_price
                        closed_at = db_pos.closed_at
                        opened_at = db_pos.opened_at
                        holding_duration = None
                        if closed_at is not None and opened_at is not None:
                            holding_duration = max(0.0, (closed_at - opened_at).total_seconds() / 3600.0)

                        outcome = TradeOutcome(
                            analysis_id=db_pos.analysis_id,
                            position_id=db_pos.id,
                            symbol=db_pos.symbol,
                            direction=db_pos.direction,
                            entry_price=db_pos.entry_price,
                            exit_price=exit_price,
                            stop_loss=db_pos.sl,
                            take_profit=db_pos.tp,
                            pnl_usd=db_pos.pnl or 0.0,
                            confluence_score=getattr(related_analysis, "confluence_score", None),
                            priced_in_score=getattr(related_analysis, "priced_in_score", None),
                            analysis_confidence=getattr(related_analysis, "confidence", None),
                            opened_at=db_pos.opened_at,
                            closed_at=db_pos.closed_at,
                            holding_hours=holding_duration,
                            was_profitable=(db_pos.pnl or 0.0) > 0,
                            exit_reason="external_terminal_close",
                            was_debate_modified=bool(getattr(related_analysis, "was_debate_modified", False)),
                            decision_source=getattr(related_analysis, "decision_source", None),
                        )
                        session.add(outcome)
                except Exception as out_err:
                    logger.debug(f"[OrderReconciler] TradeOutcome creation error: {out_err}")

                logger.info(f"[OrderReconciler] Position #{ticket} ({db_pos.symbol}) closed externally. PnL: {db_pos.pnl}")
                continue

            # -------------------------------------------------------------
            # Position Still Open: Check for External Modifications (SL, TP, Vol)
            # -------------------------------------------------------------
            term_pos = term_positions_by_ticket[ticket]
            modified = False

            new_sl = term_pos.get("sl")
            if new_sl is not None and (db_pos.sl is None or abs(float(db_pos.sl) - float(new_sl)) > 1e-5):
                db_pos.sl = float(new_sl)
                modified = True

            new_tp = term_pos.get("tp")
            if new_tp is not None and (db_pos.tp is None or abs(float(db_pos.tp) - float(new_tp)) > 1e-5):
                db_pos.tp = float(new_tp)
                modified = True

            new_vol = term_pos.get("volume")
            if new_vol is not None and (db_pos.volume is None or abs(float(db_pos.volume) - float(new_vol)) > 1e-5):
                db_pos.volume = float(new_vol)
                modified = True

            if modified:
                stats["positions_modified"] += 1
                logger.info(
                    f"[OrderReconciler] Position #{ticket} ({db_pos.symbol}) modified externally: "
                    f"SL={db_pos.sl}, TP={db_pos.tp}, Vol={db_pos.volume}"
                )

        # -----------------------------------------------------------------
        # Untracked Terminal Positions Adoption
        # -----------------------------------------------------------------
        known_tickets = {
            p.mt5_ticket for p in open_db_positions if p.mt5_ticket is not None
        }
        for t_ticket, t_pos in term_positions_by_ticket.items():
            if t_ticket not in known_tickets:
                existing_any = (
                    await session.execute(
                        select(Position).where(Position.mt5_ticket == t_ticket)
                    )
                ).scalar_one_or_none()

                if existing_any is None:
                    adopted_pos = Position(
                        mt5_ticket=t_ticket,
                        symbol=t_pos.get("symbol", ""),
                        direction=t_pos.get("direction", "buy"),
                        volume=float(t_pos.get("volume", 0.1)),
                        entry_price=float(t_pos.get("price_open", t_pos.get("open_price", 0.0))),
                        sl=t_pos.get("sl"),
                        tp=t_pos.get("tp"),
                        opened_at=t_pos.get("time") or clock.now(),
                        status="open",
                        is_paper=self.dry_run,
                    )
                    session.add(adopted_pos)
                    stats["untracked_adopted"] += 1
                    logger.warning(
                        f"[OrderReconciler] Adopted untracked terminal position #{t_ticket} "
                        f"({adopted_pos.symbol} {adopted_pos.direction} {adopted_pos.volume} lots)"
                    )

        return stats

    async def reconcile_once(self, session: Optional[AsyncSession] = None) -> dict:
        """
        Execute one full reconciliation cycle across orders and positions.
        """
        terminal_orders = await self.get_terminal_orders()
        terminal_positions = await self.get_terminal_positions()

        if terminal_orders is None or terminal_positions is None:
            logger.warning(
                f"[OrderReconciler] Terminal state unavailable (orders={terminal_orders is not None}, "
                f"positions={terminal_positions is not None}). Skipping reconciliation pass."
            )
            return {"skipped": True, "reason": "terminal_unavailable"}

        if session is not None:
            order_stats = await self.reconcile_orders(session, terminal_orders, terminal_positions)
            pos_stats = await self.reconcile_positions(session, terminal_positions)
            await session.flush()
            merged = {**order_stats, **pos_stats}
            return merged

        async with get_session() as new_session:
            order_stats = await self.reconcile_orders(new_session, terminal_orders, terminal_positions)
            pos_stats = await self.reconcile_positions(new_session, terminal_positions)
            await new_session.commit()
            merged = {**order_stats, **pos_stats}
            return merged

    async def start(self) -> None:
        """Run the continuous reconciliation background loop."""
        logger.info(f"[OrderReconciler] Background loop started (interval: {self.interval_seconds}s)")

        if self._recovery_event:
            logger.info("[OrderReconciler] Waiting for recovery event before first reconciliation pass...")
            try:
                await asyncio.wait_for(self._recovery_event.wait(), timeout=180.0)
                logger.info("[OrderReconciler] Recovery complete, starting reconciliation loop.")
            except asyncio.TimeoutError:
                logger.warning("[OrderReconciler] Recovery wait timed out (180s). Proceeding anyway.")

        while not self._stop_event.is_set():
            try:
                stats = await self.reconcile_once()
                if (
                    stats.get("orders_accepted", 0) > 0
                    or stats.get("orders_filled", 0) > 0
                    or stats.get("orders_cancelled", 0) > 0
                    or stats.get("positions_closed", 0) > 0
                    or stats.get("positions_modified", 0) > 0
                    or stats.get("untracked_adopted", 0) > 0
                ):
                    logger.info(f"[OrderReconciler] Reconciliation pass completed: {stats}")
            except Exception as e:
                logger.error(f"[OrderReconciler] Error in reconciliation cycle: {e}", exc_info=True)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        """Signal the reconciliation background loop to terminate gracefully."""
        self._running = False
        self._stop_event.set()
        logger.info("[OrderReconciler] Background loop stop requested")


__all__ = ["OrderReconciler"]
