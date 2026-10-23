# ==============================================================================
# File: application/orchestrator/builder.py
# ==============================================================================

"""
Component initialization and wiring mixin for TradingAgent.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    import asyncio
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
    from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

logger = logging.getLogger("TradingAgent.Main")


class AgentBuilderMixin:
    """Mixin responsible for instantiating and wiring all subsystems."""

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
    harness_service: Optional[Any]
    container: Optional[Any]
    plugin_engine: Optional[Any]
    universal_cron: Optional[Any]
    guardian_supervisor: Optional[Any]
    request_fallback_consent: Callable[[str], Any]

    def _init_components(self) -> None:
        """Instantiate all components with their dependencies."""
        if not hasattr(self, "container") or self.container is None:
            from monika.application.bootstrap import bootstrap_application

            self.container = bootstrap_application(settings=self.settings)

        container = self.container
        assert container is not None

        if not container.has("shutdown_event"):
            container.register_instance("shutdown_event", self.shutdown_event)
        if hasattr(self, "_recovery_complete") and not container.has("recovery_complete_event"):
            container.register_instance("recovery_complete_event", self._recovery_complete)

        from monika.application.agent.task_registry import TaskRegistry
        from monika.application.analysis.stages.fundamental_stage import FundamentalStage
        from monika.application.analysis.stages.per_asset_stage import PerAssetStage
        from monika.application.execution.execution_service import ExecutionService
        from monika.core.primitives.event_bus import get_event_bus
        from monika.application.scheduler.edge_strategy_runner import EdgeStrategyRunner
        from monika.application.scheduler.graph_cycle_scheduler import GraphCycleScheduler
        from monika.application.scheduler.macro_data_scheduler import MacroDataScheduler
        from monika.application.scheduler.market_data_scheduler import MarketDataScheduler
        from monika.application.scheduler.news_watcher import NewsWatcher
        from monika.application.scheduler.position_guardian import PositionGuardian
        from monika.application.scheduler.trailing_stop_manager import TrailingStopManager
        from monika.application.scheduler.trigger_checker import TriggerChecker
        from monika.infrastructure.brokers.ea_bridge.heartbeat_writer import HeartbeatManager
        from monika.infrastructure.brokers.mt5_client import MT5Client

        if not container.has("task_registry"):
            self.task_registry = TaskRegistry(self.shutdown_event)
            container.register_instance("task_registry", self.task_registry)
        else:
            self.task_registry = container.get("task_registry")

        if not container.has("event_bus"):
            self.event_bus = get_event_bus()
            container.register_instance("event_bus", self.event_bus)
        else:
            self.event_bus = container.get("event_bus")

        if not container.has("mt5_client"):
            self.mt5_client = MT5Client(settings=self.settings)
            container.register_instance("mt5_client", self.mt5_client)
        else:
            self.mt5_client = container.get("mt5_client")
        from monika.application.execution.health_check import FlakeTolerantHealthChecker

        self.mt5_health_checker = FlakeTolerantHealthChecker(self.mt5_client, ttl_seconds=30.0, grace_seconds=60.0)
        self.market_data_scheduler = MarketDataScheduler(
            self.settings, mt5_client=self.mt5_client, event_bus=self.event_bus
        )
        warmup_evt = getattr(self, "_warmup_complete", self._recovery_complete)
        self.macro_data_scheduler = MacroDataScheduler(self.settings, recovery_event=warmup_evt)

        exec_cfg = self.settings.get("execution", {})
        adapter_type = exec_cfg.get("adapter_type", "live")
        broker_adapter = None
        if adapter_type == "remote_gateway":
            from monika.infrastructure.brokers.broker_adapter import MT5RemoteGatewayAdapter

            gateway_url = (
                exec_cfg.get("remote_gateway_url")
                or exec_cfg.get("gateway_url")
                or os.getenv("EXECUTION_SERVICE_URL")
                or os.getenv("MT5_GATEWAY_URL")
                or "http://127.0.0.1:8080"
            )
            api_token = (
                exec_cfg.get("remote_gateway_token")
                or exec_cfg.get("api_token")
                or os.getenv("EXECUTION_SERVICE_AUTH_TOKEN")
                or os.getenv("MT5_GATEWAY_TOKEN")
            )
            broker_adapter = MT5RemoteGatewayAdapter(gateway_url=gateway_url, api_token=api_token)
            logger.info(f"ExecutionService configured with MT5RemoteGatewayAdapter ({gateway_url})")

        if broker_adapter is not None or not container.has("execution_service"):
            self.execution_service = ExecutionService(
                self.settings,
                mt5_client=self.mt5_client,
                dry_run=self.dry_run,
                broker_adapter=broker_adapter,
            )
            container.register_instance("execution_service", self.execution_service)
        else:
            self.execution_service = container.get("execution_service")
        mt5_common = self.settings.get("execution", {}).get("mt5_common_dir", "")
        self.heartbeat_mgr = HeartbeatManager(mt5_common_path=mt5_common)
        self.ea_watchdog = self.heartbeat_mgr.get_watchdog()

        self.edge_strategy_runner = EdgeStrategyRunner(
            self.settings,
            execution_service=self.execution_service,
            market_data_scheduler=self.market_data_scheduler,
            recovery_event=warmup_evt,
        )

        self.fundamental_stage = FundamentalStage(self.settings)
        self.per_asset_stage = PerAssetStage(self.settings, mt5_client=self.mt5_client)
        self.fundamental_stage.consent_callback = self.request_fallback_consent
        self.per_asset_stage.consent_callback = self.request_fallback_consent
        self.fundamental_stage.is_fallback_always_approved = lambda: getattr(self, "_fallback_always_approved", False)
        self.per_asset_stage.is_fallback_always_approved = lambda: getattr(self, "_fallback_always_approved", False)

        from monika.application.scheduler.position_exit_reviewer import PositionExitReviewer

        self.position_exit_reviewer = PositionExitReviewer(
            self.settings,
            per_asset_stage=self.per_asset_stage,
            execution_service=self.execution_service,
            recovery_event=self._recovery_complete,
        )

        self.position_guardian = PositionGuardian(self.settings, execution_service=self.execution_service)
        from monika.application.scheduler.order_reconciler import OrderReconciler

        self.order_reconciler = OrderReconciler(
            self.settings,
            mt5_client=self.mt5_client,
            execution_service=self.execution_service,
            broker_adapter=getattr(self.execution_service, "broker_adapter", None),
            recovery_event=self._recovery_complete,
            shutdown_event=self.shutdown_event,
        )
        from monika.application.scheduler.active_calendar_poller import ActiveCalendarPoller

        self.active_calendar_poller = ActiveCalendarPoller(self.settings)

        self.trailing_stop_manager = TrailingStopManager(
            self.settings,
            execution_service=self.execution_service,
            recovery_event=self._recovery_complete,
        )

        try:
            from monika.application.scheduler.position_supervisor import PositionSupervisor

            self.position_supervisor = PositionSupervisor(
                mt5_client=self.mt5_client,
                settings=self.settings,
            )
            if self.position_guardian is not None and hasattr(self.position_guardian, "check_and_protect"):
                guardian = self.position_guardian
                self.position_supervisor.register_evaluator(
                    "position_guardian",
                    lambda pos, acct: guardian.check_and_protect(),
                )
            if self.trailing_stop_manager is not None and hasattr(self.trailing_stop_manager, "run_once"):
                trailing_mgr = self.trailing_stop_manager
                self.position_supervisor.register_evaluator(
                    "trailing_stop_manager",
                    lambda pos, acct: trailing_mgr.run_once(),
                )
        except Exception as e:
            logger.warning(f"PositionSupervisor initialization failed: {e}")
            self.position_supervisor = None

        from monika.application.scheduler.digest_slice_scheduler import DigestSliceScheduler

        self.digest_slice_scheduler = DigestSliceScheduler(self.settings)

        self.cycle_scheduler = GraphCycleScheduler(
            self.settings,
            mt5_client=self.mt5_client,
            fundamental_stage=self.fundamental_stage,
            per_asset_stage=self.per_asset_stage,
            dry_run=self.dry_run,
            recovery_event=warmup_evt,
            macro_data_scheduler=self.macro_data_scheduler,
            execution_service=self.execution_service,
        )
        # Wire ActivityLogger to key components
        self.cycle_scheduler._activity_log = self._activity_log

        from monika.application.agent.turn_lease_manager import SymbolTurnLeaseManager

        self.turn_lease_manager = SymbolTurnLeaseManager.get_instance()

        self.news_watcher = NewsWatcher(
            self.settings,
            cycle_scheduler=self.cycle_scheduler,
            fundamental_stage=self.fundamental_stage,
            per_asset_stage=self.per_asset_stage,
            position_guardian=self.position_guardian,
            execution_service=self.execution_service,
        )
        self.news_watcher._activity_log = self._activity_log

        from monika.application.scheduler.post_release_analyzer import PostReleaseAnalyzer

        self.post_release_analyzer = PostReleaseAnalyzer(
            self.settings,
            per_asset_stage=self.per_asset_stage,
            fundamental_stage=self.fundamental_stage,
            execution_service=self.execution_service,
            mt5_client=self.mt5_client,
            dry_run=self.dry_run,
            cycle_scheduler=self.cycle_scheduler,
        )
        self.active_calendar_poller._news_watcher = self.news_watcher
        self.news_watcher._post_release_analyzer = self.post_release_analyzer
        self.active_calendar_poller._post_release_analyzer = self.post_release_analyzer

        self.trigger_checker = TriggerChecker(
            self.settings,
            per_asset_stage=self.per_asset_stage,
            execution_service=self.execution_service,
            cycle_scheduler=self.cycle_scheduler,
            recovery_event=self._recovery_complete,
        )

        # Telegram Bot (Presentation Interface)
        bot_instance = self.container.get("telegram_bot") if self.container else None
        if bot_instance is not None:
            self.telegram_bot = bot_instance
        else:
            try:
                import importlib

                tg_mod = importlib.import_module("monika.interfaces.telegram.bot")
                TelegramBotCls = getattr(tg_mod, "TelegramBot")
                self.telegram_bot = TelegramBotCls(
                    settings=self.settings,
                    execution_service=self.execution_service,
                    cycle_scheduler=self.cycle_scheduler,
                )
            except Exception as tg_err:
                logger.debug(f"TelegramBot interface resolution note: {tg_err}")
                self.telegram_bot = None

        if self.telegram_bot is not None:
            self.telegram_bot._activity_log = self._activity_log
            self.telegram_bot.task_registry = self.task_registry

        from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

        self.notifier = AgentNotifier()

        from monika.application.scheduler.flash_crash_detector import FlashCrashDetector

        self.flash_crash_detector = FlashCrashDetector(
            self.settings,
            execution_service=self.execution_service,
            notifier=self.notifier,
        )
        if self.execution_service is not None:
            if hasattr(self.execution_service, "gate") and getattr(self.execution_service, "gate", None):
                self.execution_service.gate.flash_crash_detector = self.flash_crash_detector
            if hasattr(self.execution_service, "risk_gate") and getattr(self.execution_service, "risk_gate", None):
                self.execution_service.risk_gate.flash_crash_detector = self.flash_crash_detector

        # Hot-Reload Risk Parameters (M-4)
        from monika.core.config.hot_reload import RiskParameterReloader

        settings_yaml_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "settings.yaml")
        rg = getattr(self.execution_service, "risk_gate", None)
        if rg:
            self.risk_parameter_reloader = RiskParameterReloader(
                config_path=settings_yaml_path,
                risk_gate=rg,
                notifier=self.notifier,
                check_interval_seconds=15.0,
            )
        else:
            self.risk_parameter_reloader = None

        # Universal ConfigManager Pub/Sub Subscriptions
        from monika.core.config.config_manager import ConfigManager

        self.config_manager = ConfigManager.get_instance()

        def _on_config_risk_update(payload: dict):
            if rg and hasattr(rg, "update_parameters"):
                try:
                    rg.update_parameters(payload)
                    logger.info("ConfigManager dispatched risk parameter reload to RiskGate")
                except Exception as ex:
                    logger.warning(f"Error applying ConfigManager risk update: {ex}")

        def _on_config_scheduler_update(payload: dict):
            cs = getattr(self, "cycle_scheduler", None)
            if cs:
                if "analysis_cycle_hours" in payload:
                    try:
                        cs.cycle_interval_hours = float(payload["analysis_cycle_hours"])
                        logger.info(f"ConfigManager updated cycle_interval_hours to {cs.cycle_interval_hours}")
                    except Exception:
                        pass
                elif "cycle_interval_hours" in payload:
                    try:
                        cs.cycle_interval_hours = float(payload["cycle_interval_hours"])
                        logger.info(f"ConfigManager updated cycle_interval_hours to {cs.cycle_interval_hours}")
                    except Exception:
                        pass

        def _on_config_all_update(payload: dict):
            if isinstance(payload, dict):
                self.settings.clear()
                self.settings.update(payload)

        self.config_manager.subscribe("risk", _on_config_risk_update)
        self.config_manager.subscribe("scheduler", _on_config_scheduler_update)
        self.config_manager.subscribe("all", _on_config_all_update)

        # Wire EventBus subscribers for sub-second reactive protection & live observability
        if self.event_bus:
            from monika.core.primitives.event_bus import OrderStateChangedEvent, TickPriceEvent

            if self.flash_crash_detector and hasattr(self.flash_crash_detector, "on_tick"):
                self.event_bus.subscribe(TickPriceEvent, self.flash_crash_detector.on_tick, priority=10)
            if self.position_guardian and hasattr(self.position_guardian, "on_tick"):
                self.event_bus.subscribe(TickPriceEvent, self.position_guardian.on_tick, priority=8)
            if self.trailing_stop_manager and hasattr(self.trailing_stop_manager, "on_tick"):
                self.event_bus.subscribe(TickPriceEvent, self.trailing_stop_manager.on_tick, priority=5)

            from monika.core.primitives.event_bus import CircuitBreakerEvent, RiskBreachEvent

            async def _on_circuit_breaker(evt: CircuitBreakerEvent):
                logger.warning(
                    f"[EventBus] Circuit breaker received from {evt.component}: {evt.reason} (active={evt.is_active})"
                )
                if (
                    evt.is_active
                    and self.execution_service
                    and hasattr(self.execution_service, "trigger_circuit_breaker")
                ):
                    try:
                        await self.execution_service.trigger_circuit_breaker(f"{evt.component}: {evt.reason}")
                    except Exception as cb_err:
                        logger.error(f"[EventBus] Failed to dispatch circuit breaker to ExecutionService: {cb_err}")

            async def _on_risk_breach(evt: RiskBreachEvent):
                logger.warning(f"[EventBus] Risk breach received: {evt.breach_type} (severity={evt.severity})")

            self.event_bus.subscribe(CircuitBreakerEvent, _on_circuit_breaker, priority=10)
            self.event_bus.subscribe(RiskBreachEvent, _on_risk_breach, priority=10)
            logger.info("  [OK] EventBus CircuitBreakerEvent and RiskBreachEvent subscribed for safety protection")

        # Berikan recovery_complete event ke cycle_scheduler agar bisa menunggu
        if hasattr(self, "cycle_scheduler") and self.cycle_scheduler is not None:
            self.cycle_scheduler._recovery_complete_event = self._recovery_complete

        from monika.application.scheduler.alpha_discovery_scheduler import AlphaDiscoveryScheduler

        self.alpha_discovery_scheduler = AlphaDiscoveryScheduler(
            self.settings,
            recovery_event=self._recovery_complete,
            notifier=self.notifier,
            edge_strategy_runner=self.edge_strategy_runner,
        )

        from monika.application.scheduler.strategy_synthesis_scheduler import StrategySynthesisScheduler

        self.strategy_synthesis_scheduler = StrategySynthesisScheduler(
            self.settings,
            recovery_event=self._recovery_complete,
            notifier=self.notifier,
            edge_strategy_runner=self.edge_strategy_runner,
        )

        from monika.application.analysis.memory.background_review import BackgroundReviewEngine

        self.background_review_engine = BackgroundReviewEngine(self.settings)

        from monika.application.scheduler.playbook_curator import PlaybookCurator

        self.playbook_curator = PlaybookCurator(self.settings)

        # Initialize Universal PluginEngine Harness
        try:
            from monika.application.plugins.engine.engine import PluginEngine

            if not container.has("settings"):
                container.register_instance("settings", self.settings)

            # Initialize RecursiveHarnessService
            try:
                from monika.application.analysis.recursive_harness.service import RecursiveHarnessService
                from monika.application.analysis.prompt_sections import get_prompt_section_registry

                self.harness_service = RecursiveHarnessService()
                container.register_instance("harness_service", self.harness_service)

                psr = get_prompt_section_registry()

                def _inject_harness_lessons(ctx: Any = None) -> str:
                    svc = getattr(self, "harness_service", None)
                    if not svc:
                        return ""
                    ctx_map = ctx if isinstance(ctx, dict) else {}
                    domain = ctx_map.get("domain") or ctx_map.get("symbol") or "GENERAL"
                    return svc.library.format_domain_lessons_for_prompt(str(domain), max_lessons=2)

                psr.register(
                    section_id="harness_domain_lessons",
                    content=_inject_harness_lessons,
                    position="after_memory",
                    max_chars=2048,
                    plugin_id="harness_recursive_engine",
                )
                logger.info("[Builder] RecursiveHarnessService wired into container and PromptSectionRegistry.")
            except Exception as h_err:
                logger.debug(f"[Builder] Harness wiring notice: {h_err}")

            self.plugin_engine = PluginEngine(
                container=container,
                event_bus=self.event_bus,
                task_registry=self.task_registry,
            )
            from monika.core.paths import get_repo_root

            plugins_dir = os.path.join(get_repo_root(), "src", "monika", "application", "plugins")
            self.plugin_engine.discover_directory(plugins_dir)
            self.plugin_engine.discover_entrypoints()
            logger.info(f"[PluginEngine] Discovered {len(self.plugin_engine.registry)} plugins.")
            if self.risk_parameter_reloader:
                self.risk_parameter_reloader.subscribe(self.plugin_engine)
        except Exception as e:
            logger.warning(f"PluginEngine initialization error: {e}")

        # Initialize Universal Cron Scheduler
        try:
            from monika.application.scheduler.unified_cron_engine import get_unified_cron_engine

            self.universal_cron = get_unified_cron_engine()
            logger.info("  [OK] UnifiedCronEngine initialized")
        except Exception as e:
            logger.warning(f"UnifiedCronEngine initialization error: {e}")
        # Initialize Multi-Process Guardian Supervisor
        try:
            from monika.application.agent.monitors.process_guardian import GuardianSupervisor

            self.guardian_supervisor = GuardianSupervisor(settings=self.settings)
            logger.info("  [OK] Multi-Process GuardianSupervisor initialized")
        except Exception as e:
            logger.warning(f"GuardianSupervisor initialization error: {e}")
            self.guardian_supervisor = None

        logger.info("All components initialized")


__all__ = ["AgentBuilderMixin"]
