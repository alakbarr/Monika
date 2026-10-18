# ==============================================================================
# File: domain/risk/evaluators/execution_checks.py
# ==============================================================================

"""
Order, position sizing, spread, duplicate, and loss cooldown checks for RiskGate.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import math
from datetime import datetime, timedelta, timezone, UTC
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import monika.core.primitives.clock as clock
from monika.domain.entities.order_status import OrderStatus
from monika.domain.risk.evaluators.base import _RiskGateMixinBase, get_trading_day_start, resolve_model
from monika.domain.risk.position_sizing import SizingResult

Position: Any = resolve_model("Position")
RiskState: Any = resolve_model("RiskState")
TradeOutcome: Any = resolve_model("TradeOutcome")
PaperTradeRecord: Any = resolve_model("PaperTradeRecord")
SystemConfig: Any = resolve_model("SystemConfig")
Order: Any = resolve_model("Order")

logger = logging.getLogger("TradingAgent.RiskGate")


DEFAULT_SYMBOL_MAX_SPREAD_POINTS: dict[str, float] = {
    "BTCUSD": 3500.0,
    "ETHUSD": 2500.0,
    "XAUUSD": 150.0,
    "XTIUSD": 150.0,
    "XBRUSD": 150.0,
}


class RiskExecutionChecksMixin(_RiskGateMixinBase):
    """Execution, order size, spread, duplicate, and loss streak validation mixin."""

    async def _check_consecutive_losses(self, session: Any, symbol: str, is_backtest: bool = False) -> tuple[bool, str]:
        """Check apakah symbol ini sedang dalam losing streak yang berbahaya."""
        if is_backtest:
            return (True, "consecutive_losses_backtest_ok")

        from sqlalchemy import select

        trading_cfg = self.settings.get("trading", {}) if isinstance(self.settings.get("trading"), dict) else {}
        auto_execute = trading_cfg.get("auto_execute", False)
        paper_raw = trading_cfg.get("paper_trading", {})
        if isinstance(paper_raw, dict):
            paper_cfg = paper_raw
        elif isinstance(self.settings.get("paper_trading"), dict):
            paper_cfg = self.settings["paper_trading"]
        elif isinstance(paper_raw, bool):
            paper_cfg = {"enabled": paper_raw}
        else:
            paper_cfg = {}
        streak_policy = (
            paper_cfg.get("streak_loss_policy", "warn_and_scale") if isinstance(paper_cfg, dict) else "warn_and_scale"
        )
        risk_cfg = trading_cfg.get("risk", {}) if isinstance(trading_cfg.get("risk"), dict) else {}
        max_consecutive = risk_cfg.get("max_consecutive_losses_per_symbol", 3)

        # Check recent losses (limited to past 7 days lookback)
        cutoff = clock.now() - timedelta(days=7)
        recent = (
            (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.symbol == symbol)
                    .where(PaperTradeRecord.status == "closed")
                    .where(PaperTradeRecord.closed_at >= cutoff)
                    .order_by(PaperTradeRecord.closed_at.desc())
                    .limit(max_consecutive + 1)
                )
            )
            .scalars()
            .all()
        )

        consecutive_losses = 0
        for trade in recent:
            if (trade.pnl_pct is not None and trade.pnl_pct < 0) or trade.exit_reason == "sl_hit":
                consecutive_losses += 1
            else:
                break

        # Jika mode paper trading (auto_execute=False atau dry-run)
        if not auto_execute:
            if streak_policy == "disabled":
                return (True, f"consecutive_losses_paper_disabled(streak={consecutive_losses})")
            elif streak_policy == "warn_and_scale":
                scale_factor = paper_cfg.get("streak_risk_scale_factor", 0.5) if isinstance(paper_cfg, dict) else 0.5
                if consecutive_losses >= max_consecutive:
                    return (
                        True,
                        f"consecutive_losses_paper_warn_and_scale(streak={consecutive_losses}, scale={scale_factor})",
                    )
                return (True, f"consecutive_losses_paper_ok({consecutive_losses}/{max_consecutive})")

        # Mode strict / Live Trading:
        from monika.domain.risk.ports import get_default_suspended_symbols_provider

        provider_factory = get_default_suspended_symbols_provider()
        if provider_factory is not None:
            suspended = await provider_factory(self.settings).get_suspended_symbols(session)
        else:
            try:
                import importlib

                tracker_mod = importlib.import_module("monika.core.analytics.paper_tracker")
                tracker_cls = getattr(tracker_mod, "PaperTracker")
                suspended = await tracker_cls(self.settings).get_suspended_symbols(session)
            except Exception:
                suspended = []
        if symbol in suspended:
            return (False, f"{symbol} is suspended due to consecutive losses")

        if consecutive_losses >= max_consecutive:
            return (
                False,
                f"{symbol}: {consecutive_losses} consecutive SL hits detected. "
                f"Auto-suspend should have triggered. Blocking as safety measure.",
            )

        return (True, f"consecutive_losses={consecutive_losses}/{max_consecutive}")

    async def _check_not_paused(self, session: Any, is_backtest: bool = False) -> tuple[bool, str]:
        """Periksa bahwa trading belum di-pause manual."""
        if is_backtest:
            return (True, "ok")

        from sqlalchemy import select

        # Check persistent SystemConfig manual pause & emergency kill switch (persists across midnight rollover)
        pause_configs = (
            (
                await session.execute(
                    select(SystemConfig).where(
                        SystemConfig.key.in_(
                            ["manual_trading_paused", "system_paused", "kill_switch", "system_kill_switch"]
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        for cfg in pause_configs:
            if cfg and cfg.value and cfg.value.split(":", 1)[0].strip().lower() == "true":
                val_parts = cfg.value.split("|unpause_at:", 1)
                if len(val_parts) > 1 and cfg.key == "manual_trading_paused":
                    try:
                        exp_dt = datetime.fromisoformat(val_parts[1].strip())
                        if clock.now() >= exp_dt:
                            cfg.value = "false"
                            if hasattr(session, "commit"):
                                try:
                                    await session.commit()
                                except Exception as e:
                                    logger.debug(f"Failed to commit auto-unpause config: {e}")
                            continue
                    except Exception:
                        pass
                reason = cfg.value.split(":", 1)[1] if ":" in cfg.value else f"kill switch active ({cfg.key})"
                return False, f"Trading is blocked by {cfg.key}: {reason}"

        today_start = get_trading_day_start(self.settings)
        state = (
            await session.execute(
                select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
            )
        ).scalar_one_or_none()

        if state and state.trading_paused:
            unpause_time = getattr(state, "unpause_at", None)
            if isinstance(unpause_time, datetime) and clock.now() >= unpause_time:
                state.trading_paused = False
                state.unpause_at = None
                state.reason = None
                cfg = (
                    await session.execute(select(SystemConfig).where(SystemConfig.key == "manual_trading_paused"))
                ).scalar_one_or_none()
                if cfg:
                    cfg.value = "false"
                if hasattr(session, "commit"):
                    try:
                        await session.commit()
                    except Exception as e:
                        logger.warning(f"Failed to commit auto-unpause state: {e}")
                logger.info("Timed trading pause expired, automatically resumed.")
                return True, "ok"
            return False, f"Trading is manually paused: {state.reason or 'no reason given'}"
        return True, "ok"

    async def _check_daily_trade_count(
        self,
        session: Any,
        is_backtest: bool = False,
        is_paper: bool | None = None,
    ) -> tuple[bool, str]:
        """Hard limit: max N trades per day regardless of other conditions"""
        if is_backtest:
            return (True, "daily_trades_backtest_ok")
        today_start = get_trading_day_start(self.settings)
        from datetime import timedelta
        from sqlalchemy import func, select

        today_end = today_start + timedelta(days=1)
        # Count from positions opened today (separating live vs paper positions)
        # to ensure paper simulation trades do not exhaust live quota limits.

        # Hitung posisi live yang dibuka hari ini
        live_today = (
            await session.execute(
                select(func.count(Position.id))
                .where(Position.opened_at >= today_start)
                .where(Position.opened_at < today_end)
                .where(Position.is_paper == False)  # noqa: E712
            )
        ).scalar_one_or_none() or 0

        # Hitung paper trades yang dibuka hari ini (sebagai proxy jika belum ada live trades)
        paper_today = (
            await session.execute(
                select(func.count(PaperTradeRecord.id))
                .where(PaperTradeRecord.opened_at >= today_start)
                .where(PaperTradeRecord.opened_at < today_end)
                .where(PaperTradeRecord.is_pending_fill == False)  # noqa: E712
            )
        ).scalar_one_or_none() or 0

        # Pisahkan live vs paper (DB-14)
        if is_paper is None:
            pt_cfg = self.settings.get("paper_trading", {})
            if isinstance(pt_cfg, dict):
                is_paper = bool(pt_cfg.get("enabled", False))
            elif isinstance(pt_cfg, bool):
                is_paper = pt_cfg
            else:
                is_paper = False

        today_trades = paper_today if is_paper else live_today
        trade_label = "paper" if is_paper else "live"

        max_daily_trades = self.settings.get("trading", {}).get("risk", {}).get("max_daily_trades", 3)
        logger.debug(
            f"Daily trade count ({trade_label}): live_positions_today={live_today}, "
            f"paper_trades_today={paper_today}, effective_count={today_trades}/{max_daily_trades}"
        )

        if today_trades >= max_daily_trades:
            return (
                False,
                f"Daily {trade_label} trade limit reached: {today_trades}/{max_daily_trades} trades opened today.",
            )
        return (True, f"daily_{trade_label}_trades={today_trades}/{max_daily_trades}")

    async def _check_sizing_valid(self, sizing: SizingResult) -> tuple[bool, str]:
        """Validasi bahwa position sizing sebelumnya (engine) telah sukses."""
        if not sizing.is_valid:
            return False, f"Invalid sizing: {'; '.join(sizing.rejection_reasons)}"
        if (
            sizing.recommended_lots is None
            or not math.isfinite(sizing.recommended_lots)
            or sizing.recommended_lots <= 0
        ):
            return False, "Recommended lots is zero, negative, or non-finite"
        if not math.isfinite(sizing.entry_price) or not math.isfinite(sizing.stop_loss):
            return False, "Entry price or stop loss is non-finite"
        return True, "ok"

    async def _check_lot_size(self, sizing: SizingResult) -> tuple[bool, str]:
        """Validasi bahwa ukuran lot berada dalam batas aman."""
        if (
            sizing.recommended_lots is None
            or not math.isfinite(sizing.recommended_lots)
            or sizing.recommended_lots <= 0
        ):
            return False, "Lot size is non-finite, zero, or negative"

        # Check against max_lot from instrument spec
        # (Position sizing already handles this, but double-check here)
        # We use a hard limit of 100 lots as absolute maximum for any instrument
        ABSOLUTE_MAX_LOTS = 100.0
        if sizing.recommended_lots > ABSOLUTE_MAX_LOTS:
            return False, f"Lot size {sizing.recommended_lots} exceeds absolute maximum {ABSOLUTE_MAX_LOTS}"

        # Check minimum lot
        ABSOLUTE_MIN_LOTS = 0.001
        if sizing.recommended_lots < ABSOLUTE_MIN_LOTS:
            return False, f"Lot size {sizing.recommended_lots} is below minimum tradeable {ABSOLUTE_MIN_LOTS}"

        return True, f"lot_size={sizing.recommended_lots} (valid)"

    async def _check_min_rr_ratio(self, sizing: SizingResult) -> tuple[bool, str]:
        """Validasi bahwa Risk-to-Reward ratio proposal memenuhi batas minimum (FR-4.1)."""
        rr = getattr(sizing, "rr_ratio", None)
        if rr is None or not math.isfinite(rr) or rr <= 0:
            return (
                False,
                "Risk-to-reward ratio missing, non-finite, or non-positive; rejected by FR-4.1 fail-closed protection",
            )
        min_rr = float(self.settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.3))
        if rr < min_rr:
            return False, f"Risk-to-reward ratio {rr:.2f} is below minimum requirement {min_rr:.2f}"
        return True, f"rr_ratio={rr:.2f} >= {min_rr:.2f} (valid)"

    async def _check_max_spread(
        self, session: Any, symbol: str, is_backtest: bool = False, is_paper: bool | None = None
    ) -> tuple[bool, str]:
        """Validasi batas spread pasar tidak sedang melebar (FR-4.1)."""
        if is_backtest:
            return True, "backtest_spread_ok"
        if is_paper is not None:
            effective_paper = is_paper
        else:
            pt_cfg = self.settings.get("paper_trading", {})
            if isinstance(pt_cfg, dict):
                effective_paper = bool(pt_cfg.get("enabled", True))
            elif isinstance(pt_cfg, bool):
                effective_paper = pt_cfg
            else:
                effective_paper = True
        try:
            client: Any = getattr(self, "_mt5", None)
            if client is None:
                try:
                    import importlib

                    broker_mod = importlib.import_module("monika.infrastructure.brokers.mt5_client")
                    get_client_fn = getattr(broker_mod, "get_mt5_client", None)
                    if callable(get_client_fn):
                        client = get_client_fn()
                except Exception:
                    client = None
            if client is None:
                if effective_paper:
                    return True, "no_client_spread_skipped"
                return False, "mt5_client_unavailable_spread_blocked"
            is_conn = (
                await client.is_connected()
                if callable(getattr(client, "is_connected", None))
                else getattr(client, "is_connected", False)
            )
            if asyncio.iscoroutine(is_conn):
                is_conn = await is_conn
            if not is_conn:
                if effective_paper:
                    return True, "client_disconnected_spread_skipped"
                return False, "client_disconnected_spread_blocked"
            spread_info = await client.get_spread(symbol)
            if asyncio.iscoroutine(spread_info):
                spread_info = await spread_info
            spread_pts = spread_info.get("spread_points", 0) if isinstance(spread_info, dict) else 0
            default_spread = DEFAULT_SYMBOL_MAX_SPREAD_POINTS.get(symbol, 100.0)
            max_spread = float(
                self.settings.get("trading", {})
                .get("risk", {})
                .get("max_spread_points", {})
                .get(symbol, default_spread)
            )
            if spread_pts > max_spread:
                return False, f"Current spread {spread_pts} pts exceeds maximum allowed {max_spread} pts"
            return True, "ok"
        except Exception as e:
            logger.debug(f"Spread check error: {e}")
            return False, f"spread_check_error: {e}"

    async def _check_max_positions(
        self,
        session: Any,
        simulated_positions: list | None = None,
        is_paper: bool | None = None,
    ) -> tuple[bool, str]:
        """Pastikan batas maksimal posisi terbuka (concurrent) belum terlewati."""
        if simulated_positions is not None:
            count = len(simulated_positions)
            if count >= self.max_concurrent:
                return False, f"Max concurrent positions reached (simulated): {count}/{self.max_concurrent}"
            return True, f"open_positions={count}/{self.max_concurrent}"

        from sqlalchemy import func, select

        stmt = select(func.count(Position.id)).where(Position.status == "open")
        if is_paper is not None:
            stmt = stmt.where(Position.is_paper == is_paper)
        count = (await session.execute(stmt)).scalar_one_or_none() or 0

        # Also account for pending/in-flight orders to prevent concurrent over-allocation
        order_stmt = select(func.count(Order.id)).where(
            Order.status.in_(
                [
                    OrderStatus.ACCEPTED,
                    OrderStatus.SUBMITTED,
                    OrderStatus.INTENT_COMMITTED,
                    OrderStatus.PARTIALLY_FILLED,
                ]
            )
        )
        pending_count = (await session.execute(order_stmt)).scalar_one_or_none() or 0
        total_exposure = count + pending_count

        if total_exposure >= self.max_concurrent:
            return False, (
                f"Max concurrent exposure reached: {total_exposure}/{self.max_concurrent} "
                f"(open={count}, pending={pending_count})"
            )
        return True, f"open_positions={count}, pending={pending_count}, total={total_exposure}/{self.max_concurrent}"

    async def _check_no_duplicate(
        self,
        session: Any,
        symbol: str,
        simulated_positions: list | None = None,
        pair_group_id: str | None = None,
        is_paper: bool | None = None,
    ) -> tuple[bool, str]:
        """Pastikan hanya ada SATU posisi terbuka untuk simbol ini (kecuali multi-leg/tranche dengan pair_group_id)."""
        if simulated_positions is not None:
            for pos in simulated_positions:
                pos_sym = getattr(pos, "symbol", None) or (pos.get("symbol") if isinstance(pos, dict) else None)
                pos_group = getattr(pos, "pair_group_id", None) or (
                    pos.get("pair_group_id") if isinstance(pos, dict) else None
                )
                if pos_sym == symbol:
                    if pair_group_id and pos_group == pair_group_id:
                        continue
                    return False, f"Already have an open simulated position for {symbol}"
            return True, "no duplicate (simulated)"

        from sqlalchemy import func, select

        # Check pending/in-flight orders for this symbol first
        pending_stmt = select(Order.id).where(
            Order.symbol == symbol,
            Order.status.in_(
                [
                    OrderStatus.ACCEPTED,
                    OrderStatus.SUBMITTED,
                    OrderStatus.INTENT_COMMITTED,
                    OrderStatus.PARTIALLY_FILLED,
                ]
            ),
        )
        pending_order = (await session.execute(pending_stmt.limit(1))).scalar_one_or_none()
        if pending_order is not None and not pair_group_id:
            return False, f"Already have an active pending/in-flight order for {symbol} (id={pending_order})"

        if pair_group_id:
            # DB-15: Posisi dengan pair_group_id diizinkan multi-leg/tranche dalam group yang sama
            conflict_stmt = (
                select(Position.id)
                .where(Position.symbol == symbol)
                .where(Position.status == "open")
                .where((Position.pair_group_id != pair_group_id) | (Position.pair_group_id.is_(None)))
            )
            if is_paper is not None:
                conflict_stmt = conflict_stmt.where(Position.is_paper == is_paper)
            conflict = (await session.execute(conflict_stmt.limit(1))).scalar_one_or_none()
            if conflict is not None:
                return (
                    False,
                    f"Already have an open position for {symbol} outside pair group {pair_group_id} (id={conflict})",
                )

            group_stmt = (
                select(func.count(Position.id))
                .where(Position.symbol == symbol)
                .where(Position.status == "open")
                .where(Position.pair_group_id == pair_group_id)
            )
            if is_paper is not None:
                group_stmt = group_stmt.where(Position.is_paper == is_paper)
            group_count = (await session.execute(group_stmt)).scalar_one_or_none() or 0
            if group_count >= 2:
                return False, f"Pair group {pair_group_id} already has max legs ({group_count}) for {symbol}"
            return True, "no duplicate (pair group leg allowed)"

        existing_stmt = select(Position.id).where(Position.symbol == symbol).where(Position.status == "open")
        if is_paper is not None:
            existing_stmt = existing_stmt.where(Position.is_paper == is_paper)
        existing = (await session.execute(existing_stmt.limit(1))).scalar_one_or_none()

        if existing is not None:
            return False, f"Already have an open position for {symbol} (id={existing})"
        return True, "no duplicate"

    async def _check_post_loss_cooldown(
        self, session: Any, symbol: str, as_of: datetime | None = None, is_backtest: bool = False
    ) -> tuple[bool, str]:
        """Blokir re-entry pada simbol yang sama selama N jam jika baru saja terkena Stop Loss."""
        if is_backtest:
            return True, "cooldown_backtest_ok"
        cooldown_hours = self.settings.get("trading", {}).get("risk", {}).get("post_sl_cooldown_hours", 6)
        if cooldown_hours <= 0:
            return True, "cooldown disabled"

        from sqlalchemy import select

        now = as_of or clock.now()
        since = now - timedelta(hours=cooldown_hours)

        # Check for recent SL hits on this symbol
        recent_sl = (
            await session.execute(
                select(TradeOutcome)
                .where(TradeOutcome.symbol == symbol)
                .where(TradeOutcome.exit_reason == "sl_hit")
                .where(TradeOutcome.closed_at >= since)
                .limit(1)
            )
        ).scalar_one_or_none()

        # Also check PaperTradeRecord for sl_hit
        if recent_sl is None:
            recent_sl_paper = (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.symbol == symbol)
                    .where(PaperTradeRecord.exit_reason == "sl_hit")
                    .where(PaperTradeRecord.closed_at >= since)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if recent_sl_paper and recent_sl_paper.closed_at is not None:
                hours_ago = (now - recent_sl_paper.closed_at).total_seconds() / 3600
                return False, (
                    f"Post-SL cooldown active for {symbol}: "
                    f"SL was hit {hours_ago:.1f}h ago. Cooldown: {cooldown_hours}h. "
                    f"Prevents immediate re-entry after loss."
                )
        elif recent_sl is not None and recent_sl.closed_at is not None:
            hours_ago = (now - recent_sl.closed_at).total_seconds() / 3600
            return False, (
                f"Post-SL cooldown active for {symbol}: SL was hit {hours_ago:.1f}h ago. Cooldown: {cooldown_hours}h."
            )

        return True, "no recent SL hits"


__all__ = ["RiskExecutionChecksMixin"]
