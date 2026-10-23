# ==============================================================================
# File: application/orchestrator/agent.py
# ==============================================================================

"""
TradingAgent composite class orchestrating all subsystems and mixins.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

from monika.application.orchestrator.builder import AgentBuilderMixin
from monika.application.orchestrator.lifecycle import AgentLifecycleMixin
from monika.application.orchestrator.monitors import AgentMonitorsMixin
from monika.application.orchestrator.recovery import AgentRecoveryMixin
from monika.core.telemetry.activity_logger import ActivityLogger

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
    from monika.infrastructure.brokers.ea_bridge.heartbeat_writer import HeartbeatManager
    from monika.infrastructure.brokers.ea_bridge.watchdog import EAWatchdog
    from monika.infrastructure.brokers.mt5_client import MT5Client
    from monika.infrastructure.notifications.telegram_notifier import AgentNotifier


class TradingAgent(AgentBuilderMixin, AgentRecoveryMixin, AgentMonitorsMixin, AgentLifecycleMixin):
    """
    Top-level orchestrator that owns and coordinates all subsystems.
    Composes component builder, recovery, background monitors, and lifecycle mixins.
    """

    execution_service: Optional[ExecutionService]
    cycle_scheduler: Optional[GraphCycleScheduler]
    news_watcher: Optional[NewsWatcher]
    digest_slice_scheduler: Optional[DigestSliceScheduler]
    trigger_checker: Optional[TriggerChecker]
    telegram_bot: Optional[Any]
    heartbeat_mgr: Optional[HeartbeatManager]
    ea_watchdog: Optional[EAWatchdog]
    market_data_scheduler: Optional[MarketDataScheduler]
    macro_data_scheduler: Optional[MacroDataScheduler]
    edge_strategy_runner: Optional[EdgeStrategyRunner]
    position_exit_reviewer: Optional[PositionExitReviewer]
    position_guardian: Optional[PositionGuardian]
    order_reconciler: Optional[OrderReconciler]
    trailing_stop_manager: Optional[TrailingStopManager]
    active_calendar_poller: Optional[ActiveCalendarPoller]
    post_release_analyzer: Optional[PostReleaseAnalyzer]
    alpha_discovery_scheduler: Optional[AlphaDiscoveryScheduler]
    strategy_synthesis_scheduler: Optional[StrategySynthesisScheduler]
    background_review_engine: Optional[Any]
    playbook_curator: Optional[Any]
    harness_service: Optional[Any]
    _active_scraper_runner: Optional[Any]
    fundamental_stage: Optional[FundamentalStage]
    per_asset_stage: Optional[PerAssetStage]
    flash_crash_detector: Optional[FlashCrashDetector]
    turn_lease_manager: Optional[Any]
    notifier: Optional[AgentNotifier]
    mt5_client: Optional[MT5Client]
    position_supervisor: Optional[PositionSupervisor]
    event_bus: Optional[Any]
    mt5_health_checker: Optional[Any]
    risk_parameter_reloader: Optional[Any]
    config_manager: Optional[Any]
    task_registry: Optional[Any]
    container: Optional[Any]
    plugin_engine: Optional[Any]
    universal_cron: Optional[Any]
    guardian_supervisor: Optional[Any]
    _recovery_task: Optional[asyncio.Task[Any]]
    _tg_task: Optional[asyncio.Task[Any]]
    _mt5_degraded: bool
    _fallback_always_approved: bool
    _recovery_complete: asyncio.Event
    _warmup_complete: asyncio.Event
    _activity_log: ActivityLogger
    _background_tasks: set[asyncio.Task[Any]]
    _tasks: list[asyncio.Task[Any]]

    def __init__(
        self,
        settings: dict[str, Any],
        dry_run: bool = False,
        container: Optional[Any] = None,
    ) -> None:
        self.settings = settings
        paper_cfg = self.settings.get("trading", {}).get("paper_trading", {})
        if "enabled" in paper_cfg:
            paper_enabled = bool(paper_cfg["enabled"])
        elif "paper_trading" in self.settings:
            paper_enabled = bool(self.settings.get("paper_trading", {}).get("enabled", True))
        else:
            paper_enabled = True
        self.dry_run = dry_run or paper_enabled
        self.shutdown_event = asyncio.Event()
        # Event to unblock position guards once startup position sync completes.
        self._recovery_complete = asyncio.Event()
        # Event to block initial analysis cycles and quant strategies until market data warmup completes.
        self._warmup_complete = asyncio.Event()
        self._activity_log = ActivityLogger()
        self._fallback_always_approved = False
        self._mt5_degraded = False
        self._recovery_task = None
        self._tg_task = None
        self.event_bus = None

        self.execution_service = None
        self.cycle_scheduler = None
        self.news_watcher = None
        self.digest_slice_scheduler = None
        self.trigger_checker = None
        self.telegram_bot = None
        self.heartbeat_mgr = None
        self.ea_watchdog = None
        self.market_data_scheduler = None
        self.macro_data_scheduler = None
        self.edge_strategy_runner = None
        self.position_exit_reviewer = None
        self.position_guardian = None
        self.order_reconciler = None
        self.trailing_stop_manager = None
        self.active_calendar_poller = None
        self.post_release_analyzer = None
        self.alpha_discovery_scheduler = None
        self.strategy_synthesis_scheduler = None
        self.background_review_engine = None
        self.playbook_curator = None
        self.harness_service = None
        self._active_scraper_runner = None
        self.fundamental_stage = None
        self.per_asset_stage = None
        self.flash_crash_detector = None
        self.turn_lease_manager = None
        self.notifier = None
        self.mt5_client = None
        self.mt5_health_checker = None
        self.risk_parameter_reloader = None
        self.config_manager = None
        self.position_supervisor = None
        self.task_registry = None
        if container is not None:
            self.container = container
        else:
            from monika.core.container import get_container

            self.container = get_container().extend()
            self.container.register("settings", self.settings)
        self.plugin_engine = None
        self.universal_cron = None
        self.guardian_supervisor = None
        self._background_tasks = set()
        self._tasks = []

    def _create_background_task(self, coro: Any, name: Optional[str] = None) -> asyncio.Task[Any]:
        """Create and track background task to prevent dangling or orphaned tasks."""
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task


__all__ = ["TradingAgent"]
