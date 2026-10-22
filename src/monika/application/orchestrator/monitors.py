# ==============================================================================
# File: application/orchestrator/monitors.py
# ==============================================================================

"""
Background monitoring and worker loop mixin for TradingAgent.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import os
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional

if TYPE_CHECKING:
    from monika.application.execution.execution_service import ExecutionService
    from monika.application.scheduler.flash_crash_detector import FlashCrashDetector
    from monika.application.scheduler.graph_cycle_scheduler import GraphCycleScheduler
    from monika.application.scheduler.market_data_scheduler import MarketDataScheduler
    from monika.application.scheduler.order_reconciler import OrderReconciler
    from monika.application.scheduler.position_guardian import PositionGuardian
    from monika.infrastructure.brokers.mt5_client import MT5Client

logger = logging.getLogger("TradingAgent.Main")


class AgentMonitorsMixin:
    """Mixin providing background worker loops and system health monitors."""

    settings: dict[str, Any]
    shutdown_event: asyncio.Event
    _recovery_complete: asyncio.Event
    mt5_client: Optional[MT5Client]
    mt5_health_checker: Optional[Any]
    execution_service: Optional[ExecutionService]
    cycle_scheduler: Optional[GraphCycleScheduler]
    order_reconciler: Optional[OrderReconciler]
    flash_crash_detector: Optional[FlashCrashDetector]
    position_guardian: Optional[PositionGuardian]
    market_data_scheduler: Optional[MarketDataScheduler]
    risk_parameter_reloader: Optional[Any]
    container: Optional[Any]
    publish_tick: Callable[..., Coroutine[Any, Any, None]]

    async def _run_tick_stream_loop(self) -> None:
        """
        Sub-second / low-latency event-driven tick stream publisher.
        Periodically samples live MT5 quotes and broadcasts TickPriceEvents to EventBus subscribers.
        """
        interval = float(self.settings.get("trading", {}).get("schedule", {}).get("tick_stream_interval_seconds", 5.0))
        symbols = self.settings.get("trading", {}).get(
            "asset_universe",
            ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "BTCUSD", "XTIUSD", "XBRUSD"],
        )
        logger.info(f"TickStream loop started (interval: {interval}s, symbols: {len(symbols)})")

        while not self.shutdown_event.is_set():
            try:
                if self.mt5_client and await self.mt5_client.is_connected():

                    async def _sample_and_publish(sym: str) -> None:
                        if not self.mt5_client:
                            return
                        try:
                            quote = await self.mt5_client.get_current_price(sym)
                            if quote and isinstance(quote, dict):
                                bid = float(quote.get("bid", 0.0) or 0.0)
                                ask = float(quote.get("ask", 0.0) or 0.0)
                                last = float(quote.get("last", 0.0) or 0.0)
                                if bid > 0 or ask > 0:
                                    await self.publish_tick(
                                        symbol=sym,
                                        bid=bid,
                                        ask=ask,
                                        last=last,
                                        spread=round(ask - bid, 5) if ask > bid else 0.0,
                                    )
                        except Exception as e:
                            logger.debug(f"TickStream quote error for {sym}: {e}")

                    await asyncio.gather(*[_sample_and_publish(s) for s in symbols])
            except Exception as e:
                logger.debug(f"TickStream loop error: {e}")

            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _run_flash_crash_detector(self) -> None:
        """Dedicated loop to monitor flash crashes and extreme volatility spikes."""
        from monika.infrastructure.database.db import get_session

        interval = int(
            self.settings.get("trading", {}).get("risk", {}).get("flash_crash", {}).get("check_interval_seconds", 30)
        )
        logger.info(f"Flash Crash detector loop started (interval: {interval}s)")
        if hasattr(self, "_recovery_complete") and self._recovery_complete:
            try:
                await asyncio.wait_for(self._recovery_complete.wait(), timeout=180.0)
            except asyncio.TimeoutError:
                pass
        while not self.shutdown_event.is_set():
            try:
                async with get_session() as session:
                    if self.flash_crash_detector:
                        await self.flash_crash_detector.check(session)
            except Exception as e:
                logger.error(f"Flash crash detector loop error: {e}")
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _run_whatif_resolver(self) -> None:
        """Dedicated loop to resolve paper what-ifs."""
        check_interval_seconds = 3600  # Every 1 hour
        logger.info("What-If resolver started (interval: 1h)")

        from monika.application.analysis.memory.outcome_linker import OutcomeLinker
        from monika.infrastructure.database.db import get_session

        linker = OutcomeLinker()

        while not self.shutdown_event.is_set():
            try:
                async with get_session() as session:
                    await linker.process_paper_whatifs(session)
            except Exception as e:
                logger.error(f"Error in What-If resolver loop: {e}")

            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=check_interval_seconds)
                break
            except asyncio.TimeoutError:
                pass

    async def _run_paper_trade_monitor(self) -> None:
        """Dedicated loop to monitor and close paper trades based on price action."""
        from monika.application.agent.monitors import run_paper_trade_monitor

        await run_paper_trade_monitor(self)

    async def _run_micro_playbook_compiler_loop(self) -> None:
        """
        Autonomous micro-playbook compilation loop.
        Evaluates trade memories and promotes high-performing strategies (>=3 consecutive wins or >=65% win rate).
        """
        from monika.application.analysis.memory.skill_evolution import MicroPlaybookCompiler
        from monika.infrastructure.database.db import get_session

        compiler = MicroPlaybookCompiler(self.settings)
        check_interval_seconds = 21600  # Run every 6 hours
        logger.info("Micro-playbook compiler loop started (interval: 6h)")
        while not self.shutdown_event.is_set():
            try:
                async with get_session() as session:
                    promoted = await compiler.evaluate_and_compile(session, settings=self.settings)
                    if promoted:
                        logger.info(
                            f"[MicroPlaybookCompiler] Promoted {len(promoted)} autonomous micro-playbooks: {promoted}"
                        )
            except Exception as e:
                logger.warning(f"[MicroPlaybookCompiler] Loop iteration error (non-fatal): {e}")
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=check_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def _run_skill_curator_loop(self) -> None:
        """
        Autonomous background skill curator loop (MEDIUM-2).
        Periodically audits and archives stale playbooks and deduplicates redundant conditions (every 24 hours).
        """
        from monika.application.analysis.memory.skill_curator import SkillCurator
        from monika.infrastructure.database.db import get_session

        curator = SkillCurator(self.settings)
        check_interval_seconds = 86400  # Run every 24 hours
        logger.info("Skill curator loop started (interval: 24h)")
        # Allow daemon startup sequence and trading monitors to fully stabilize before first curation pass
        try:
            await asyncio.wait_for(self.shutdown_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            pass

        while not self.shutdown_event.is_set():
            try:
                async with get_session() as session:
                    res = await curator.run_once(session)
                    logger.info(f"[SkillCurator] Completed cycle: {res}")
            except Exception as e:
                logger.warning(f"[SkillCurator] Loop iteration error (non-fatal): {e}")
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=check_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def _run_dashboard(self) -> None:
        """Run the FastAPI dashboard server as an asyncio task with bind-retry resilience."""
        dashboard_runner = self.container.get("dashboard_runner") if self.container else None
        if dashboard_runner:
            await dashboard_runner(self)
            return

        try:
            import importlib

            dash_api = importlib.import_module("monika.interfaces.dashboard.api")
            set_dashboard_dependencies = getattr(dash_api, "set_dashboard_dependencies")
            run_dashboard_async = getattr(dash_api, "run_dashboard_async")
        except Exception as imp_err:
            logger.debug(f"Dashboard interface resolution note: {imp_err}")
            return

        rg = getattr(self.execution_service, "risk_gate", None)
        reloader = getattr(self, "risk_parameter_reloader", None)
        set_dashboard_dependencies(
            cycle_scheduler=self.cycle_scheduler,
            execution_service=self.execution_service,
            mt5_client=self.mt5_client,
            settings=self.settings,
            agent=self,
            risk_gate=rg,
            risk_parameter_reloader=reloader,
        )
        host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
        port = int(os.getenv("DASHBOARD_PORT", 8000))
        logger.info(f"Dashboard API starting on http://{host}:{port}")
        while not self.shutdown_event.is_set():
            try:
                await run_dashboard_async(port=port, shutdown_event=self.shutdown_event)
                if self.shutdown_event.is_set():
                    break
                await asyncio.sleep(2)
            except (Exception, SystemExit) as e:
                if self.shutdown_event.is_set():
                    break
                logger.warning(f"Dashboard API server error on port {port}: {e}. Retrying in 5s...")
                await asyncio.sleep(5)

    async def _run_position_sync_loop(self) -> None:
        """
        Periodically sync MT5 positions to DB.
        Runs every 60 seconds — keeps DB positions up-to-date with actual MT5 state.
        """
        if self.order_reconciler and getattr(self.order_reconciler, "is_running", False):
            logger.info("[PositionSync] OrderReconciler is active; skipping standalone PositionSync loop.")
            return

        sync_interval = 60
        while not self.shutdown_event.is_set():
            try:
                if self.execution_service:
                    await self.execution_service.sync_positions()
            except Exception as e:
                logger.debug(f"Position sync error (non-fatal): {e}")
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=sync_interval)
            except asyncio.TimeoutError:
                pass

    async def _run_scraper_loop(self) -> None:
        from monika.application.agent.monitors import run_scraper_loop

        await run_scraper_loop(self)

    async def _run_risk_parameter_reloader(self) -> None:
        if hasattr(self, "risk_parameter_reloader") and self.risk_parameter_reloader:
            await self.risk_parameter_reloader.watch_and_reload(self.shutdown_event)

    async def _run_mt5_health_monitor(self) -> None:
        """Monitor MT5 connection health and auto-heal market data on reconnect."""
        consecutive_failures = 0
        max_failures_before_alert = 1
        was_disconnected = False

        while not self.shutdown_event.is_set():
            await asyncio.sleep(60)  # Check every 60s for faster reconnection recovery
            try:
                if self.mt5_health_checker is not None:
                    is_conn = await self.mt5_health_checker.is_healthy()
                elif (
                    self.execution_service
                    and hasattr(self.execution_service, "broker_adapter")
                    and self.execution_service.broker_adapter
                ):
                    adapter = self.execution_service.broker_adapter
                    if hasattr(adapter, "ensure_connected"):
                        is_conn = await adapter.ensure_connected()
                    elif hasattr(adapter, "is_connected"):
                        is_conn = await adapter.is_connected()
                    else:
                        is_conn = True
                elif self.mt5_client:
                    is_conn = await self.mt5_client.is_connected()
                else:
                    is_conn = True
                if not is_conn:
                    consecutive_failures += 1
                    was_disconnected = True
                    logger.warning(f"MT5 health check failed ({consecutive_failures}/{max_failures_before_alert})")
                    if consecutive_failures == max_failures_before_alert:
                        if self.mt5_health_checker is not None:
                            self.mt5_health_checker.record_failure()
                        from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

                        await AgentNotifier().send_critical(
                            f"[PLUGIN] <b>MT5 Connection Lost</b>\n"
                            f"MT5 has been disconnected for ~{consecutive_failures} minutes.\n"
                            f"[PERINGATAN] EA dead-man switch may trigger in ~2 minutes if not reconnected!\n"
                            f"Price data is stale. Analysis quality is degraded.\n"
                            f"Please check MT5 terminal immediately!"
                        )
                else:
                    if was_disconnected:
                        # Auto-Healing: Reconnection detected!
                        logger.info(
                            "[MT5HealthMonitor] MT5 reconnected! Triggering instant auto-healing market data sync..."
                        )
                        was_disconnected = False
                        if self.mt5_health_checker is not None:
                            self.mt5_health_checker.record_success()
                        if self.market_data_scheduler:
                            asyncio.create_task(self.market_data_scheduler.sync_now())
                        try:
                            from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

                            await AgentNotifier().send_info(
                                "[OK] <b>MT5 Reconnected</b> — Market data auto-healing sync dispatched."
                            )
                        except Exception:
                            pass
                    consecutive_failures = 0  # Reset on successful connection
            except Exception as e:
                logger.debug(f"MT5 health monitor error (non-fatal): {e}")

    async def _run_friday_close_monitor(self) -> None:
        """Check setiap 30 menit apakah mendekati Friday close."""
        if hasattr(self, "_recovery_complete") and self._recovery_complete:
            try:
                await asyncio.wait_for(self._recovery_complete.wait(), timeout=180.0)
            except asyncio.TimeoutError:
                pass
        while not self.shutdown_event.is_set():
            now = datetime.now(timezone.utc)
            if now.weekday() == 4 and 20 <= now.hour <= 21:
                if self.position_guardian:
                    await self.position_guardian.check_friday_close_protection()
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=1800)  # 30 menit
            except asyncio.TimeoutError:
                pass

    async def _run_position_guardian_loop(self) -> None:
        """Independent position guardian loop (default 60s, configurable via trading.position_guardian_interval_seconds)."""
        if hasattr(self, "_recovery_complete") and self._recovery_complete:
            try:
                await asyncio.wait_for(self._recovery_complete.wait(), timeout=180.0)
            except asyncio.TimeoutError:
                pass
        guardian_cfg = self.settings.get("trading", {}).get("position_guardian", {})
        interval = int(
            guardian_cfg.get("check_interval_seconds")
            or self.settings.get("trading", {}).get("position_guardian_interval_seconds", 60)
        )
        while not self.shutdown_event.is_set():
            try:
                if self.position_guardian:
                    await self.position_guardian.check_and_protect()
            except Exception as e:
                logger.debug(f"PositionGuardian check failed (non-fatal): {e}")
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _run_floating_drawdown_monitor(self) -> None:
        """Monitor floating drawdown."""
        from monika.application.agent.monitors import run_floating_drawdown_monitor

        await run_floating_drawdown_monitor(self)

    async def _run_margin_monitor(self) -> None:
        """Monitor account margin level and emit warning when critical (< 200%)."""
        from monika.application.agent.monitors import run_margin_monitor

        await run_margin_monitor(self)

    async def _run_db_health_check(self) -> None:
        """Monitor Database connection pool health."""
        from monika.application.agent.monitors import run_db_health_check

        await run_db_health_check(self)


__all__ = ["AgentMonitorsMixin"]
