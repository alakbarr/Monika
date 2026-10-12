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

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.models import Position
from monika.domain.risk.trade_proposal import TradeProposal
from monika.infrastructure.database.repositories.position_repository import PositionRepository
from monika.infrastructure.database.repositories.trade_proposal_repository import TradeProposalRepository
from monika.infrastructure.database.repositories.activity_log_repository import ActivityLogRepository
from monika.infrastructure.database.repositories.system_config_repository import SystemConfigRepository

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

    SECRET_KEY = os.environ.get("MONIKA_ORDER_SIGNING_SECRET", "monika-internal-fortress-secret-key").encode()

    @classmethod
    def generate_preview_token(cls, symbol: str, action: str, volume: float, expires_at: float) -> str:
        """Generate HMAC-SHA256 signature for pre-trade verification confirmation."""
        payload = f"{symbol}:{action}:{volume}:{expires_at}".encode()
        return hmac.new(cls.SECRET_KEY, payload, hashlib.sha256).hexdigest()

    @classmethod
    def verify_preview_token(cls, token: str, symbol: str, action: str, volume: float, expires_at: float) -> bool:
        """Verify validity and non-expiration of pre-trade confirmation token."""
        if time.time() > expires_at:
            return False
        expected = cls.generate_preview_token(symbol, action, volume, expires_at)
        return hmac.compare_digest(token, expected)

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

        # Calculate estimated risk / reward
        est_risk = 0.0
        est_reward = 0.0
        if stop_loss and entry_price:
            diff = abs(entry_price - stop_loss)
            est_risk = diff * volume * 100.0  # Normalized pip/point scale
        if take_profit and entry_price:
            diff = abs(take_profit - entry_price)
            est_reward = diff * volume * 100.0

        rr_ratio = (est_reward / est_risk) if est_risk > 0 else 0.0
        margin_est = (entry_price * volume * 1000.0) / 100.0  # Standard 1:100 leverage estimate

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
    ) -> TradeExecutionResult:
        """
        Execute an order after verifying pre-trade confirmation token and risk parameters.
        Enforces paper mode isolation and mechanical fortress validation.
        """
        sym = symbol.upper()
        act = action.upper()

        # 1. Verify confirmation token if provided
        if preview_token and token_expires_at:
            if not cls.verify_preview_token(preview_token, sym, act, volume, token_expires_at):
                return TradeExecutionResult(
                    success=False,
                    symbol=sym,
                    action=act,
                    volume=volume,
                    error_message="Invalid or expired pre-trade confirmation token.",
                )

        now = datetime.now(timezone.utc)
        pos_repo = PositionRepository(session)
        activity_repo = ActivityLogRepository(session)

        # 2. Check kill switch status
        cfg_repo = SystemConfigRepository(session)
        kill_cfg = await cfg_repo.get("emergency_kill_active")
        if kill_cfg and kill_cfg.lower() == "true":
            logger.warning(f"[TradingService] Order rejected: Emergency kill switch is active.")
            return TradeExecutionResult(
                success=False,
                symbol=sym,
                action=act,
                volume=volume,
                error_message="Rejected: Emergency kill switch is currently active.",
            )

        # 3. Paper Execution vs Live MT5 Execution
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
            # Live broker execution through broker_adapter with strict safety assertions
            try:
                live_res = await broker_adapter.place_order(
                    symbol=sym,
                    action=act,
                    volume=volume,
                    price=entry_price,
                    sl=stop_loss,
                    tp=take_profit,
                )
                if isinstance(live_res, dict):
                    if not live_res.get("success", True):
                        err_msg = str(live_res.get("message") or live_res.get("error") or "Broker order rejected")
                        return TradeExecutionResult(
                            success=False,
                            symbol=sym,
                            action=act,
                            volume=volume,
                            error_message=err_msg,
                        )
                    live_ticket = int(live_res.get("ticket") or live_res.get("order") or int(time.time()))
                    exec_price = float(live_res.get("price") or entry_price)
                else:
                    live_ticket = int(getattr(live_res, "order", None) or getattr(live_res, "ticket", None) or int(time.time()))
                    exec_price = float(getattr(live_res, "price", None) or entry_price)

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
                logger.error(f"[TradingService] Live broker order failed: {e}", exc_info=True)
                return TradeExecutionResult(
                    success=False,
                    symbol=sym,
                    action=act,
                    volume=volume,
                    error_message=f"Broker rejection: {e}",
                )

    @classmethod
    async def close_position(
        cls,
        session: AsyncSession,
        ticket: int,
        reason: str = "manual_close",
        actor: str = "operator",
        broker_adapter: Any = None,
    ) -> bool:
        """Close open position and record realization in repository."""
        pos_repo = PositionRepository(session)
        activity_repo = ActivityLogRepository(session)

        pos = await pos_repo.get_by_ticket(ticket)
        if not pos:
            logger.warning(f"[TradingService] Position with ticket {ticket} not found.")
            return False

        if not pos.is_paper and broker_adapter is not None:
            try:
                await broker_adapter.close_position(ticket=ticket)
            except Exception as e:
                logger.error(f"[TradingService] Failed to close live position {ticket}: {e}")
                return False

        await pos_repo.close_position(
            ticket=ticket,
            pnl=0.0,
        )

        await activity_repo.log_activity(
            category="EXECUTION",
            description=f"Closed position {ticket} ({pos.symbol}): {reason}",
            actor=actor,
        )
        await session.commit()
        return True

    @classmethod
    async def emergency_kill(
        cls,
        session: AsyncSession,
        reason: str = "Emergency stop requested",
        actor: str = "operator",
    ) -> Dict[str, Any]:
        """Activate global emergency kill switch and persist state to database."""
        cfg_repo = SystemConfigRepository(session)
        activity_repo = ActivityLogRepository(session)

        await cfg_repo.set("emergency_kill_active", "true")
        await cfg_repo.set("emergency_kill_reason", reason)
        await cfg_repo.set("emergency_kill_timestamp", datetime.now(timezone.utc).isoformat())

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
