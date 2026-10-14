# ==============================================================================
# File: application/orchestrator/lifecycle.py
# ==============================================================================

"""
Process lifecycle, signals, startup, and graceful shutdown mixin for TradingAgent.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import os
import signal
import sys
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional

import monika.core.primitives.clock as clock
from monika.application.agent.task_registry import mark_clean_shutdown
from monika.infrastructure.database.db import close_db

if TYPE_CHECKING:
    from monika.application.analysis.stages.fundamental_stage import FundamentalStage
    from monika.application.analysis.stages.per_asset_stage import PerAssetStage
    from monika.application.execution.execution_service import ExecutionService
    from monika.application.scheduler.active_calendar_poller import ActiveCalendarPoller
    from monika.application.scheduler.alpha_discovery_scheduler import AlphaDiscoveryScheduler
    from monika.application.scheduler.digest_slice_scheduler import DigestSliceScheduler
    from monika.application.scheduler.edge_strategy_runner import EdgeStrategyRunner
    from monika.application.scheduler.flash_crash_detector import FlashCrashDetector
    from monika.application.scheduler.graph_cycle_scheduler import GraphCycleScheduler
    from monika.application.scheduler.macro_data_scheduler import MacroDataScheduler
    from monika.application.scheduler.market_data_scheduler import MarketDataScheduler
    from monika.application.scheduler.news_watcher import NewsWatcher
    from monika.application.scheduler.order_reconciler import OrderReconciler
    from monika.application.scheduler.position_exit_reviewer import PositionExitReviewer
    from monika.application.scheduler.position_guardian import PositionGuardian
    from monika.application.scheduler.position_supervisor import PositionSupervisor
    from monika.application.scheduler.post_release_analyzer import PostReleaseAnalyzer
    from monika.application.scheduler.strategy_synthesis_scheduler import StrategySynthesisScheduler
    from monika.application.scheduler.trailing_stop_manager import TrailingStopManager
    from monika.application.scheduler.trigger_checker import TriggerChecker
    from monika.core.telemetry.activity_logger import ActivityLogger
    from monika.infrastructure.brokers.ea_bridge.heartbeat_writer import HeartbeatManager
    from monika.infrastructure.brokers.ea_bridge.watchdog import EAWatchdog
    from monika.infrastructure.brokers.mt5_client import MT5Client
    from monika.infrastructure.infra.notifier import AgentNotifier

logger = logging.getLogger("TradingAgent.Main")

BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║             MONIKA — MT5 TRADING AGENT  v1.0.0               ║
╚══════════════════════════════════════════════════════════════╝
"""


