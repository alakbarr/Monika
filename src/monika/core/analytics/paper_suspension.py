# ==============================================================================
# File: core/analytics/paper_suspension.py
# ==============================================================================

"""
Symbol Suspension & Streak Policy Engine for Paper Trading.
Handles consecutive loss tracking, cool-off windows, and auto-suspensions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.infrastructure.database.models import PaperTradeRecord, SystemConfig

logger = logging.getLogger("TradingAgent.PaperTracker")


async def get_suspended_symbols(session: AsyncSession) -> list[str]:
    """Return list of symbols currently suspended due to poor performance"""
    from sqlalchemy import select

    from monika.infrastructure.database.models import SystemConfig

    cfg = (
        await session.execute(select(SystemConfig).where(SystemConfig.key == "suspended_symbols"))
    ).scalar_one_or_none()

    if not cfg or not cfg.value:
        return []

    try:
        import json

        data = json.loads(cfg.value)
        now = clock.now()
        # Filter out suspensions that have expired
        active = [s for s in data if datetime.fromisoformat(s["until"]) > now]
        return [s["symbol"] for s in active]
    except Exception:
        return []


async def check_and_suspend_poor_performers(session: AsyncSession, settings: dict) -> list[str]:
    """
    Auto-suspend symbols with consecutive losses.
    Returns list of newly suspended symbols.
    Respects trading.paper_trading.streak_loss_policy and prevents infinite re-suspension loop.
    """
    import json

    from sqlalchemy import select

    from monika.infrastructure.database.models import PaperTradeRecord, SystemConfig

    paper_cfg = settings.get("trading", {}).get("paper_trading", {})
    streak_policy = paper_cfg.get("streak_loss_policy", "warn_and_scale")
    is_auto_execute = settings.get("trading", {}).get("auto_execute", False)

    # Jika paper exploration mode (disabled / warn_and_scale) dan bukan live trading:
    if not is_auto_execute and streak_policy in ("disabled", "warn_and_scale"):
        logger.debug(f"[PaperTracker] Skipping auto-suspension (streak_loss_policy: '{streak_policy}')")
        return []

    newly_suspended = []
    max_consecutive_losses = settings.get("trading", {}).get("risk", {}).get("max_consecutive_losses_per_symbol", 3)
    suspension_hours = paper_cfg.get(
        "suspension_hours",
        settings.get("trading", {}).get("risk", {}).get("suspension_hours_after_consecutive_losses", 12),
    )

    asset_universe = settings.get("trading", {}).get("asset_universe", [])

    cfg = (
        await session.execute(select(SystemConfig).where(SystemConfig.key == "suspended_symbols"))
    ).scalar_one_or_none()

    current = []
    if cfg and cfg.value:
        try:
            current = json.loads(cfg.value)
        except Exception:
            current = []

    now = clock.now()

    for symbol in asset_universe:
        # FIX INFINITE LOOP: Cek apakah simbol ini sebelumnya pernah di-suspend
        prev_entry = next((s for s in current if s.get("symbol") == symbol), None)
        last_suspended_until = None
        if prev_entry and "until" in prev_entry:
            try:
                last_suspended_until = datetime.fromisoformat(prev_entry["until"])
            except Exception:
                last_suspended_until = None

        query = (
            select(PaperTradeRecord)
            .where(PaperTradeRecord.symbol == symbol)
            .where(PaperTradeRecord.status == "closed")
            .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
        )
        # Jika suspensi sebelumnya telah expired, HANYA hitung trade yang ditutup SETELAH masa suspensi berakhir
        if last_suspended_until and last_suspended_until <= now:
            query = query.where(PaperTradeRecord.closed_at > last_suspended_until)

        recent = (
            (await session.execute(query.order_by(PaperTradeRecord.closed_at.desc()).limit(max_consecutive_losses + 1)))
            .scalars()
            .all()
        )

        consecutive_losses = 0
        for trade in recent:
            if trade.exit_reason == "sl_hit":
                consecutive_losses += 1
            else:
                break

        if consecutive_losses >= max_consecutive_losses:
            # Suspend this symbol
            until = (now + timedelta(hours=suspension_hours)).isoformat()

            # Remove old entry for this symbol if exists
            current = [s for s in current if s.get("symbol") != symbol]
            current.append(
                {
                    "symbol": symbol,
                    "suspended_at": now.isoformat(),
                    "until": until,
                    "reason": f"{consecutive_losses} consecutive losses",
                }
            )

            newly_suspended.append(symbol)
            logger.warning(
                f"AUTO-SUSPENDED {symbol}: {consecutive_losses} consecutive SL hits. Suspended for {suspension_hours}h."
            )

            try:
                from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

                await AgentNotifier().send_warning(
                    f"[DIJEDA] <b>{symbol} Auto-Suspended</b>\n"
                    f"{consecutive_losses} consecutive losses detected.\n"
                    f"Suspended for {suspension_hours}h until {until[:16]} UTC.\n"
                    f"Review recent analyses to identify systematic issue."
                )
            except Exception:
                pass

    if newly_suspended:
        if cfg:
            cfg.value = json.dumps(current)
        else:
            session.add(SystemConfig(key="suspended_symbols", value=json.dumps(current)))
        await session.commit()

    return newly_suspended


async def suspend_symbol(
    session: AsyncSession, symbol: str, duration_hours: float = 24.0, reason: str = "manual_command"
) -> dict:
    """Suspend trading untuk simbol tertentu secara manual dengan durasi waktu."""
    import json
    from datetime import timedelta

    from sqlalchemy import select

    from monika.infrastructure.database.models import SystemConfig

    sym_norm = symbol.strip().upper().replace("/", "")
    cfg = (
        await session.execute(select(SystemConfig).where(SystemConfig.key == "suspended_symbols"))
    ).scalar_one_or_none()

    current = []
    if cfg and cfg.value:
        try:
            current = json.loads(cfg.value)
        except Exception:
            current = []

    now = clock.now()
    until = now + timedelta(hours=duration_hours)
    until_iso = until.isoformat()

    entry = {"symbol": sym_norm, "until": until_iso, "reason": reason}
    updated = False
    for s in current:
        if s.get("symbol", "").upper() == sym_norm:
            s["until"] = until_iso
            s["reason"] = reason
            updated = True
            break
    if not updated:
        current.append(entry)

    if cfg:
        cfg.value = json.dumps(current)
    else:
        session.add(SystemConfig(key="suspended_symbols", value=json.dumps(current)))
    await session.commit()
    logger.warning(f"[PaperTracker] Symbol {sym_norm} suspended manually until {until_iso} (reason={reason})")
    return {"symbol": sym_norm, "until": until_iso, "duration_hours": duration_hours, "reason": reason}


async def unsuspend_symbol(session: AsyncSession, symbol: str) -> bool:
    """Buka suspensi untuk simbol tertentu."""
    import json

    from sqlalchemy import select

    from monika.infrastructure.database.models import SystemConfig

    cfg = (
        await session.execute(select(SystemConfig).where(SystemConfig.key == "suspended_symbols"))
    ).scalar_one_or_none()
    if not cfg or not cfg.value:
        return False
    try:
        current = json.loads(cfg.value)
        new_list = [s for s in current if s.get("symbol", "").upper() != symbol.upper()]
        if len(new_list) != len(current):
            cfg.value = json.dumps(new_list)
            await session.commit()
            logger.info(f"[PaperTracker] Symbol {symbol} unsuspended successfully.")
            return True
    except Exception as e:
        logger.error(f"Failed to unsuspend {symbol}: {e}")
    return False


async def unsuspend_all(session: AsyncSession) -> list[str]:
    """Buka suspensi untuk semua simbol."""
    import json

    from sqlalchemy import select

    from monika.infrastructure.database.models import SystemConfig

    cfg = (
        await session.execute(select(SystemConfig).where(SystemConfig.key == "suspended_symbols"))
    ).scalar_one_or_none()
    if not cfg or not cfg.value:
        return []
    try:
        current = json.loads(cfg.value)
        cleared_symbols = [s.get("symbol") for s in current if s.get("symbol")]
        cfg.value = json.dumps([])
        await session.commit()
        logger.info(f"[PaperTracker] All symbols unsuspended: {cleared_symbols}")
        return cleared_symbols
    except Exception as e:
        logger.error(f"Failed to unsuspend all: {e}")
        return []


async def get_streak_status(session: AsyncSession, symbol: str, settings: Optional[dict] = None) -> dict:
    """Mengambil status streak loss dan suspensi untuk simbol tertentu."""
    from sqlalchemy import select

    from monika.infrastructure.database.models import PaperTradeRecord

    recent = (
        (
            await session.execute(
                select(PaperTradeRecord)
                .where(PaperTradeRecord.symbol == symbol)
                .where(PaperTradeRecord.status == "closed")
                .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
                .order_by(PaperTradeRecord.closed_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )

    consecutive_losses = 0
    for trade in recent:
        if trade.exit_reason == "sl_hit":
            consecutive_losses += 1
        else:
            break

    suspended_list = await get_suspended_symbols(session)
    is_suspended = symbol in suspended_list

    paper_cfg = (settings or {}).get("trading", {}).get("paper_trading", {})
    streak_policy = paper_cfg.get("streak_loss_policy", "warn_and_scale")

    return {
        "symbol": symbol,
        "consecutive_losses": consecutive_losses,
        "is_suspended": is_suspended,
        "streak_policy": streak_policy,
    }


async def check_recent_streak(session: AsyncSession, lookback: int = 5) -> dict:
    """
    Deteksi losing streak mendadak (misal: 5 kerugian beruntun memicu alarm).
    Lebih sensitif mendeteksi kelemahan dibanding metrik all-time win rate.
    """
    recent = (
        (
            await session.execute(
                select(PaperTradeRecord)
                .where(PaperTradeRecord.status == "closed")
                .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
                .order_by(PaperTradeRecord.closed_at.desc())
                .limit(lookback)
            )
        )
        .scalars()
        .all()
    )

    if len(recent) < lookback:
        return {"streak_data": "insufficient", "count": len(recent)}

    losses = [r for r in recent if r.exit_reason == "sl_hit"]
    wins = [r for r in recent if r.exit_reason == "tp_hit"]
    recent_wr = len(wins) / len(recent) * 100

    result = {
        "lookback": lookback,
        "recent_win_rate": recent_wr,
        "recent_wins": len(wins),
        "recent_losses": len(losses),
        "alert_triggered": len(losses) >= lookback - 1,  # 4 dari 5 terakhir loss
    }

    if result["alert_triggered"]:
        msg = (
            f"[KRITIS] <b>LOSING STREAK DETECTED</b>\n"
            f"Last {lookback} trades: {len(losses)} losses, {len(wins)} wins\n"
            f"Recent win rate: {recent_wr:.0f}%\n"
            f"Consider pausing and reviewing recent analyses."
        )
        try:
            from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

            await AgentNotifier().send_critical(msg)
        except Exception:
            pass

    return result
