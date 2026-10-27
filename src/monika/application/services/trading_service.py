# ==============================================================================
# Package: monika.application.services
# File: trading_service.py
# ==============================================================================

"""
Trading Application Service.
Consolidates trade proposals, manual order execution, confirmation verification,
and emergency halt procedures across all presentation layers (CLI, Telegram, Dashboard).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import time

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Union

from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.entities.position import PositionEntity
from monika.domain.ports import UnitOfWorkPort
from monika.domain.risk.position_sizing import get_instrument_spec
from monika.domain.risk.trade_proposal import TradeProposal
from monika.infrastructure.database.repositories.activity_log_repository import ActivityLogRepository
from monika.infrastructure.database.repositories.position_repository import PositionRepository
from monika.infrastructure.database.repositories.system_config_repository import SystemConfigRepository
from monika.infrastructure.database.repositories.trade_proposal_repository import TradeProposalRepository

logger = logging.getLogger("Monika.Application.TradingService")


@dataclass
class OrderPreviewResult:
    """Pre-trade verification calculation with time-limited confirmation token."""

    symbol: str
    action: str
    volume: float
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    estimated_risk_usd: float
    estimated_reward_usd: float
    risk_reward_ratio: float
    margin_required: float
    preview_token: str
    expires_at: float
    is_paper: bool


@dataclass
class TradeExecutionResult:
    """Execution outcome from broker adapter or paper emulator."""

    success: bool
    ticket: Optional[int] = None
    order_id: Optional[str] = None
    symbol: str = ""
    action: str = ""
    volume: float = 0.0
    price: float = 0.0
    is_paper: bool = True
    error_message: Optional[str] = None
    execution_time: Optional[datetime] = None


class TradingService:
    """Canonical Application Service orchestrating order placement and safety."""

    _order_lock: Optional[asyncio.Lock] = None

    @classmethod
    def _get_order_lock(cls) -> asyncio.Lock:
        if cls._order_lock is None:
            cls._order_lock = asyncio.Lock()
        return cls._order_lock

    @classmethod
    def _get_signing_key(cls, is_live: bool = False) -> bytes:
        secret = os.environ.get("MONIKA_ORDER_SIGNING_SECRET")
        if not secret:
            if is_live:
                raise ValueError("MONIKA_ORDER_SIGNING_SECRET must be configured for live order execution.")
            secret = "monika-internal-fortress-secret-key"
        return secret.encode("utf-8")

    @classmethod
    def generate_preview_token(
        cls,
        symbol: str,
        action: str,
        volume: float,
        expires_at: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> str:
        """Generate HMAC-SHA256 signature for pre-trade verification confirmation."""
        components = [symbol, action, str(volume), str(expires_at)]
        if price is not None:
            components.append(str(price))
        if stop_loss is not None:
            components.append(str(stop_loss))
        if take_profit is not None:
            components.append(str(take_profit))
        payload = ":".join(components).encode()
        key = cls._get_signing_key(is_live=False)
        return hmac.new(key, payload, hashlib.sha256).hexdigest()

    @classmethod
    def verify_preview_token(
        cls,
        token: str,
        symbol: str,
        action: str,
        volume: float,
        expires_at: float,
        is_live: bool = False,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """Verify validity and non-expiration of pre-trade confirmation token."""
        if time.time() > expires_at:
            return False
        try:
            key = cls._get_signing_key(is_live=is_live)
        except ValueError:
            return False

        # Check extended payload first
        components = [symbol, action, str(volume), str(expires_at)]
        if price is not None:
            components.append(str(price))
        if stop_loss is not None:
            components.append(str(stop_loss))
        if take_profit is not None:
            components.append(str(take_profit))
        expected_extended = hmac.new(key, ":".join(components).encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(token, expected_extended):
            return True

        # Fallback to legacy 4-tuple payload for backward compatibility
        expected_base = hmac.new(key, f"{symbol}:{action}:{volume}:{expires_at}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(token, expected_base)

    @classmethod
    async def preview_manual_order(
        cls,
        session: AsyncSession,
        symbol: str,
        action: str,
        volume: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        is_paper: bool = True,
    ) -> OrderPreviewResult:
        """
        Calculate margin requirements, risk/reward ratios, and generate a signed
        preview confirmation token with a 60-second TTL.
        """
        sym = symbol.upper()
        act = action.upper()
        expires_at = time.time() + 60.0  # 60s TTL

        spec = get_instrument_spec(sym)
        pip_size = spec.pip_size if spec.pip_size > 0 else 0.0001
        pip_val = spec.pip_value_usd if spec.pip_value_usd > 0 else 10.0
        contract_size = spec.contract_size if spec.contract_size > 0 else 100_000.0

        # Calculate estimated risk / reward
        est_risk = 0.0
        est_reward = 0.0
        if stop_loss and entry_price:
            diff = abs(entry_price - stop_loss)
            pips = diff / pip_size
            est_risk = pips * pip_val * volume
        if take_profit and entry_price:
            diff = abs(take_profit - entry_price)
            pips = diff / pip_size
            est_reward = pips * pip_val * volume

        rr_ratio = (est_reward / est_risk) if est_risk > 0 else 0.0
        margin_est = (entry_price * volume * contract_size) / 100.0  # Standard 1:100 leverage estimate

        token = cls.generate_preview_token(sym, act, volume, expires_at)

        return OrderPreviewResult(
            symbol=sym,
            action=act,
            volume=volume,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            estimated_risk_usd=round(est_risk, 2),
            estimated_reward_usd=round(est_reward, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            margin_required=round(margin_est, 2),
            preview_token=token,
            expires_at=expires_at,
            is_paper=is_paper,
        )

    @classmethod
    async def submit_order(
        cls,
        session: AsyncSession,
        symbol: str,
        action: str,
        volume: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        is_paper: bool = True,
        preview_token: Optional[str] = None,
        token_expires_at: Optional[float] = None,
        actor: str = "system",
        broker_adapter: Any = None,
        risk_gate: Any = None,
    ) -> TradeExecutionResult:
        """
        Execute an order after verifying pre-trade confirmation token and risk parameters.
        Enforces paper mode isolation and mechanical fortress validation.
        """
        sym = symbol.upper()
        act = action.upper()

        async with cls._get_order_lock():
            now = datetime.now(timezone.utc)
            if isinstance(session, UnitOfWorkPort):
                pos_repo = session.positions
                activity_repo = session.activity_logs
                cfg_repo = session.system_config
            else:
                pos_repo = PositionRepository(session)
                activity_repo = ActivityLogRepository(session)
                cfg_repo = SystemConfigRepository(session)

            # 1. Enforce Emergency Kill Switch status first
            is_kill_active = await cfg_repo.is_kill_switch_active()
            if not is_kill_active:
                emergency_kill = await cfg_repo.get("emergency_kill_active")
                is_kill_active = bool(emergency_kill and emergency_kill.lower() == "true")
            if is_kill_active:
                logger.warning("[TradingService] Order rejected: Emergency kill switch is active.")
                return TradeExecutionResult(
                    success=False,
                    symbol=sym,
                    action=act,
                    volume=volume,
                    error_message="Rejected: Emergency kill switch is currently active.",
                )

            # 2. Enforce confirmation token if provided
            if preview_token and token_expires_at:
                if not cls.verify_preview_token(
                    preview_token,
                    sym,
                    act,
                    volume,
                    token_expires_at,
                    is_live=not is_paper,
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                ):
                    return TradeExecutionResult(
                        success=False,
                        symbol=sym,
                        action=act,
                        volume=volume,
                        error_message="Invalid or expired pre-trade confirmation token.",
                    )

            # 3. Enforce Mechanical Fortress: RiskGate validation for ALL orders (Live & Paper)
            if stop_loss is None or stop_loss <= 0.0:
                return TradeExecutionResult(
                    success=False,
                    symbol=sym,
                    action=act,
                    volume=volume,
                    error_message="Rejected: Order requires a strictly positive stop_loss for risk protection.",
                )

            tp_val = 0.0 if (take_profit is None or take_profit <= 0.0) else float(take_profit)
            is_open_ended_tp = tp_val == 0.0

            # Validate directional geometry
            if act == "BUY":
                if stop_loss >= entry_price:
                    return TradeExecutionResult(
                        success=False,
                        symbol=sym,
                        action=act,
                        volume=volume,
                        error_message=f"BUY geometry violation: SL ({stop_loss}) must be < Entry ({entry_price})",
                    )
                if not is_open_ended_tp and tp_val <= entry_price:
                    return TradeExecutionResult(
                        success=False,
                        symbol=sym,
                        action=act,
                        volume=volume,
                        error_message=f"BUY geometry violation: TP ({tp_val}) must be > Entry ({entry_price})",
                    )
            elif act == "SELL":
                if stop_loss <= entry_price:
                    return TradeExecutionResult(
                        success=False,
                        symbol=sym,
                        action=act,
                        volume=volume,
                        error_message=f"SELL geometry violation: SL ({stop_loss}) must be > Entry ({entry_price})",
                    )
                if not is_open_ended_tp and tp_val >= entry_price:
                    return TradeExecutionResult(
                        success=False,
                        symbol=sym,
                        action=act,
                        volume=volume,
                        error_message=f"SELL geometry violation: TP ({tp_val}) must be < Entry ({entry_price})",
                    )

            try:
                from monika.domain.risk.trade_proposal import TradeProposal

                prop_dir = "BUY" if act == "BUY" else ("SELL" if act == "SELL" else "WAIT")
                proposal_meta: Dict[str, Any] = {
                    "actor": actor,
                    "source": "TradingService.submit_order",
                }
                if is_open_ended_tp:
                    proposal_meta["is_trailing"] = True

                proposal = TradeProposal(
                    symbol=sym,
                    direction=prop_dir,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=tp_val,
                    lot_size=volume,
                    confluence_score=75.0,
                    metadata=proposal_meta,
                )
                if risk_gate is not None:
                    rg = risk_gate
                else:
                    from monika.core.config.settings import load_settings
                    from monika.domain.risk.risk_gate import RiskGate

                    rg = RiskGate(settings=load_settings(), mt5_client=broker_adapter)
                verdict = await rg.evaluate_proposal(
                    session,
                    proposal,
                    is_paper=is_paper,
                    is_backtest=(actor == "unit_test"),
                )
                if not verdict.approved:
                    err_msg = f"Rejected by RiskGate: {', '.join(verdict.rejection_reasons)}"
                    logger.warning(f"[TradingService] Order {act} {volume} {sym} blocked: {err_msg}")
                    return TradeExecutionResult(
                        success=False,
                        symbol=sym,
                        action=act,
                        volume=volume,
                        error_message=err_msg,
                    )
            except Exception as e:
                logger.error(f"[TradingService] RiskGate evaluation error: {e}", exc_info=True)
                return TradeExecutionResult(
                    success=False,
                    symbol=sym,
                    action=act,
                    volume=volume,
                    error_message=f"RiskGate evaluation failure: {e}",
                )

            # 4. Paper Execution vs Live MT5 Execution
            if is_paper or broker_adapter is None:
                # Deterministic simulated ticket
                sim_ticket = int(time.time() * 1000) % 2147483647
                pos = await pos_repo.create_position(
                    symbol=sym,
                    direction=act.lower(),
                    volume=volume,
                    entry_price=entry_price,
                    sl=stop_loss,
                    tp=take_profit,
                    mt5_ticket=sim_ticket,
                    is_paper=True,
                )

                await activity_repo.log_activity(
                    category="EXECUTION",
                    description=f"Paper trade executed: {act} {volume} {sym} @ {entry_price} (Ticket: {sim_ticket})",
                    actor=actor,
                )
                await session.commit()

                return TradeExecutionResult(
                    success=True,
                    ticket=sim_ticket,
                    symbol=sym,
                    action=act,
                    volume=volume,
                    price=entry_price,
                    is_paper=True,
                    execution_time=now,
                )
            else:
                # Live broker execution through broker_adapter with strict fail-closed assertions
                try:
                    live_res = await broker_adapter.place_order(
                        symbol=sym,
                        action=act,
                        volume=volume,
                        price=entry_price,
                        sl=stop_loss,
                        tp=take_profit,
                    )
                    if not live_res:
                        return TradeExecutionResult(
                            success=False,
                            symbol=sym,
                            action=act,
                            volume=volume,
                            error_message="Broker returned empty response",
                        )
                    if isinstance(live_res, dict):
                        if not live_res.get("success"):
                            err_msg = str(live_res.get("message") or live_res.get("error") or "Broker order rejected")
                            return TradeExecutionResult(
                                success=False,
                                symbol=sym,
                                action=act,
                                volume=volume,
                                error_message=err_msg,
                            )
                        ticket_val = live_res.get("ticket") or live_res.get("order")
                        if not ticket_val:
                            return TradeExecutionResult(
                                success=False,
                                symbol=sym,
                                action=act,
                                volume=volume,
                                error_message="Broker order rejected: missing ticket identifier",
                            )
                        live_ticket = int(ticket_val)
                        price_val = live_res.get("price")
                        exec_price = float(price_val) if price_val is not None else entry_price
                    else:
                        is_succ = getattr(live_res, "success", None)
                        retcode = getattr(live_res, "retcode", None)
                        if is_succ is False or (retcode is not None and retcode != 10009):
                            err_msg = str(
                                getattr(live_res, "comment", None)
                                or getattr(live_res, "error", None)
                                or "Broker order rejected"
                            )
                            return TradeExecutionResult(
                                success=False,
                                symbol=sym,
                                action=act,
                                volume=volume,
                                error_message=err_msg,
                            )
                        ticket_val = getattr(live_res, "order", None) or getattr(live_res, "ticket", None)
                        if not ticket_val:
                            return TradeExecutionResult(
                                success=False,
                                symbol=sym,
                                action=act,
                                volume=volume,
                                error_message="Broker order rejected: missing ticket identifier",
                            )
                        live_ticket = int(ticket_val)
                        price_val = getattr(live_res, "price", None)
                        exec_price = float(price_val) if price_val is not None else entry_price

                    await pos_repo.create_position(
                        symbol=sym,
                        direction=act.lower(),
                        volume=volume,
                        entry_price=exec_price,
                        sl=stop_loss,
                        tp=take_profit,
                        mt5_ticket=live_ticket,
                        is_paper=False,
                    )

                    await activity_repo.log_activity(
                        category="EXECUTION",
                        description=f"LIVE order executed: {act} {volume} {sym} @ {exec_price} (Ticket: {live_ticket})",
                        actor=actor,
                    )
                    await session.commit()

                    return TradeExecutionResult(
                        success=True,
                        ticket=live_ticket,
                        symbol=sym,
                        action=act,
                        volume=volume,
                        price=exec_price,
                        is_paper=False,
                        execution_time=now,
                    )
                except Exception as e:
                    logger.error(f"[TradingService] Live order execution exception: {e}", exc_info=True)
                    return TradeExecutionResult(
                        success=False,
                        symbol=sym,
                        action=act,
                        volume=volume,
                        error_message=f"Live execution error: {e}",
                    )

    @classmethod
    async def close_position(
        cls,
        session: Union[AsyncSession, UnitOfWorkPort],
        ticket: int,
        reason: str = "manual_close",
        actor: str = "operator",
        broker_adapter: Any = None,
        pnl: Optional[float] = None,
    ) -> bool:
        """Close open position and record realization in repository."""
        if isinstance(session, UnitOfWorkPort):
            pos_repo = session.positions
            activity_repo = session.activity_logs
        else:
            pos_repo = PositionRepository(session)
            activity_repo = ActivityLogRepository(session)

        pos = await pos_repo.get_by_ticket(ticket)
        if not pos:
            logger.warning(f"[TradingService] Position with ticket {ticket} not found.")
            return False

        realized_pnl = pnl
        if not pos.is_paper and broker_adapter is not None:
            try:
                res = await broker_adapter.close_position(ticket=ticket)
                if isinstance(res, dict):
                    if not res.get("success", False):
                        err = res.get("error") or "Broker rejection"
                        logger.error(f"[TradingService] Failed to close live position {ticket}: {err}")
                        return False
                    if realized_pnl is None and "pnl" in res:
                        try:
                            realized_pnl = float(res["pnl"])
                        except ValueError, TypeError:
                            pass
                elif res is False:
                    logger.error(f"[TradingService] Failed to close live position {ticket}: broker returned False")
                    return False
            except Exception as e:
                logger.error(f"[TradingService] Failed to close live position {ticket}: {e}", exc_info=True)
                return False

        await pos_repo.close_position(
            ticket=ticket,
            pnl=realized_pnl,
        )

        pnl_desc = f", Realized PnL: {realized_pnl}" if realized_pnl is not None else ""
        await activity_repo.log_activity(
            category="EXECUTION",
            description=f"Closed position {ticket} ({pos.symbol}): {reason}{pnl_desc}",
            actor=actor,
        )
        await session.commit()
        return True

    @classmethod
    async def modify_position(
        cls,
        session: Union[AsyncSession, UnitOfWorkPort],
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        actor: str = "operator",
        broker_adapter: Any = None,
    ) -> bool:
        """Modify stop loss and/or take profit of an open position."""
        if isinstance(session, UnitOfWorkPort):
            pos_repo = session.positions
            activity_repo = session.activity_logs
        else:
            pos_repo = PositionRepository(session)
            activity_repo = ActivityLogRepository(session)

        pos = await pos_repo.get_by_ticket(ticket, open_only=True)
        if not pos:
            logger.warning(f"[TradingService] Open position with ticket {ticket} not found.")
            return False

        if not pos.is_paper and broker_adapter is not None:
            try:
                if hasattr(broker_adapter, "modify_position"):
                    res = await broker_adapter.modify_position(ticket=ticket, sl=sl, tp=tp)
                    if isinstance(res, dict) and not res.get("success", False):
                        err = res.get("error") or "Broker modification rejected"
                        logger.error(f"[TradingService] Broker modification rejected for #{ticket}: {err}")
                        return False
                    elif res is False:
                        logger.error(f"[TradingService] Broker modification rejected for #{ticket}")
                        return False
            except Exception as e:
                logger.error(f"[TradingService] Broker modification failed for #{ticket}: {e}", exc_info=True)
                return False

        await pos_repo.update_sl_tp(ticket=ticket, sl=sl, tp=tp)

        await activity_repo.log_activity(
            category="TRADING",
            description=f"Modified position #{ticket}: SL={sl}, TP={tp}",
            actor=actor,
            related_id=ticket,
        )
        await session.commit()
        return True

    @classmethod
    async def close_positions_batch(
        cls,
        session: Union[AsyncSession, UnitOfWorkPort],
        tickets: Sequence[int],
        reason: str = "Batch close",
        actor: str = "operator",
        broker_adapter: Any = None,
    ) -> Dict[str, Any]:
        """Close multiple positions selectively in a single batch request."""
        if isinstance(session, UnitOfWorkPort):
            pos_repo = session.positions
            activity_repo = session.activity_logs
        else:
            pos_repo = PositionRepository(session)
            activity_repo = ActivityLogRepository(session)

        closed_count = 0
        failed_count = 0
        for ticket in tickets:
            pos = await pos_repo.get_by_ticket(ticket, open_only=True)
            if not pos:
                failed_count += 1
                continue
            realized_pnl: Optional[float] = None
            if not pos.is_paper and broker_adapter is not None:
                try:
                    res = await broker_adapter.close_position(ticket=ticket)
                    if isinstance(res, dict):
                        if not res.get("success", False):
                            logger.error(f"[TradingService] Failed to close live position {ticket}: {res.get('error')}")
                            failed_count += 1
                            continue
                        if "pnl" in res:
                            try:
                                realized_pnl = float(res["pnl"])
                            except ValueError, TypeError:
                                pass
                    elif res is False:
                        failed_count += 1
                        continue
                except Exception as e:
                    logger.error(f"[TradingService] Failed to close live position {ticket}: {e}", exc_info=True)
                    failed_count += 1
                    continue
            await pos_repo.close_position(ticket=ticket, pnl=realized_pnl)
            closed_count += 1

        await activity_repo.log_activity(
            category="TRADING",
            description=f"Batch closed {closed_count} positions (requested: {len(tickets)}): {reason}",
            actor=actor,
        )
        await session.commit()
        return {
            "success": True,
            "closed_count": closed_count,
            "failed_count": failed_count,
            "tickets": list(tickets),
        }

    @classmethod
    async def bulk_breakeven(
        cls,
        session: Union[AsyncSession, UnitOfWorkPort],
        symbol: Optional[str] = None,
        actor: str = "operator",
        broker_adapter: Any = None,
    ) -> Dict[str, Any]:
        """Move Stop Loss to Entry Price across open positions and synchronize with broker."""
        if isinstance(session, UnitOfWorkPort):
            pos_repo = session.positions
            activity_repo = session.activity_logs
        else:
            pos_repo = PositionRepository(session)
            activity_repo = ActivityLogRepository(session)

        # Synchronize live MT5 positions if broker_adapter is supplied
        if broker_adapter is not None:
            open_positions = await pos_repo.get_open_positions(symbol=symbol)
            for pos in open_positions:
                if not pos.is_paper:
                    try:
                        if hasattr(broker_adapter, "modify_position"):
                            await broker_adapter.modify_position(
                                ticket=pos.ticket,
                                sl=pos.entry_price,
                                tp=pos.take_profit,
                            )
                    except Exception as e:
                        logger.warning(f"[TradingService] Broker breakeven sync failed for #{pos.ticket}: {e}")

        updated = await pos_repo.apply_bulk_breakeven(symbol=symbol)
        await activity_repo.log_activity(
            category="TRADING",
            description=f"Bulk breakeven applied to {updated} positions (symbol={symbol})",
            actor=actor,
        )
        await session.commit()
        return {
            "success": True,
            "updated_count": updated,
            "message": f"Updated {updated} positions to BE.",
        }

    @classmethod
    async def set_trailing_override(
        cls,
        session: Union[AsyncSession, UnitOfWorkPort],
        ticket: int,
        override_data: Optional[Dict[str, Any]] = None,
        reset_to_default: bool = False,
        actor: str = "operator",
    ) -> Optional[PositionEntity]:
        """Set or reset dynamic/static trailing stop override per position ticket."""
        import json

        if isinstance(session, UnitOfWorkPort):
            pos_repo = session.positions
            activity_repo = session.activity_logs
        else:
            pos_repo = PositionRepository(session)
            activity_repo = ActivityLogRepository(session)

        pos = await pos_repo.get_by_ticket(ticket)
        if not pos:
            logger.warning(f"[TradingService] Position #{ticket} not found for trailing override.")
            return None

        if reset_to_default:
            override_json = None
            msg = f"Reset trailing override to default for ticket #{ticket}"
        else:
            override_json = json.dumps(override_data) if override_data else None
            msg = f"Updated trailing override for ticket #{ticket}: {override_data}"

        updated_pos = await pos_repo.update_trailing_override(ticket=ticket, override_json=override_json)
        await activity_repo.log_activity(
            category="TRADING",
            description=msg,
            actor=actor,
            related_id=ticket,
        )
        await session.commit()
        return updated_pos

    @classmethod
    async def emergency_kill(
        cls,
        session: Union[AsyncSession, UnitOfWorkPort],
        reason: str = "Emergency stop requested",
        actor: str = "operator",
    ) -> Dict[str, Any]:
        """Activate global emergency kill switch and persist state to database."""
        if isinstance(session, UnitOfWorkPort):
            cfg_repo = session.system_config
            activity_repo = session.activity_logs
        else:
            cfg_repo = SystemConfigRepository(session)
            activity_repo = ActivityLogRepository(session)

        await cfg_repo.set("emergency_kill_active", "true")
        await cfg_repo.set("emergency_kill_reason", reason)
        await cfg_repo.set("emergency_kill_timestamp", datetime.now(timezone.utc).isoformat())
        await cfg_repo.set_kill_switch(True)

        await activity_repo.log_activity(
            category="SECURITY",
            description=f"CRITICAL: Emergency kill switch activated: {reason}",
            actor=actor,
        )
        await session.commit()
        logger.critical(f"[TradingService] EMERGENCY KILL SWITCH ACTIVATED by '{actor}': {reason}")

        return {
            "status": "HALTED",
            "reason": reason,
            "actor": actor,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    async def pause_trading(
        cls,
        session: Union[AsyncSession, UnitOfWorkPort],
        reason: str = "Trading paused",
        actor: str = "operator",
    ) -> Dict[str, Any]:
        """Pause system trading proposals and persist state."""
        if isinstance(session, UnitOfWorkPort):
            cfg_repo = session.system_config
            activity_repo = session.activity_logs
        else:
            cfg_repo = SystemConfigRepository(session)
            activity_repo = ActivityLogRepository(session)

        await cfg_repo.set_system_paused(True)
        await activity_repo.log_activity(
            category="TRADING",
            description=f"System trading paused: {reason}",
            actor=actor,
        )
        await session.commit()
        logger.info(f"[TradingService] System trading paused by '{actor}': {reason}")
        return {"status": "PAUSED", "reason": reason, "actor": actor}

    @classmethod
    async def resume_trading(
        cls,
        session: Union[AsyncSession, UnitOfWorkPort],
        actor: str = "operator",
    ) -> Dict[str, Any]:
        """Resume system trading operations and lift pause flags."""
        if isinstance(session, UnitOfWorkPort):
            cfg_repo = session.system_config
            activity_repo = session.activity_logs
        else:
            cfg_repo = SystemConfigRepository(session)
            activity_repo = ActivityLogRepository(session)

        await cfg_repo.set("suspended_symbols", "[]")
        for key in (
            "kill_switch",
            "emergency_kill_active",
            "system_paused",
            "budget_pause",
            "trading_paused",
            "manual_trading_paused",
        ):
            await cfg_repo.set(key, "false")

        await activity_repo.log_activity(
            category="TRADING",
            description="System trading resumed and pause flags cleared",
            actor=actor,
        )
        await session.commit()

        # Ensure physical disk kill switch flag is removed
        from monika.core.paths import DATA_DIR

        disk_flag = DATA_DIR / "kill_switch.flag"
        if disk_flag.exists():
            try:
                disk_flag.unlink(missing_ok=True)
                logger.info(f"[TradingService] Removed disk kill switch flag: {disk_flag}")
            except Exception as flag_err:
                logger.error(f"[TradingService] Failed removing disk kill flag: {flag_err}")

        logger.info(f"[TradingService] System trading resumed by '{actor}'")
        return {"status": "RESUMED", "actor": actor}