class AgentLifecycleMixin:
    """Mixin responsible for process initialization, signal handling, and shutdown sequences."""

    settings: dict[str, Any]
    dry_run: bool
    shutdown_event: asyncio.Event
    _recovery_complete: asyncio.Event
    _activity_log: ActivityLogger
    event_bus: Optional[Any]
    task_registry: Optional[Any]
    mt5_client: Optional[MT5Client]
    mt5_health_checker: Optional[Any]
    market_data_scheduler: Optional[MarketDataScheduler]
    macro_data_scheduler: Optional[MacroDataScheduler]
    execution_service: Optional[ExecutionService]
    heartbeat_mgr: Optional[HeartbeatManager]
    ea_watchdog: Optional[EAWatchdog]
    edge_strategy_runner: Optional[EdgeStrategyRunner]
    fundamental_stage: Optional[FundamentalStage]
    per_asset_stage: Optional[PerAssetStage]
    position_exit_reviewer: Optional[PositionExitReviewer]
    position_guardian: Optional[PositionGuardian]
    order_reconciler: Optional[OrderReconciler]
    active_calendar_poller: Optional[ActiveCalendarPoller]
    trailing_stop_manager: Optional[TrailingStopManager]
    position_supervisor: Optional[PositionSupervisor]
    digest_slice_scheduler: Optional[DigestSliceScheduler]
    cycle_scheduler: Optional[GraphCycleScheduler]
    turn_lease_manager: Optional[Any]
    news_watcher: Optional[NewsWatcher]
    post_release_analyzer: Optional[PostReleaseAnalyzer]
    trigger_checker: Optional[TriggerChecker]
    telegram_bot: Optional[Any]
    notifier: Optional[AgentNotifier]
    flash_crash_detector: Optional[FlashCrashDetector]
    risk_parameter_reloader: Optional[Any]
    config_manager: Optional[Any]
    alpha_discovery_scheduler: Optional[AlphaDiscoveryScheduler]
    strategy_synthesis_scheduler: Optional[StrategySynthesisScheduler]
    background_review_engine: Optional[Any]
    playbook_curator: Optional[Any]
    plugin_engine: Optional[Any]
    universal_cron: Optional[Any]
    guardian_supervisor: Optional[Any]
    _active_scraper_runner: Optional[Any]
    _recovery_task: Optional[asyncio.Task[Any]]
    _tg_task: Optional[asyncio.Task[Any]]
    _background_tasks: set[asyncio.Task[Any]]
    _tasks: list[asyncio.Task[Any]]
    _init_components: Callable[[], None]
    _post_restart_recovery: Callable[[], Coroutine[Any, Any, None]]
    _run_dashboard: Callable[[], Coroutine[Any, Any, None]]
    _run_position_sync_loop: Callable[[], Coroutine[Any, Any, None]]
    _run_mt5_health_monitor: Callable[[], Coroutine[Any, Any, None]]
    _run_friday_close_monitor: Callable[[], Coroutine[Any, Any, None]]
    _run_position_guardian_loop: Callable[[], Coroutine[Any, Any, None]]
    _run_flash_crash_detector: Callable[[], Coroutine[Any, Any, None]]
    _run_tick_stream_loop: Callable[[], Coroutine[Any, Any, None]]
    _run_floating_drawdown_monitor: Callable[[], Coroutine[Any, Any, None]]
    _run_margin_monitor: Callable[[], Coroutine[Any, Any, None]]
    _run_paper_trade_monitor: Callable[[], Coroutine[Any, Any, None]]
    _run_db_health_check: Callable[[], Coroutine[Any, Any, None]]
    _run_scraper_loop: Callable[[], Coroutine[Any, Any, None]]
    _run_whatif_resolver: Callable[[], Coroutine[Any, Any, None]]
    _run_micro_playbook_compiler_loop: Callable[[], Coroutine[Any, Any, None]]
    _run_skill_curator_loop: Callable[[], Coroutine[Any, Any, None]]
    _run_risk_parameter_reloader: Callable[[], Coroutine[Any, Any, None]]
    _create_background_task: Callable[..., asyncio.Task[Any]]

    def _register_signals(self) -> None:
        """Register OS signal handlers for graceful shutdown."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        def _signal_handler(sig_name: str):
            logger.info(f"Signal {sig_name} received — initiating graceful shutdown...")
            mark_clean_shutdown()
            try:
                if loop and not loop.is_closed():
                    loop.call_soon_threadsafe(self.shutdown_event.set)
                else:
                    self.shutdown_event.set()
            except RuntimeError:
                self.shutdown_event.set()

        # SIGINT (Ctrl+C) and SIGTERM (systemd/docker stop)
        for sig in (signal.SIGINT, signal.SIGTERM):
            if loop is not None:
                try:
                    loop.add_signal_handler(sig, lambda s=sig.name: _signal_handler(s))
                except NotImplementedError, RuntimeError:
                    # Windows: add_signal_handler not supported for all signals
                    signal.signal(sig, lambda s, f, n=sig.name: _signal_handler(n))
            else:
                signal.signal(sig, lambda s, f, n=sig.name: _signal_handler(n))

        # SIGHUP (systemd ExecReload / config reload, Unix only)
        if hasattr(signal, "SIGHUP"):

            def _sighup_handler():
                logger.info("SIGHUP received — reloading configuration...")
                try:
                    from monika.core.config.settings import load_all_config

                    new_settings = load_all_config()
                    self.settings.clear()
                    self.settings.update(new_settings)
                    if hasattr(self, "risk_parameter_reloader") and self.risk_parameter_reloader:
                        self.risk_parameter_reloader.check_and_reload()
                    rg = getattr(getattr(self, "execution_service", None), "risk_gate", None)
                    if rg and hasattr(rg, "update_parameters"):
                        rg.update_parameters(self.settings)
                    logger.info("Configuration successfully reloaded on SIGHUP.")
                except Exception as ex:
                    logger.error(f"Failed to reload configuration on SIGHUP: {ex}")

            sighup = getattr(signal, "SIGHUP", None)
            if sighup is not None:
                if loop is not None:
                    try:
                        loop.add_signal_handler(sighup, _sighup_handler)
                    except NotImplementedError, RuntimeError:
                        signal.signal(sighup, lambda s, f: _sighup_handler())
                else:
                    signal.signal(sighup, lambda s, f: _sighup_handler())

    async def start(self) -> None:
        """
        Full startup sequence — blocks until shutdown.
        """
        reconfig = getattr(sys.stdout, "reconfigure", None)
        if (
            callable(reconfig)
            and hasattr(sys.stdout, "encoding")
            and sys.stdout.encoding
            and sys.stdout.encoding.lower() != "utf-8"
        ):
            try:
                reconfig(encoding="utf-8")
            except Exception:
                pass

        print(BANNER)
        logger.info("=" * 62)
        logger.info("Monika (MT5 Trading Agent) starting up...")
        logger.info(f"Environment: {self.settings.get('environment', 'development')}")
        logger.info(f"Asset universe: {self.settings.get('trading', {}).get('asset_universe', [])}")
        if self.dry_run:
            logger.info("MODE: DRY RUN (No actual trades will be placed)")
        logger.info("=" * 62)

        # Arm startup watchdog to detect deadlocks during component initialization
        from monika.application.agent.monitors.startup_watchdog import global_startup_watchdog

        global_startup_watchdog.start()

        # Register signal handlers
        self._register_signals()

        # Initialize components
        self._init_components()

        # Connect MT5 / Broker Gateway Adapter
        try:
            from monika.infrastructure.brokers.broker_adapter import MT5LiveAdapter

            custom_adapter = getattr(self.execution_service, "broker_adapter", None) if self.execution_service else None
            if custom_adapter and not isinstance(custom_adapter, MT5LiveAdapter):
                connected = await custom_adapter.ensure_connected()
                if connected:
                    logger.info(f"Broker Adapter ({type(custom_adapter).__name__}) connected successfully")
                else:
                    logger.warning(
                        f"Broker Adapter ({type(custom_adapter).__name__}) connection failed — live execution disabled"
                    )
            elif self.mt5_client:
                connected = await self.mt5_client.connect()
                if connected:
                    logger.info("MT5 connected successfully")
                else:
                    logger.warning("MT5 connection failed — live execution disabled")
        except Exception as e:
            logger.warning(f"MT5/Broker not available: {e}")

        # Start recovery AFTER MT5 connected
        self._recovery_task = asyncio.create_task(self._post_restart_recovery())

        # Write startup event
        await self._activity_log.system(
            f"Agent started. Environment={self.settings.get('environment')} "
            f"Assets={self.settings.get('trading', {}).get('asset_universe', [])}",
            actor="main",
        )

        # Notify Telegram admin
        self._create_background_task(self._send_startup_notification(), name="startup_notification")

        # PR-22: Cold-Start Pre-Flight Verification before enabling schedulers
        try:
            from monika.application.agent.monitors.startup_watchdog import run_cold_start_preflight

            preflight = await run_cold_start_preflight(self)
            logger.info(
                f"[Preflight] Cold-start verification: broker_ping={preflight.get('broker_ping')}, "
                f"positions_reconciled={preflight.get('positions_reconciled')}, "
                f"ready={preflight.get('ready')}"
            )
        except Exception as preflight_err:
            logger.warning(f"[Preflight] Cold-start pre-flight note (non-fatal): {preflight_err}")

        # Launch all concurrent tasks
        logger.info("Launching concurrent tasks...")
        tasks_list: list[asyncio.Task[Any]] = []

        from monika.application.agent.task_registry import _run_with_restart

        def _launch_task(name: str, runner: Callable[..., Any], task_name: str) -> asyncio.Task[Any]:
            t: asyncio.Task[Any]
            if hasattr(self, "task_registry") and self.task_registry:
                try:
                    defn = self.task_registry.register(name, runner, task_id=task_name)
                    t = self.task_registry.create_asyncio_task(defn)
                except Exception as ex:
                    logger.warning(f"Failed to register task {name} in task_registry ({ex}), fallback to direct task.")
                    t = asyncio.create_task(_run_with_restart(name, runner, self.shutdown_event), name=task_name)
            else:
                t = asyncio.create_task(_run_with_restart(name, runner, self.shutdown_event), name=task_name)
            tasks_list.append(t)
            return t

        if hasattr(self, "guardian_supervisor") and self.guardian_supervisor:
            try:
                self.guardian_supervisor.start()
            except Exception as e:
                logger.warning(f"GuardianSupervisor start note: {e}")

        if self.market_data_scheduler and hasattr(self.market_data_scheduler, "start"):
            _launch_task("MarketDataScheduler", self.market_data_scheduler.start, "market_data_scheduler")
        if self.macro_data_scheduler and hasattr(self.macro_data_scheduler, "start"):
            _launch_task("MacroDataScheduler", self.macro_data_scheduler.start, "macro_data_scheduler")
        if self.edge_strategy_runner and hasattr(self.edge_strategy_runner, "start"):
            _launch_task("EdgeStrategyRunner", self.edge_strategy_runner.start, "edge_strategy_runner")
        if self.cycle_scheduler:
            _launch_task("CycleScheduler", self.cycle_scheduler.start, "cycle_scheduler")
            _launch_task(
                "DailyReportScheduler", self.cycle_scheduler.run_scheduled_reports_loop, "daily_report_scheduler"
            )
            _launch_task("SessionTrigger", self.cycle_scheduler.run_session_trigger_loop, "session_trigger")
        if self.news_watcher:
            _launch_task("NewsWatcher", self.news_watcher.start, "news_watcher")
        if self.digest_slice_scheduler and hasattr(self.digest_slice_scheduler, "start"):
            _launch_task("DigestSliceScheduler", self.digest_slice_scheduler.start, "digest_slice_scheduler")
        if self.active_calendar_poller:
            _launch_task("ActiveCalendarPoller", self.active_calendar_poller.start, "active_calendar_poller")
        if self.post_release_analyzer and hasattr(self.post_release_analyzer, "start"):
            _launch_task("PostReleaseAnalyzer", self.post_release_analyzer.start, "post_release_analyzer")
        if self.trigger_checker:
            _launch_task("TriggerChecker", self.trigger_checker.start, "trigger_checker")
        if self.position_exit_reviewer:
            _launch_task("PositionExitReviewer", self.position_exit_reviewer.start, "position_exit_reviewer")
        if self.heartbeat_mgr:
            _launch_task("Heartbeat", self.heartbeat_mgr.run_forever, "heartbeat")
        if self.ea_watchdog:
            _launch_task("EAWatchdog", self.ea_watchdog.run_forever, "ea_watchdog")
        _launch_task("Dashboard", self._run_dashboard, "dashboard")
        if self.order_reconciler:
            _launch_task("OrderReconciler", self.order_reconciler.start, "order_reconciler")
        else:
            _launch_task("PositionSync", self._run_position_sync_loop, "position_sync")
        if self.trailing_stop_manager:
            _launch_task("TrailingStop", self.trailing_stop_manager.start, "trailing_stop")
        if self.position_supervisor and hasattr(self.position_supervisor, "start"):
            _launch_task("PositionSupervisor", self.position_supervisor.start, "position_supervisor")
        _launch_task("MT5HealthMonitor", self._run_mt5_health_monitor, "mt5_health_monitor")
        _launch_task("FridayCloseGuardian", self._run_friday_close_monitor, "friday_close_guardian")
        _launch_task("PositionGuardian", self._run_position_guardian_loop, "position_guardian")
        _launch_task("FlashCrashDetector", self._run_flash_crash_detector, "flash_crash_detector")
        _launch_task("TickStream", self._run_tick_stream_loop, "tick_stream")
        _launch_task("FloatingDrawdownMonitor", self._run_floating_drawdown_monitor, "floating_drawdown_monitor")
        _launch_task("MarginGuardian", self._run_margin_monitor, "margin_guardian")
        _launch_task("PaperTradeMonitor", self._run_paper_trade_monitor, "paper_trade_monitor")
        _launch_task("DBHealthCheck", self._run_db_health_check, "db_health_check")
        _launch_task("ScraperLoop", self._run_scraper_loop, "scraper_loop")
        _launch_task("WhatIfResolver", self._run_whatif_resolver, "whatif_resolver")
        if self.notifier and hasattr(self.notifier, "flush_outbox_loop"):
            _launch_task("NotifierOutboxFlusher", self.notifier.flush_outbox_loop, "notifier_outbox_flusher")
        _launch_task("MicroPlaybookCompiler", self._run_micro_playbook_compiler_loop, "micro_playbook_compiler")
        _launch_task("SkillCurator", self._run_skill_curator_loop, "skill_curator")
        if hasattr(self, "risk_parameter_reloader") and self.risk_parameter_reloader:
            _launch_task("RiskParameterReloader", self._run_risk_parameter_reloader, "risk_parameter_reloader")
        if hasattr(self, "alpha_discovery_scheduler") and self.alpha_discovery_scheduler:
            _launch_task("AlphaDiscoveryScheduler", self.alpha_discovery_scheduler.start, "alpha_discovery_scheduler")
        if hasattr(self, "strategy_synthesis_scheduler") and self.strategy_synthesis_scheduler:
            _launch_task(
                "StrategySynthesisScheduler", self.strategy_synthesis_scheduler.start, "strategy_synthesis_scheduler"
            )
        if hasattr(self, "background_review_engine") and self.background_review_engine:
            _launch_task("BackgroundReviewEngine", self.background_review_engine.run, "background_review_engine")
        if hasattr(self, "playbook_curator") and self.playbook_curator:
            _launch_task("PlaybookCurator", self.playbook_curator.start, "playbook_curator")
        if hasattr(self, "universal_cron") and self.universal_cron:
            self.universal_cron.start()
        if hasattr(self, "config_manager") and self.config_manager:
            _launch_task("ConfigManagerWatcher", self.config_manager.start_watcher, "config_manager_watcher")

        if self.telegram_bot:
            self._tg_task = _launch_task("TelegramBot", self.telegram_bot.start, "telegram_bot")

        # Initialize and launch discovered plugins via PluginEngine
        if hasattr(self, "plugin_engine") and self.plugin_engine:
            try:
                await self.plugin_engine.initialize(self.settings)
                await self.plugin_engine.start()
                await self.plugin_engine.emit_hook("on_startup", agent=self)
            except Exception as e:
                logger.error(f"[PluginEngine] Launch error: {e}", exc_info=True)

        self._tasks = tasks_list
        if hasattr(self, "_recovery_task") and self._recovery_task:
            self._tasks.append(self._recovery_task)

        # Disarm startup watchdog upon successful concurrent task launch
        global_startup_watchdog.mark_complete()

        logger.info(f"All {len(self._tasks)} tasks launched. Agent is RUNNING.")
        logger.info("Press Ctrl+C to stop.")

        # Wait until shutdown event is triggered (via Ctrl+C / SIGINT / SIGTERM or fatal error)
        try:
            await self.shutdown_event.wait()
        finally:
            global_startup_watchdog.mark_complete()
            logger.info("Shutdown event received — executing graceful component shutdown...")
            await self._shutdown()

            logger.info("Waiting up to 10s for worker tasks to finish cleanly...")
            pending = [t for t in self._tasks if not t.done()]
            if pending:
                done, pending = await asyncio.wait(pending, timeout=10.0)

            if pending:
                logger.warning(f"Cancelling {len(pending)} worker tasks that did not exit within 10s grace period...")
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            logger.info("All worker tasks shut down successfully.")

    async def stop(self) -> None:
        """Trigger agent shutdown event."""
        logger.info("TradingAgent stop requested.")
        self.shutdown_event.set()

    async def _shutdown(self) -> None:
        """Graceful shutdown sequence."""
        logger.info("=" * 62)
        logger.info("Shutdown sequence starting...")

        try:
            import json

            from sqlalchemy import select

            from monika.infrastructure.database.db import get_session
            from monika.infrastructure.database.models import Position

            async with get_session() as session:
                open_positions = (
                    (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()
                )

                try:
                    from monika.infrastructure.database.event_store import TradingEventStore

                    await TradingEventStore.emit(
                        session=session,
                        event_type="system.shutdown",
                        payload={"open_positions": len(open_positions), "reason": "graceful_shutdown"},
                        correlation_id=f"shutdown_{clock.now().strftime('%Y%m%d%H%M%S')}",
                        actor="main",
                    )
                    await session.commit()
                except Exception as es_err:
                    logger.debug(f"Event store emit system.shutdown error: {es_err}")

                # Save snapshot to file
                os.makedirs("data", exist_ok=True)
                snapshot = {
                    "shutdown_at": datetime.now(timezone.utc).isoformat(),
                    "open_positions": [
                        {
                            "ticket": p.mt5_ticket,
                            "symbol": p.symbol,
                            "direction": p.direction,
                            "entry": p.entry_price,
                            "sl": p.sl,
                            "tp": p.tp,
                        }
                        for p in open_positions
                    ],
                }

                with open("data/last_shutdown_snapshot.json", "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, indent=2)
                logger.info(f"Shutdown snapshot saved: {len(open_positions)} open positions")

                if open_positions:
                    pos_summary = "\n".join(
                        [
                            f"• {p.symbol} {p.direction.upper()} {p.volume}L @ {p.entry_price} (SL:{p.sl})"
                            for p in open_positions
                        ]
                    )
                    if self.telegram_bot:
                        await self.telegram_bot.send_notification(
                            f"[PERINGATAN] *Agent SHUTDOWN dengan posisi terbuka:*\n{pos_summary}\n\n"
                            f"EA Dead-Man's Switch akan memproteksi posisi ini.\n"
                            f"MT5 terminal JANGAN ditutup!"
                        )
        except Exception as e:
            logger.warning(f"Shutdown position check/snapshot failed: {e}")

        # Stop schedulers
        import inspect

        for comp, name in [
            (self.cycle_scheduler, "CycleScheduler"),
            (self.news_watcher, "NewsWatcher"),
            (self.digest_slice_scheduler, "DigestSliceScheduler"),
            (self.active_calendar_poller, "ActiveCalendarPoller"),
            (self.trigger_checker, "TriggerChecker"),
            (self.heartbeat_mgr, "HeartbeatManager"),
            (self.ea_watchdog, "EAWatchdog"),
            (self.position_supervisor, "PositionSupervisor"),
            (self.position_exit_reviewer, "PositionExitReviewer"),
            (self.position_guardian, "PositionGuardian"),
            (self.order_reconciler, "OrderReconciler"),
            (self.trailing_stop_manager, "TrailingStopManager"),
            (self.edge_strategy_runner, "EdgeStrategyRunner"),
            (self.market_data_scheduler, "MarketDataScheduler"),
            (self.macro_data_scheduler, "MacroDataScheduler"),
            (self.post_release_analyzer, "PostReleaseAnalyzer"),
            (self.alpha_discovery_scheduler, "AlphaDiscoveryScheduler"),
            (getattr(self, "strategy_synthesis_scheduler", None), "StrategySynthesisScheduler"),
            (getattr(self, "background_review_engine", None), "BackgroundReviewEngine"),
            (getattr(self, "playbook_curator", None), "PlaybookCurator"),
            (getattr(self, "universal_cron", None), "UniversalCronScheduler"),
            (self._active_scraper_runner, "ActiveScraperRunner"),
            (getattr(self, "execution_service", None), "ExecutionService"),
            (getattr(self, "mt5_health_checker", None), "MT5HealthChecker"),
            (getattr(self, "config_manager", None), "ConfigManager"),
        ]:
            try:
                if comp:
                    if hasattr(comp, "aclose"):
                        aclose_fn = comp.aclose
                        if inspect.iscoroutinefunction(aclose_fn):
                            await aclose_fn()
                        else:
                            res = aclose_fn()
                            if inspect.isawaitable(res):
                                await res
                    if hasattr(comp, "stop"):
                        stop_fn = comp.stop
                        if inspect.iscoroutinefunction(stop_fn):
                            await stop_fn()
                        else:
                            res = stop_fn()
                            if inspect.isawaitable(res):
                                await res
                    logger.info(f"  [OK] {name} stopped")
            except Exception as e:
                logger.warning(f"  [WARN] {name} stop failed: {e}")

        # Stop PluginEngine
        if hasattr(self, "plugin_engine") and self.plugin_engine:
            try:
                await self.plugin_engine.emit_hook("on_shutdown", agent=self)
                await self.plugin_engine.stop()
                logger.info("  [OK] PluginEngine stopped")
            except Exception as e:
                logger.warning(f"  [WARN] PluginEngine stop failed: {e}")

        # Notify Telegram admin
        try:
            if self.telegram_bot:
                await self.telegram_bot.send_notification("[KRITIS] *Agent stopped.* Graceful shutdown complete.")
        except Exception:
            pass

        # Stop Telegram bot if active
        try:
            if self.telegram_bot and hasattr(self.telegram_bot, "stop"):
                stop_fn = self.telegram_bot.stop
                if inspect.iscoroutinefunction(stop_fn):
                    await stop_fn()
                else:
                    res = stop_fn()
                    if inspect.isawaitable(res):
                        await res
                logger.info("  [OK] TelegramBot stopped")
        except Exception as e:
            logger.warning(f"  [WARN] TelegramBot stop failed: {e}")

        # Write shutdown activity log
        try:
            await self._activity_log.system(
                "Agent stopped — graceful shutdown complete.",
                actor="main",
            )
        except Exception:
            pass

        # Disconnect MT5 with bounded timeout
        try:
            if hasattr(self, "mt5_client") and self.mt5_client:
                await asyncio.wait_for(self.mt5_client.disconnect(), timeout=5.0)
                logger.info("  [OK] MT5 disconnected")
        except Exception as e:
            logger.warning(f"  [WARN] MT5 disconnect error or timeout: {e}")

        # Stop Multi-Process Guardian Supervisor
        if hasattr(self, "guardian_supervisor") and self.guardian_supervisor:
            try:
                self.guardian_supervisor.stop()
                logger.info("  [OK] GuardianSupervisor stopped")
            except Exception as e:
                logger.warning(f"  [WARN] GuardianSupervisor stop failed: {e}")

        # Stop EventBus workers
        if hasattr(self, "event_bus") and self.event_bus and hasattr(self.event_bus, "stop_workers"):
            try:
                self.event_bus.stop_workers()
                logger.info("  [OK] EventBus workers stopped")
            except Exception as e:
                logger.warning(f"  [WARN] EventBus stop workers error: {e}")

        # Cancel and await all active agent tasks and background tasks BEFORE closing DB pool
        all_pending_tasks: list[asyncio.Task[Any]] = []
        if hasattr(self, "_tasks") and self._tasks:
            all_pending_tasks.extend([t for t in self._tasks if not t.done()])
        if hasattr(self, "_background_tasks") and self._background_tasks:
            all_pending_tasks.extend([t for t in self._background_tasks if not t.done() and t not in all_pending_tasks])

        for t in all_pending_tasks:
            t.cancel()
        if all_pending_tasks:
            await asyncio.gather(*all_pending_tasks, return_exceptions=True)
            logger.info(f"  [OK] Cancelled {len(all_pending_tasks)} active agent and background tasks")

        # Close DB pool
        try:
            await close_db()
            logger.info("  [OK] DB connection pool closed")
        except Exception as e:
            logger.warning(f"  [WARN] DB close error: {e}")

        # Shutdown Telegram bot after all notifications are sent
        if hasattr(self, "_tg_task") and self._tg_task and not self._tg_task.done():
            self._tg_task.cancel()
            try:
                await asyncio.wait_for(self._tg_task, timeout=5.0)
            except asyncio.CancelledError, asyncio.TimeoutError:
                pass

        logger.info("Shutdown complete. Goodbye.")
        logger.info("=" * 62)

    async def _send_startup_notification(self) -> None:
        """Send startup notification to Telegram admin (best-effort)."""
        try:
            await asyncio.sleep(5)  # Wait for bot to be online
            if self.telegram_bot:
                env = self.settings.get("environment", "dev")
                assets = ", ".join(self.settings.get("trading", {}).get("asset_universe", []))
                now = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
                await self.telegram_bot.send_notification(
                    f"[AKTIF] *Agent Online*\n\n"
                    f"Environment: `{env}`\n"
                    f"Assets: {assets}\n"
                    f"Started: {now}\n\n"
                    f"Use /status for live dashboard."
                )
        except Exception as e:
            logger.debug(f"Startup notification failed: {e}")


__all__ = [
    "BANNER",
    "AgentLifecycleMixin",
]
