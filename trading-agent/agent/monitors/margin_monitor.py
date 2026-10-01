"""
File: trading-agent/agent/monitors/margin_monitor.py
Margin level watcher and threshold alerting monitor (MarginGuardian).
"""

import asyncio
import logging
from typing import Any, Optional
from utils.infra.notifier import AgentNotifier

logger = logging.getLogger("TradingAgent.MarginMonitor")


async def run_margin_monitor(agent: Any, alert_threshold_pct: float = 200.0, poll_interval: float = 30.0) -> None:
    """
    Monitors account margin level periodically.
    Emits warning notifications via AgentNotifier when margin level falls below alert threshold.
    """
    notifier = AgentNotifier()
    last_alert_time: float = 0.0
    ALERT_COOLDOWN_SECONDS: float = 300.0  # Alert max once every 5 minutes

    if hasattr(agent, "_recovery_complete") and agent._recovery_complete:
        try:
            await asyncio.wait_for(agent._recovery_complete.wait(), timeout=180.0)
        except asyncio.TimeoutError:
            pass

    logger.info(f"[MarginGuardian] Started monitoring margin level (Threshold: {alert_threshold_pct}%).")

    while not agent.shutdown_event.is_set():
        try:
            account_info: Optional[dict] = None
            if getattr(agent, "execution_service", None):
                if getattr(agent.execution_service, "broker_adapter", None):
                    try:
                        account_info = await agent.execution_service.broker_adapter.get_account_info()
                    except Exception:
                        pass
                if not account_info and getattr(agent.execution_service, "mt5", None):
                    try:
                        if await agent.execution_service.mt5.is_connected():
                            account_info = await agent.execution_service.mt5.get_account_info()
                    except Exception:
                        pass

            if account_info:
                margin_level = account_info.get("margin_level")
                margin = account_info.get("margin", 0.0)
                equity = account_info.get("equity", 0.0)

                if margin_level is not None and margin and float(margin) > 0:
                    ml_val = float(margin_level)
                    if ml_val > 0 and ml_val < alert_threshold_pct:
                        now_ts = asyncio.get_event_loop().time()
                        if now_ts - last_alert_time >= ALERT_COOLDOWN_SECONDS:
                            last_alert_time = now_ts
                            msg = (
                                f"[DARURAT] **MARGIN LEVEL ALERT (MarginGuardian)**\n\n"
                                f"[PERINGATAN] Tingkat margin akun Anda kritis: `{ml_val:.1f}%` (di bawah batas `{alert_threshold_pct:.0f}%`)!\n"
                                f"- **Equity**: `${float(equity):,.2f}`\n"
                                f"- **Margin Terpakai**: `${float(margin):,.2f}`\n\n"
                                f"[CATATAN] *Saran*: Kurangi posisi terbuka atau tambahkan margin untuk menghindari Stop-Out."
                            )
                            logger.warning(f"[MarginGuardian] Critical margin level: {ml_val:.1f}% (< {alert_threshold_pct}%)")
                            try:
                                await notifier.send_warning(msg)
                            except Exception as notif_err:
                                logger.debug(f"[MarginGuardian] Failed sending notifier warning: {notif_err}")

        except Exception as e:
            logger.debug(f"[MarginGuardian] Error checking margin level: {e}")

        try:
            await asyncio.wait_for(agent.shutdown_event.wait(), timeout=poll_interval)
        except asyncio.TimeoutError:
            pass
