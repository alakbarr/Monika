"""
File: trading-agent/agent/monitors/drawdown_monitor.py
Floating drawdown monitoring with hysteresis and auto-kill-switch.
"""

import asyncio
import json as _json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("TradingAgent.DrawdownMonitor")


async def run_floating_drawdown_monitor(agent: Any) -> None:
    """
    Monitor floating drawdown. Uses hysteresis (2 consecutive breaches)
    before triggering kill switch to avoid false positives from price spikes.
    """
    consecutive_breach_count = 0
    BREACH_THRESHOLD = 2

    if hasattr(agent, "_recovery_complete") and agent._recovery_complete:
        try:
            await asyncio.wait_for(agent._recovery_complete.wait(), timeout=180.0)
        except asyncio.TimeoutError:
            pass

    while not agent.shutdown_event.is_set():
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
                        fallback_bal = float(getattr(agent, "settings", {}).get("paper_trading", {}).get("initial_balance", 10000.0))
                        if raw_balance is not None and float(raw_balance) > 0:
                            balance = float(raw_balance)
                        else:
                            logger.warning(f"Account balance missing or non-positive ({raw_balance}); falling back to initial_balance {fallback_bal}")
                            balance = fallback_bal

                        if raw_equity is not None and float(raw_equity) > 0:
                            equity = float(raw_equity)
                        else:
                            equity = balance
                        try:
                            from database.db import get_session
                            from database.models import SystemConfig
                            from sqlalchemy import select as _sel

                            now_utc = datetime.now(timezone.utc)
                            today_str = now_utc.strftime("%Y-%m-%d")
                            real_state = {
                                "balance": balance,
                                "equity": equity,
                                "floating_pnl": equity - balance,
                                "floating_pnl_pct": round((equity - balance) / balance * 100, 4) if balance > 0 else 0,
                                "date": today_str,
                                "updated_at": now_utc.isoformat(),
                            }
                            async with get_session() as cfg_session:
                                balance_key = f"mt5_balance_start_{today_str}"
                                balance_cfg = (
                                    await cfg_session.execute(_sel(SystemConfig).where(SystemConfig.key == balance_key))
                                ).scalar_one_or_none()
                                if not balance_cfg or balance_cfg.value is None:
                                    cfg_session.add(SystemConfig(key=balance_key, value=str(balance)))
                                    await cfg_session.commit()
                                    starting_balance = balance
                                else:
                                    starting_balance = float(balance_cfg.value)

                                daily_pnl = equity - starting_balance
                                daily_pnl_pct = round(daily_pnl / starting_balance * 100, 4) if starting_balance > 0 else 0
                                real_state["starting_balance"] = starting_balance
                                real_state["daily_pnl"] = daily_pnl
                                real_state["daily_pnl_pct"] = daily_pnl_pct

                                state_key = "mt5_real_risk_state"
                                state_cfg = (
                                    await cfg_session.execute(_sel(SystemConfig).where(SystemConfig.key == state_key))
                                ).scalar_one_or_none()
                                state_json = _json.dumps(real_state)
                                if state_cfg:
                                    state_cfg.value = state_json
                                else:
                                    cfg_session.add(SystemConfig(key=state_key, value=state_json))
                                await cfg_session.commit()
                        except Exception as e:
                            logger.debug(f"Real risk state write failed (non-fatal): {e}")

                        # Drawdown check with hysteresis
                        if equity < balance and balance > 0:
                            drawdown_pct = (balance - equity) / balance * 100
                            risk_cfg = agent.settings.get("trading", {}).get("risk", {})
                            max_dd = risk_cfg.get("max_daily_drawdown_percent", 3.0)
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
                                    logger.info(f"Floating drawdown recovered to {drawdown_pct:.2f}%. Resetting breach counter.")
                                consecutive_breach_count = 0
                        else:
                            consecutive_breach_count = 0
        except Exception as e:
            logger.error(f"Floating drawdown monitor error: {e}")
            consecutive_breach_count = 0

        try:
            await asyncio.wait_for(agent.shutdown_event.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass
