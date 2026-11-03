"""
File: src/monika/application/agent/monitors/drawdown_monitor.py
Floating drawdown monitoring with hysteresis and auto-kill-switch.
"""

import asyncio
import json as _json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("TradingAgent.DrawdownMonitor")


async def run_floating_drawdown_monitor(agent: Any) -> None:
    """
    Monitor floating drawdown. Uses hysteresis (2 consecutive breaches)
    before triggering kill switch to avoid false positives from price spikes.
    """
    consecutive_breach_count = 0
    BREACH_THRESHOLD = 2
    cached_start_balance_date: Optional[str] = None
    cached_start_balance_val: Optional[float] = None
    last_saved_balance: Optional[float] = None
    last_saved_equity: Optional[float] = None
    last_saved_date: Optional[str] = None
    last_saved_mono: float = 0.0

    if hasattr(agent, "_recovery_complete") and agent._recovery_complete:
        try:
            await asyncio.wait_for(agent._recovery_complete.wait(), timeout=180.0)
        except asyncio.TimeoutError:
            pass

    while not agent.shutdown_event.is_set():
        try:
            try:
                if agent.execution_service:
                    account_info = None
                    if getattr(agent.execution_service, "broker_adapter", None):
                        try:
                            account_info = await agent.execution_service.broker_adapter.get_account_info()
                        except Exception:
                            pass
                    if not account_info and getattr(agent.execution_service, "mt5", None):
                        if await agent.execution_service.mt5.is_connected():
                            account_info = await agent.execution_service.mt5.get_account_info()
                    if account_info:
                        raw_balance = account_info.get("balance")
                        raw_equity = account_info.get("equity")
                        if raw_balance is None or raw_equity is None:
                            logger.error(
                                f"[DrawdownMonitor] Account balance or equity missing (balance={raw_balance}, equity={raw_equity}). Skipping cycle (fail-closed)."
                            )
                            continue
                        try:
                            balance = float(raw_balance)
                            equity = float(raw_equity)
                        except (ValueError, TypeError) as conv_err:
                            logger.error(f"[DrawdownMonitor] Unparseable account numbers: {conv_err}. Skipping cycle.")
                            continue
                        if balance <= 0:
                            logger.error(f"[DrawdownMonitor] Non-positive account balance ({balance}). Skipping cycle.")
                            continue
                        try:
                            from sqlalchemy import select as _sel

                            from monika.infrastructure.database.db import get_session
                            from monika.infrastructure.database.models import SystemConfig
                            from monika.infrastructure.database.safe_ops import atomic_upsert_system_config, safe_commit

                            now_utc = datetime.now(timezone.utc)
                            today_str = now_utc.strftime("%Y-%m-%d")
                            balance_key = f"mt5_balance_start_{today_str}"

                            if cached_start_balance_date == today_str and cached_start_balance_val is not None:
                                starting_balance = cached_start_balance_val
                            else:
                                async with get_session() as cfg_session:
                                    balance_cfg = (
                                        await cfg_session.execute(
                                            _sel(SystemConfig).where(SystemConfig.key == balance_key)
                                        )
                                    ).scalar_one_or_none()
                                    if not balance_cfg or balance_cfg.value is None:
                                        await atomic_upsert_system_config(
                                            cfg_session, key=balance_key, value=str(balance)
                                        )
                                        await safe_commit(cfg_session, label="drawdown_monitor_start_balance")
                                        starting_balance = balance
                                    else:
                                        starting_balance = float(balance_cfg.value)
                                cached_start_balance_date = today_str
                                cached_start_balance_val = starting_balance

                            daily_pnl = equity - starting_balance
                            daily_pnl_pct = round(daily_pnl / starting_balance * 100, 4) if starting_balance > 0 else 0
                            real_state = {
                                "balance": balance,
                                "equity": equity,
                                "floating_pnl": equity - balance,
                                "floating_pnl_pct": round((equity - balance) / balance * 100, 4) if balance > 0 else 0,
                                "date": today_str,
                                "updated_at": now_utc.isoformat(),
                                "starting_balance": starting_balance,
                                "daily_pnl": daily_pnl,
                                "daily_pnl_pct": daily_pnl_pct,
                            }

                            now_mono = time.monotonic()
                            needs_save = False
                            if last_saved_date != today_str:
                                needs_save = True
                            elif last_saved_balance is None or last_saved_equity is None:
                                needs_save = True
                            elif abs(balance - last_saved_balance) > 0.01:
                                needs_save = True
                            elif abs(equity - last_saved_equity) / (last_saved_equity or 1.0) >= 0.0005:
                                needs_save = True
                            elif (now_mono - last_saved_mono) >= 900.0:
                                needs_save = True

                            if needs_save:
                                from monika.core.serialization import fast_json

                                state_key = "mt5_real_risk_state"
                                state_json = fast_json.dumps(real_state)
                                async with get_session() as cfg_session:
                                    await atomic_upsert_system_config(cfg_session, key=state_key, value=state_json)
                                    await safe_commit(cfg_session, label="drawdown_monitor_risk_state")
                                last_saved_balance = balance
                                last_saved_equity = equity
                                last_saved_date = today_str
                                last_saved_mono = now_mono
                        except Exception as e:
                            logger.debug(f"Real risk state write failed (non-fatal): {e}")

                        # Drawdown check with hysteresis
                        if balance <= 0 or equity <= 0:
                            consecutive_breach_count += 1
                            logger.critical(
                                f"Account liquidation detected (balance: {balance}, equity: {equity})! "
                                f"Breach count: {consecutive_breach_count}/{BREACH_THRESHOLD}"
                            )
                            if consecutive_breach_count >= BREACH_THRESHOLD:
                                await agent.execution_service.kill_switch(
                                    reason=f"Account balance/equity liquidated: balance={balance}, equity={equity}"
                                )
                                consecutive_breach_count = 0
                        elif equity < balance and balance > 0:
                            drawdown_pct = (balance - equity) / balance * 100
                            risk_cfg = agent.settings.get("trading", {}).get("risk", {})
                            max_dd = risk_cfg.get("max_daily_drawdown_percent", 4.0)
                            if drawdown_pct >= max_dd:
                                consecutive_breach_count += 1
                                logger.warning(
                                    f"Floating drawdown {drawdown_pct:.2f}% >= limit {max_dd}%. "
                                    f"Breach count: {consecutive_breach_count}/{BREACH_THRESHOLD}"
                                )
                                if consecutive_breach_count >= BREACH_THRESHOLD:
                                    logger.critical(
                                        f"Floating drawdown {drawdown_pct:.2f}% confirmed over "
                                        f"{BREACH_THRESHOLD} consecutive checks. Triggering KILL SWITCH!"
                                    )
                                    await agent.execution_service.kill_switch(
                                        reason=f"Sustained floating drawdown exceeded limit: {drawdown_pct:.2f}% for {BREACH_THRESHOLD} consecutive minutes"
                                    )
                                    consecutive_breach_count = 0
                            else:
                                if consecutive_breach_count > 0:
                                    logger.info(
                                        f"Floating drawdown recovered to {drawdown_pct:.2f}%. Resetting breach counter."
                                    )
                                consecutive_breach_count = 0
                        else:
                            consecutive_breach_count = 0
                    else:
                        consecutive_breach_count = 0
            except Exception as e:
                logger.error(f"Floating drawdown monitor error: {e}")
                consecutive_breach_count = 0
        finally:
            try:
                await asyncio.wait_for(agent.shutdown_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass
