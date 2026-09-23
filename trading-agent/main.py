# ==============================================================================
# File: main.py
# ==============================================================================

"""
AI Trading Agent — Main Orchestrator
====================================

Core runtime orchestrator for multi-provider AI trading system.

Architecture (concurrent components orchestrated via asyncio.gather):

  ┌─────────────────────────────────────────────────────────────────┐
  │                     AI TRADING AGENT                            │
  │                                                                 │
  │ ┌──────────────────┐    ┌──────────────────┐     ┌────────────┐ │
  │ │  CycleScheduler  │    │  NewsWatcher     │     │  Trigger   │ │
  │ │  (every 6 hours) │    │  (every 5 min)   │     │  Checker   │ │
  │ │  Full analysis   │    │  High-impact news│     │  (2 min)   │ │
  │ └────────┬─────────┘    └────────┬─────────┘     └─────┬──────┘ │
  │          │                       │                     │        │
  │          └───────────────────────┴──────────────┬──────┘        │
  │                                                 │               │
  │                                        ┌────────▼────────┐      │
  │                                        │  ExecutionSvc   │      │
  │                                        │  RiskGate       │      │
  │                                        │  MT5 Bridge     │      │
  │                                        └────────┬────────┘      │
  │                                                 │               │
  │ ┌─────────────────┐    ┌─────────────┐    ┌─────▼───────────┐   │
  │ │  Telegram Bot   │◄───┤  Heartbeat  │    │  Dashboard API  │   │
  │ │  (polling)      │    │  Writer     │    │  (FastAPI)      │   │
  │ └─────────────────┘    └─────────────┘    └─────────────────┘   │
  └─────────────────────────────────────────────────────────────────┘

Startup sequence:
  1. Setup logging (file + console)
  2. Load settings (config/settings.yaml + .env)
  3. Init DB (create tables if not exist)
  4. Startup health checks (DB, API keys)
  5. Initialize all components
  6. Write startup activity log
  7. Launch all concurrent tasks
  8. Block until SIGINT/SIGTERM

Shutdown sequence (graceful):
  1. Receive SIGINT/SIGTERM → set shutdown event
  2. Stop all schedulers (allow current cycle to finish)
  3. Stop Telegram bot polling
  4. Stop dashboard API server
  5. Stop heartbeat writer
  6. Close DB connection pool
  7. Write shutdown activity log
  8. Exit with code 0
"""

import asyncio
import logging
import os
import signal
import sys
import argparse
from datetime import datetime, timezone, timedelta

# Arm startup watchdog early before heavy application imports (skipped in test runner)
if "pytest" not in sys.modules and "PYTEST_CURRENT_TEST" not in os.environ:
    from agent.monitors.startup_watchdog import arm_startup_watchdog
    arm_startup_watchdog(timeout_s=180.0)
from typing import Callable, Optional, Any, TYPE_CHECKING

import utils.clock as clock

if TYPE_CHECKING:
    from execution.mt5_client import MT5Client
    from execution.execution_service import ExecutionService
    from execution.ea_bridge.heartbeat_writer import HeartbeatManager
    from scheduler.graph_cycle_scheduler import GraphCycleScheduler
    from scheduler.news_watcher import NewsWatcher
    from scheduler.trigger_checker import TriggerChecker
    from telegram_bot.bot import TelegramBot
    from analysis.stages.fundamental_stage import FundamentalStage
    from analysis.stages.per_asset_stage import PerAssetStage
    from scheduler.position_guardian import PositionGuardian
    from scheduler.trailing_stop_manager import TrailingStopManager
    from scheduler.edge_strategy_runner import EdgeStrategyRunner
    from scheduler.market_data_scheduler import MarketDataScheduler
    from scheduler.macro_data_scheduler import MacroDataScheduler
    from scheduler.position_exit_reviewer import PositionExitReviewer
    from scheduler.order_reconciler import OrderReconciler
    from scheduler.active_calendar_poller import ActiveCalendarPoller
    from scheduler.digest_slice_scheduler import DigestSliceScheduler
    from scheduler.post_release_analyzer import PostReleaseAnalyzer
    from scheduler.alpha_discovery_scheduler import AlphaDiscoveryScheduler
    from scheduler.strategy_synthesis_scheduler import StrategySynthesisScheduler
    from scheduler.flash_crash_detector import FlashCrashDetector
    from scheduler.position_supervisor import PositionSupervisor
    from utils.infra.notifier import AgentNotifier

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment Variable Security Fence (Phase 6.3)
# Protect host bootstrap variables against project-level .env hijacking
# ---------------------------------------------------------------------------
FORBIDDEN_ENV_OVERRIDES = {"PATH", "PYTHONPATH", "SYSTEMROOT", "COMSPEC"}
_initial_host_env = {k: os.environ[k] for k in FORBIDDEN_ENV_OVERRIDES if k in os.environ}

# Load .env safely without overriding existing host environment
load_dotenv(override=False)
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'), override=False)
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=False)

# Enforce security fence: restore host bootstrap values if overwritten
for _fence_key, _fence_val in _initial_host_env.items():
    if os.environ.get(_fence_key) != _fence_val:
        os.environ[_fence_key] = _fence_val

# ---------------------------------------------------------------------------
# Bootstrap runtime & network hardening (RFC 8305 Happy Eyeballs & Windows UTF-8)
# ---------------------------------------------------------------------------
from bootstrap import install_bootstrap_hardening
install_bootstrap_hardening()

# ---------------------------------------------------------------------------
# Bootstrap logging immediately (before any other import)
# ---------------------------------------------------------------------------
from logging_observability.activity_logger import setup_logging
setup_logging(log_dir="logs", level=logging.INFO)
logger = logging.getLogger("TradingAgent.Main")

# ---------------------------------------------------------------------------
# Application imports (after logging is set up)
# ---------------------------------------------------------------------------
from config.settings import load_settings, load_all_config
from database.db import init_db, close_db
from logging_observability.activity_logger import ActivityLogger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║             MONIKA — MT5 TRADING AGENT  v1.0.0               ║
╚══════════════════════════════════════════════════════════════╝
"""


# ---------------------------------------------------------------------------
# Health Checks (Delegated to agent.startup_checks)
# ---------------------------------------------------------------------------
from agent.startup_checks import StartupChecker, run_startup_checks as _delegate_startup_checks

async def run_startup_checks(settings: dict) -> bool:
    """
    Run all startup health checks.
    P2-3: Validasi bahwa PostgreSQL digunakan (bukan SQLite).
    PostgreSQL is REQUIRED — partial unique indexes behave incorrectly on SQLite.

    Returns:
        True if all critical checks pass, False if agent should abort.
    """
    db_url = os.getenv('DATABASE_URL', '')
    if 'sqlite' in db_url.lower():
        logger.error('[FAIL] SQLite detected. PostgreSQL is REQUIRED — partial unique indexes behave incorrectly on SQLite.')
        return False
    return await _delegate_startup_checks(settings)


# ---------------------------------------------------------------------------
# Task wrappers (Delegated to agent.task_registry)
# ---------------------------------------------------------------------------
from agent.task_registry import (
    CORE_TRADING_TASKS,
    CLEAN_SHUTDOWN_FLAG,
    PERMANENT_ERRORS,
    LONG_RETRY_ERRORS,
    TaskDefinition,
    TaskRegistry,
    mark_clean_shutdown,
    _safe_notify_warning,
    _safe_notify_critical,
    _run_with_restart,
    get_emergency_exit_code,
    set_emergency_exit_code,
)
from agent.monitors import (
    run_floating_drawdown_monitor,
    run_scraper_loop,
    run_db_health_check,
    run_paper_trade_monitor,
)

_EMERGENCY_EXIT_CODE: Optional[int] = None



# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

class TradingAgent:
    """
    Top-level orchestrator that owns and coordinates all subsystems.
    """

    execution_service: Optional['ExecutionService']
    cycle_scheduler: Optional['GraphCycleScheduler']
    news_watcher: Optional['NewsWatcher']
    digest_slice_scheduler: Optional['DigestSliceScheduler']
    trigger_checker: Optional['TriggerChecker']
    telegram_bot: Optional['TelegramBot']
    heartbeat_mgr: Optional['HeartbeatManager']
    market_data_scheduler: Optional['MarketDataScheduler']
    macro_data_scheduler: Optional['MacroDataScheduler']
    edge_strategy_runner: Optional['EdgeStrategyRunner']
    position_exit_reviewer: Optional['PositionExitReviewer']
    position_guardian: Optional['PositionGuardian']
    order_reconciler: Optional['OrderReconciler']
    trailing_stop_manager: Optional['TrailingStopManager']
    active_calendar_poller: Optional['ActiveCalendarPoller']
    post_release_analyzer: Optional['PostReleaseAnalyzer']
    alpha_discovery_scheduler: Optional['AlphaDiscoveryScheduler']
    strategy_synthesis_scheduler: Optional['StrategySynthesisScheduler']
    background_review_engine: Optional[Any]
    playbook_curator: Optional[Any]
    _active_scraper_runner: Optional[Any]
    fundamental_stage: Optional['FundamentalStage']
    per_asset_stage: Optional['PerAssetStage']
    flash_crash_detector: Optional['FlashCrashDetector']
    notifier: Optional['AgentNotifier']
    mt5_client: Optional['MT5Client']
    position_supervisor: Optional['PositionSupervisor']
    event_bus: Optional[Any]
    mt5_health_checker: Optional[Any]
    risk_parameter_reloader: Optional[Any]
    task_registry: Optional[Any]
    plugin_loader: Optional[Any]
    _recovery_task: Optional[asyncio.Task]
    _tg_task: Optional[asyncio.Task]
    _mt5_degraded: bool
    _fallback_always_approved: bool
    _recovery_complete: asyncio.Event
    _activity_log: ActivityLogger
    _background_tasks: set[asyncio.Task]
    _tasks: list[asyncio.Task]

    def __init__(self, settings: dict, dry_run: bool = False):
        self.settings = settings
        self.dry_run = dry_run
        self.shutdown_event = asyncio.Event()
        # Event to block the initial cycle until startup recovery completes.
        # The cycle scheduler waits on this event before initiating the first cycle.
        self._recovery_complete = asyncio.Event()
        self._activity_log = ActivityLogger()
        self._fallback_always_approved = False
        self._mt5_degraded = False
        self._recovery_task = None
        self._tg_task = None
        self.event_bus = None

        self.execution_service = None
        self.cycle_scheduler   = None
        self.news_watcher      = None
        self.digest_slice_scheduler = None
        self.trigger_checker   = None
        self.telegram_bot      = None
        self.heartbeat_mgr     = None
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
        self.background_review_engine = None
        self.playbook_curator = None
        self._active_scraper_runner = None
        self.fundamental_stage = None
        self.per_asset_stage = None
        self.flash_crash_detector = None
        self.turn_lease_manager = None
        self.notifier = None
        self.mt5_client = None
        self.mt5_health_checker = None
        self.risk_parameter_reloader = None
        self.position_supervisor = None
        self.task_registry = None
        self._background_tasks: set[asyncio.Task] = set()
        self._tasks: list[asyncio.Task] = []

    def _create_background_task(self, coro, name: Optional[str] = None) -> asyncio.Task:
        """Create and track background task to prevent dangling or orphaned tasks."""
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def _init_components(self):
        """Instantiate all components with their dependencies."""
        from agent.task_registry import TaskRegistry
        self.task_registry = TaskRegistry(self.shutdown_event)
        from execution.mt5_client import MT5Client
        from execution.execution_service import ExecutionService
        from execution.ea_bridge.heartbeat_writer import HeartbeatManager
        from scheduler.graph_cycle_scheduler import GraphCycleScheduler
        from scheduler.news_watcher import NewsWatcher
        from scheduler.trigger_checker import TriggerChecker
        from telegram_bot.bot import TelegramBot
        from analysis.stages.fundamental_stage import FundamentalStage
        from analysis.stages.per_asset_stage import PerAssetStage
        from scheduler.position_guardian import PositionGuardian
        from scheduler.trailing_stop_manager import TrailingStopManager
        from scheduler.edge_strategy_runner import EdgeStrategyRunner
        from scheduler.market_data_scheduler import MarketDataScheduler
        from scheduler.macro_data_scheduler import MacroDataScheduler
        from utils.protocol.event_bus import get_event_bus

        self.event_bus = get_event_bus()
        self.mt5_client = MT5Client(settings=self.settings)
        from execution.health_check import FlakeTolerantHealthChecker
        self.mt5_health_checker = FlakeTolerantHealthChecker(self.mt5_client, ttl_seconds=30.0, grace_seconds=60.0)
        self.market_data_scheduler = MarketDataScheduler(self.settings, mt5_client=self.mt5_client, event_bus=self.event_bus)
        self.macro_data_scheduler = MacroDataScheduler(self.settings)

        exec_cfg = self.settings.get("execution", {})
        adapter_type = exec_cfg.get("adapter_type", "live")
        broker_adapter = None
        if adapter_type == "remote_gateway":
            from execution.broker_adapter import MT5RemoteGatewayAdapter
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

        self.execution_service = ExecutionService(
            self.settings,
            mt5_client=self.mt5_client,
            dry_run=self.dry_run,
            broker_adapter=broker_adapter,
        )
        mt5_common = self.settings.get("execution", {}).get("mt5_common_dir", "")
        self.heartbeat_mgr = HeartbeatManager(mt5_common_path=mt5_common)

        self.edge_strategy_runner = EdgeStrategyRunner(
            self.settings,
            execution_service=self.execution_service,
            market_data_scheduler=self.market_data_scheduler,
            recovery_event=self._recovery_complete,
        )

        self.fundamental_stage = FundamentalStage(self.settings)
        self.per_asset_stage = PerAssetStage(self.settings, mt5_client=self.mt5_client)
        self.fundamental_stage.consent_callback = self.request_fallback_consent
        self.per_asset_stage.consent_callback = self.request_fallback_consent
        self.fundamental_stage.is_fallback_always_approved = lambda: getattr(self, '_fallback_always_approved', False)
        self.per_asset_stage.is_fallback_always_approved = lambda: getattr(self, '_fallback_always_approved', False)
        
        from scheduler.position_exit_reviewer import PositionExitReviewer
        self.position_exit_reviewer = PositionExitReviewer(
            self.settings,
            per_asset_stage=self.per_asset_stage,
            execution_service=self.execution_service,
            recovery_event=self._recovery_complete,
        )
        
        self.position_guardian = PositionGuardian(
            self.settings, 
            execution_service=self.execution_service
        )
        from scheduler.order_reconciler import OrderReconciler
        self.order_reconciler = OrderReconciler(
            self.settings,
            mt5_client=self.mt5_client,
            execution_service=self.execution_service,
            broker_adapter=getattr(self.execution_service, "broker_adapter", None),
            recovery_event=self._recovery_complete,
            shutdown_event=self.shutdown_event,
        )
        from scheduler.active_calendar_poller import ActiveCalendarPoller
        self.active_calendar_poller = ActiveCalendarPoller(self.settings)
        
        self.trailing_stop_manager = TrailingStopManager(
            self.settings,
            execution_service=self.execution_service,
            recovery_event=self._recovery_complete,
        )

        try:
            from scheduler.position_supervisor import PositionSupervisor
            self.position_supervisor = PositionSupervisor(
                mt5_client=self.mt5_client,
                settings=self.settings,
            )
        except Exception as e:
            logger.warning(f"PositionSupervisor initialization failed: {e}")
            self.position_supervisor = None

        from scheduler.digest_slice_scheduler import DigestSliceScheduler
        self.digest_slice_scheduler = DigestSliceScheduler(self.settings)

        self.cycle_scheduler = GraphCycleScheduler(
            self.settings, 
            mt5_client=self.mt5_client,
            fundamental_stage=self.fundamental_stage,
            per_asset_stage=self.per_asset_stage,
            dry_run=self.dry_run,
            recovery_event=self._recovery_complete,
            macro_data_scheduler=self.macro_data_scheduler,
            execution_service=self.execution_service,
        )
        # Wire ActivityLogger to key components
        self.cycle_scheduler._activity_log = self._activity_log

        from agent.turn_lease_manager import SymbolTurnLeaseManager
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

        from scheduler.post_release_analyzer import PostReleaseAnalyzer
        self.post_release_analyzer = PostReleaseAnalyzer(
            self.settings,
            per_asset_stage=self.per_asset_stage,
            fundamental_stage=self.fundamental_stage,
            execution_service=self.execution_service,
            mt5_client=self.mt5_client,
            dry_run=self.dry_run,
        )
        self.active_calendar_poller._news_watcher = self.news_watcher
        self.news_watcher._post_release_analyzer = self.post_release_analyzer
        
        self.trigger_checker = TriggerChecker(
            self.settings, 
            per_asset_stage=self.per_asset_stage,
            execution_service=self.execution_service,
            cycle_scheduler=self.cycle_scheduler,
            recovery_event=self._recovery_complete,
        )

        self.telegram_bot = TelegramBot(
            settings=self.settings,
            execution_service=self.execution_service,
            cycle_scheduler=self.cycle_scheduler,
        )
        self.telegram_bot._activity_log = self._activity_log

        from utils.infra.notifier import AgentNotifier
        self.notifier = AgentNotifier()

        from scheduler.flash_crash_detector import FlashCrashDetector
        self.flash_crash_detector = FlashCrashDetector(
            self.settings,
            execution_service=self.execution_service,
            notifier=self.notifier,
        )
        if hasattr(self.execution_service, 'gate') and self.execution_service.gate:
            self.execution_service.gate.flash_crash_detector = self.flash_crash_detector
        if hasattr(self.execution_service, 'risk_gate') and self.execution_service.risk_gate:
            self.execution_service.risk_gate.flash_crash_detector = self.flash_crash_detector

        # Hot-Reload Risk Parameters (M-4)
        from config.hot_reload import RiskParameterReloader
        settings_yaml_path = os.path.join(os.path.dirname(__file__), "config", "settings.yaml")
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

        # Wire EventBus subscribers for sub-second reactive protection & live observability
        if self.event_bus:
            from utils.protocol.event_bus import TickPriceEvent, OrderStateChangedEvent
            if self.flash_crash_detector and hasattr(self.flash_crash_detector, "on_tick"):
                self.event_bus.subscribe(TickPriceEvent, self.flash_crash_detector.on_tick, priority=10)
            if self.position_guardian and hasattr(self.position_guardian, "on_tick"):
                self.event_bus.subscribe(TickPriceEvent, self.position_guardian.on_tick, priority=8)
            if self.trailing_stop_manager and hasattr(self.trailing_stop_manager, "on_tick"):
                self.event_bus.subscribe(TickPriceEvent, self.trailing_stop_manager.on_tick, priority=5)

            # Observability live feed forwarder to dashboard WebSockets
            try:
                from logging_observability.dashboard.api import broadcast_live_event

                async def _on_live_tick(evt: TickPriceEvent):
                    await broadcast_live_event("tick", {
                        "symbol": evt.symbol,
                        "bid": evt.bid,
                        "ask": evt.ask,
                        "spread": evt.spread,
                        "timestamp": evt.timestamp.isoformat() if hasattr(evt.timestamp, "isoformat") else str(evt.timestamp),
                    })

                async def _on_live_order(evt: OrderStateChangedEvent):
                    await broadcast_live_event("order_state_change", {
                        "order_id": evt.order_id,
                        "symbol": evt.symbol,
                        "old_state": evt.old_state,
                        "new_state": evt.new_state,
                        "details": evt.details,
                        "timestamp": evt.timestamp.isoformat() if hasattr(evt.timestamp, "isoformat") else str(evt.timestamp),
                    })

                self.event_bus.subscribe(TickPriceEvent, _on_live_tick, priority=1)
                self.event_bus.subscribe(OrderStateChangedEvent, _on_live_order, priority=1)
                logger.info("  [OK] EventBus live feed wired to Dashboard WebSocket broadcast")
            except Exception as ws_err:
                logger.debug(f"Dashboard WebSocket EventBus subscriber wiring note: {ws_err}")

            from utils.protocol.event_bus import CircuitBreakerEvent, RiskBreachEvent
            async def _on_circuit_breaker(evt: CircuitBreakerEvent):
                logger.warning(f"[EventBus] Circuit breaker received from {evt.component}: {evt.reason} (active={evt.is_active})")
                if evt.is_active and self.execution_service and hasattr(self.execution_service, "trigger_circuit_breaker"):
                    try:
                        await self.execution_service.trigger_circuit_breaker(f"{evt.component}: {evt.reason}")
                    except Exception as cb_err:
                        logger.error(f"[EventBus] Failed to dispatch circuit breaker to ExecutionService: {cb_err}")
                try:
                    from logging_observability.dashboard.api import broadcast_live_event
                    await broadcast_live_event("circuit_breaker", {
                        "component": evt.component,
                        "reason": evt.reason,
                        "is_active": evt.is_active,
                        "cooldown_seconds": evt.cooldown_seconds,
                        "timestamp": evt.timestamp.isoformat() if hasattr(evt.timestamp, "isoformat") else str(evt.timestamp),
                    })
                except Exception as ws_err:
                    logger.debug(f"Circuit breaker websocket broadcast error: {ws_err}")

            async def _on_risk_breach(evt: RiskBreachEvent):
                logger.warning(f"[EventBus] Risk breach received: {evt.breach_type} (severity={evt.severity})")
                try:
                    from logging_observability.dashboard.api import broadcast_live_event
                    await broadcast_live_event("risk_breach", {
                        "breach_type": evt.breach_type,
                        "symbol": evt.symbol,
                        "severity": evt.severity,
                        "details": evt.details,
                        "timestamp": evt.timestamp.isoformat() if hasattr(evt.timestamp, "isoformat") else str(evt.timestamp),
                    })
                except Exception as ws_err:
                    logger.debug(f"Risk breach websocket broadcast error: {ws_err}")

            self.event_bus.subscribe(CircuitBreakerEvent, _on_circuit_breaker, priority=10)
            self.event_bus.subscribe(RiskBreachEvent, _on_risk_breach, priority=10)
            logger.info("  [OK] EventBus CircuitBreakerEvent and RiskBreachEvent subscribed for safety protection and WebSocket broadcast")


        # Berikan recovery_complete event ke cycle_scheduler agar bisa menunggu
        if hasattr(self, 'cycle_scheduler') and self.cycle_scheduler is not None:
            self.cycle_scheduler._recovery_complete_event = self._recovery_complete

        from scheduler.alpha_discovery_scheduler import AlphaDiscoveryScheduler
        self.alpha_discovery_scheduler = AlphaDiscoveryScheduler(
            self.settings,
            recovery_event=self._recovery_complete,
            notifier=self.notifier,
            edge_strategy_runner=self.edge_strategy_runner,
        )

        from scheduler.strategy_synthesis_scheduler import StrategySynthesisScheduler
        self.strategy_synthesis_scheduler = StrategySynthesisScheduler(
            self.settings,
            recovery_event=self._recovery_complete,
            notifier=self.notifier,
            edge_strategy_runner=self.edge_strategy_runner,
        )

        from analysis.memory.background_review import BackgroundReviewEngine
        self.background_review_engine = BackgroundReviewEngine(self.settings)

        from scheduler.playbook_curator import PlaybookCurator
        self.playbook_curator = PlaybookCurator(self.settings)

        # Initialize and load active plugins
        try:
            from plugins.loader import PluginLoader
            self.plugin_loader = PluginLoader()
            plugins_dir = os.path.join(os.path.dirname(__file__), "plugins")
            loaded_plugins = self.plugin_loader.load_plugins_from_directory(plugins_dir)
            if loaded_plugins:
                logger.info(f"Loaded {len(loaded_plugins)} plugins: {', '.join(p.name for p in loaded_plugins)}")
        except Exception as e:
            logger.warning(f"Plugin initialization error: {e}")

        logger.info("All components initialized")

    async def publish_tick(self, symbol: str, bid: float, ask: float, last: float = 0.0, spread: float = 0.0) -> None:
        """Publish a live TickPriceEvent to the centralized EventBus."""
        if not self.event_bus:
            return
        from utils.protocol.event_bus import TickPriceEvent
        from datetime import datetime, timezone
        event = TickPriceEvent(
            symbol=symbol.upper(),
            bid=bid,
            ask=ask,
            last=last or ((bid + ask) / 2.0 if bid and ask else bid or ask),
            spread=spread or (round(ask - bid, 5) if ask > bid else 0.0),
            timestamp=datetime.now(timezone.utc),
        )
        await self.event_bus.publish(event)

    async def request_fallback_consent(self, prompt_text: str) -> bool:
        """
        Coordinate fallback consent request across CLI and Telegram channels.
        Returns True if approved (single cycle or persistent), False if rejected.
        """
        logger.warning(f"Fallback consent requested: {prompt_text}")
        
        # Event for CLI prompt synchronization
        cli_event = asyncio.Event()
        cli_result = {"approved": False, "always": False}
        
        def cli_prompt():
            import sys
            import time
            if not sys.stdin.isatty():
                # If non-interactive terminal, block thread to prevent premature completion
                # from canceling concurrent Telegram prompt task
                while not cli_event.is_set():
                    time.sleep(1)
                return

            print(f"\n[FALLBACK REQUIRED] {prompt_text}")
            print("1. Approve (Single Cycle)")
            print("2. Approve (Always / Persistent)")
            print("3. Reject")
            sys.stdout.flush()
            if sys.platform == "win32":
                try:
                    import msvcrt
                    chars = []
                    while not cli_event.is_set():
                        if msvcrt.kbhit():
                            ch = msvcrt.getwche()
                            if ch in ('\r', '\n'):
                                ans = "".join(chars).strip()
                                chars = []
                                if ans == '1':
                                    cli_result["approved"] = True
                                    cli_result["always"] = False
                                    return
                                elif ans == '2':
                                    cli_result["approved"] = True
                                    cli_result["always"] = True
                                    return
                                elif ans == '3':
                                    cli_result["approved"] = False
                                    return
                                else:
                                    print("\nPlease select 1, 2, or 3: ", end="")
                                    sys.stdout.flush()
                            else:
                                chars.append(ch)
                        else:
                            time.sleep(0.1)
                    return
                except Exception:
                    pass

            while not cli_event.is_set():
                try:
                    ans = sys.stdin.readline()
                    if not ans:  # EOF
                        while not cli_event.is_set():
                            time.sleep(1)
                        return
                    ans = ans.strip()
                    if ans == '1':
                        cli_result["approved"] = True
                        cli_result["always"] = False
                        return
                    elif ans == '2':
                        cli_result["approved"] = True
                        cli_result["always"] = True
                        return
                    elif ans == '3':
                        cli_result["approved"] = False
                        return
                    else:
                        print("Please select 1, 2, or 3: ", end="")
                        sys.stdout.flush()
                except Exception:
                    # Hold thread if stdin read fails
                    while not cli_event.is_set():
                        time.sleep(1)
                    return
        
        # Execute CLI prompt in separate thread to avoid blocking event loop
        cli_task = asyncio.create_task(asyncio.to_thread(cli_prompt))
        
        # Execute Telegram prompt
        tg_event = asyncio.Event()
        tg_result = {"approved": False, "always": False}
        if self.telegram_bot:
            bot = self.telegram_bot
            async def wait_for_tg():
                await bot.request_fallback_consent(prompt_text, tg_event, tg_result)
                await tg_event.wait()
            tg_task = asyncio.create_task(wait_for_tg())
        else:
            # Dummy task when Telegram bot is unavailable
            async def dummy_tg():
                await asyncio.sleep(86400)
            tg_task = asyncio.create_task(dummy_tg())

        # Wait for first respondent with 5 minute timeout (300s)
        done, pending = await asyncio.wait(
            [cli_task, tg_task, asyncio.create_task(self.shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
            timeout=300.0
        )

        # Cancel remaining pending tasks
        for task in pending:
            task.cancel()

        if self.shutdown_event.is_set():
            return False

        # Set event to complete cli_prompt if still active
        cli_event.set()
        
        if not done:
            # Timeout reached
            approved = False
            always = False
            source = "Timeout (5 minutes)"
            print(f"\n[FALLBACK] Approval timeout reached (5 minutes). Default: Rejected.")
            if self.telegram_bot:
                asyncio.create_task(self.telegram_bot.send_notification(
                    "⏳ Fallback approval timed out (5 minutes). Automated decision: *Rejected*."
                ))
        elif tg_event.is_set():
            approved = tg_result["approved"]
            always = tg_result["always"]
            source = "Telegram"
            print(f"\n[FALLBACK] Decision received from Telegram: {'Approved' if approved else 'Rejected'}")
        else:
            approved = cli_result["approved"]
            always = cli_result["always"]
            source = "CLI"
            if self.telegram_bot:
                asyncio.create_task(self.telegram_bot.send_notification(
                    f"ℹ️ Fallback decision received from CLI: {'Approved' if approved else 'Rejected'}"
                ))

        if approved and always:
            self._fallback_always_approved = True
            logger.info(f"Fallback APPROVED (Persistent) via {source}.")
        elif approved:
            logger.info(f"Fallback APPROVED (Single Cycle) via {source}.")
        else:
            logger.info(f"Fallback REJECTED via {source}.")

        return approved

    async def _post_restart_recovery(self):
        """
        Tasks to run after restart to ensure consistency:
        1. Sync positions dari MT5 (detect posisi yang ditutup saat kita offline)
        2. Check apakah ada analysis yang sudah expired yang perlu di-refresh
        3. Reset Gemini rate limiter counters jika hari baru
        """
        from database.db import get_session
        logger.info("[Recovery] Starting post-restart recovery tasks...")
        
        try:
            if self.execution_service:
                try:
                    await self.execution_service._restore_executed_ids_from_db()
                except Exception as e:
                    logger.error(f"[Recovery] Failed to restore executed IDs: {e}")
                
            max_wait = 120
            wait_interval = 10
            elapsed = 0
            
            async def _check_broker_connected() -> bool:
                if self.execution_service and hasattr(self.execution_service, "broker_adapter") and self.execution_service.broker_adapter:
                    adapter = self.execution_service.broker_adapter
                    if hasattr(adapter, "ensure_connected"):
                        return await adapter.ensure_connected()
                    if hasattr(adapter, "is_connected"):
                        return await adapter.is_connected()
                if self.mt5_client:
                    return await self.mt5_client.is_connected()
                return True

            while elapsed < max_wait:
                if await _check_broker_connected():
                    logger.info(f"[Recovery] Broker/MT5 connected after {elapsed}s")
                    break
                logger.info(f"[Recovery] Waiting for Broker/MT5... ({elapsed}s/{max_wait}s)")
                await asyncio.sleep(wait_interval)
                elapsed += wait_interval
                
            if not await _check_broker_connected():
                logger.error("[Recovery] Broker/MT5 failed to connect within timeout — entering degraded mode")
                self._mt5_degraded = True
                try:
                    if self.telegram_bot:
                        await self.telegram_bot.send_notification(
                            "⚠️ MT5 tidak terhubung setelah restart!\n"
                            "Agent berjalan dalam mode degraded.\n"
                            "Position monitoring tetap berjalan; eksekusi baru ditunda."
                        )
                except Exception:
                    pass
            else:
                self._mt5_degraded = False
                # 1. Sync positions
                if self.execution_service:
                    for attempt in range(3):
                        try:
                            await self.execution_service.sync_positions()
                            logger.info(f"[Recovery] Position sync successful")
                            break
                        except Exception as e:
                            logger.warning(f"[Recovery] Sync attempt {attempt+1} failed: {e}")
                            await asyncio.sleep(15)

                    # 1a. Reconcile in-flight orders stuck during crash/restart (C-4)
                    try:
                        inflight_res = await self.execution_service.reconcile_inflight_orders()
                        if inflight_res.get("total", 0) > 0:
                            logger.info(f"[Recovery] In-flight orders processed: {inflight_res}")
                    except Exception as inflight_err:
                        logger.error(f"[Recovery] In-flight order reconciliation failed (non-fatal): {inflight_err}")

                # 1b. Check Friday close protection if it's Friday and past 20:00 UTC
                now = datetime.now(timezone.utc)
                if now.weekday() == 4 and now.hour >= 20:
                    logger.info('[Recovery] Friday past 20:00 UTC detected. Running gap protection check...')
                    try:
                        if self.position_guardian:
                            res = await self.position_guardian.check_friday_close_protection()
                            alerted = res.get('positions_alerted', 0)
                            if alerted > 0:
                                logger.info(f'[Recovery] Friday protection alerted on {alerted} positions.')
                        else:
                            logger.warning('[Recovery] position_guardian not initialized, skipping Friday check.')
                    except Exception as e:
                        logger.error(f'[Recovery] Friday protection check failed: {e}')

                # 1c. Initial Market Data Synchronization & Indicator Warmup
                if self.market_data_scheduler:
                    try:
                        logger.info("[Recovery] Running initial market data synchronization and indicator warmup...")
                        await self.market_data_scheduler.sync_now()
                        logger.info("[Recovery] Initial market data warmup complete.")
                    except Exception as e:
                        logger.warning(f"[Recovery] Initial market data sync failed (non-fatal): {e}")
            
            # Signal to cycle scheduler & fast runners that recovery is complete
            self._recovery_complete.set()
            logger.info("[Recovery] Position sync and market data warmup done: _recovery_complete event set.")

            _recovery_cycle_dispatched = False
            from database.db import get_session
            from database.models import CyclePerformance, NewsDigest, FundamentalBrief
            from analysis.prefetch.news_digest import NewsDigestProcessor
            from sqlalchemy import select

            # Harmonized Catch-up & Brief Expiry Check
            try:
                sched_cfg = self.settings.get('trading', {}).get('schedule', {})
                catch_up_enabled = sched_cfg.get('catch_up_missed_cycles', True)
                overdue_multiplier = float(sched_cfg.get('catch_up_overdue_multiplier', 1.5))
                cycle_hours = float(sched_cfg.get('analysis_cycle_hours', 8.0))
                data_quality_cfg = self.settings.get('data_quality', {})
                max_brief_age = float(data_quality_cfg.get('max_brief_age_analysis_hours', 12.0))
                effective_threshold = min(cycle_hours * overdue_multiplier, max_brief_age)
                tz_name = sched_cfg.get('timezone', 'Asia/Jakarta')
                cycle_times_raw = sched_cfg.get('cycle_times_local') or ["07:00", "15:00", "20:00"]

                if not catch_up_enabled:
                    logger.info(
                        '[Recovery] catch_up_missed_cycles=false — melewati pengecekan catch-up. '
                        'Siklus berikutnya akan jalan sesuai jadwal jam tetap (cycle_times_local).'
                    )
                else:
                    async with get_session() as session:
                        last_cycle = (await session.execute(
                            select(CyclePerformance).order_by(CyclePerformance.cycle_at.desc()).limit(1)
                        )).scalar_one_or_none()
                        
                        brief = (await session.execute(
                            select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                        )).scalar_one_or_none()

                        dt_now = datetime.now(timezone.utc)
                        hours_since_last = None
                        cycle_at = None
                        if last_cycle and last_cycle.cycle_at:
                            cycle_at = last_cycle.cycle_at
                            if cycle_at.tzinfo is None:
                                cycle_at = cycle_at.replace(tzinfo=timezone.utc)
                            hours_since_last = (dt_now - cycle_at).total_seconds() / 3600

                        brief_age = None
                        brief_expired = False
                        if brief and brief.generated_at:
                            gen_at = brief.generated_at
                            if gen_at.tzinfo is None:
                                gen_at = gen_at.replace(tzinfo=timezone.utc)
                            brief_age = (dt_now - gen_at).total_seconds() / 3600
                            brief_expired = brief_age > max_brief_age
                        else:
                            brief_expired = True

                        from utils.scheduling.wall_clock import parse_time_list, previous_occurrence, get_tzinfo
                        most_recent_target_utc = None
                        try:
                            times = parse_time_list(cycle_times_raw)
                            most_recent_target_utc = previous_occurrence(times, tz_name, dt_now)
                        except Exception as e:
                            logger.debug(f"[Recovery] Failed calculating previous occurrence: {e}")

                        needs_recovery = False
                        reason = ""

                        if not last_cycle:
                            if brief_expired:
                                needs_recovery = True
                                reason = "Belum pernah ada siklus yang berjalan / Fundamental Brief belum tersedia"
                        elif most_recent_target_utc is not None and cycle_at is not None:
                            tolerance = timedelta(minutes=90)
                            cycle_covered = cycle_at >= (most_recent_target_utc - tolerance)
                            if not cycle_covered:
                                tz = get_tzinfo(tz_name)
                                target_local_str = most_recent_target_utc.astimezone(tz).strftime('%Y-%m-%d %H:%M')
                                last_local_str = cycle_at.astimezone(tz).strftime('%Y-%m-%d %H:%M')
                                needs_recovery = True
                                reason = f"Jadwal sesi {target_local_str} ({tz_name}) terlewat (siklus terakhir: {last_local_str})"
                            elif brief_expired:
                                needs_recovery = True
                                if brief_age is not None:
                                    reason = f"Fundamental Brief sudah kedaluwarsa ({brief_age:.1f}h > {max_brief_age:.1f}h)"
                                else:
                                    reason = "Fundamental Brief belum tersedia / tidak valid"
                        else:
                            if hours_since_last is not None and hours_since_last > effective_threshold:
                                needs_recovery = True
                                reason = f"Siklus terakhir {hours_since_last:.1f}h lalu (> ambang {effective_threshold:.1f}h)"
                            elif brief_expired:
                                needs_recovery = True
                                reason = "Fundamental Brief sudah kedaluwarsa / belum tersedia"

                        if needs_recovery:
                            logger.warning(
                                f"[Recovery] {reason}. Menjadwalkan SATU siklus pemulihan sekarang."
                            )
                            if not _recovery_cycle_dispatched and self.cycle_scheduler:
                                self._create_background_task(self.cycle_scheduler.run_once(forced=True), name="recovery_cycle")
                                _recovery_cycle_dispatched = True
                        else:
                            if hours_since_last is not None:
                                brief_age_str = f"age={brief_age:.1f}h" if brief_age is not None else "no brief"
                                logger.info(
                                    f"[Recovery] Siklus terakhir {hours_since_last:.1f}h lalu dan Fundamental Brief masih valid "
                                    f"({brief_age_str} <= {max_brief_age:.1f}h). Tidak perlu catch-up; siklus berikutnya mengikuti jadwal."
                                )
                            else:
                                logger.info(
                                    "[Recovery] Belum ada siklus tercatat di DB (instalasi baru). Menunggu jadwal pertama."
                                )
            except Exception as e:
                logger.error(f'[Recovery] Cycle and brief catch-up check failed: {e}')
            
            # Check news digest freshness
            try:
                async with get_session() as session:
                    last_digest = (await session.execute(
                        select(NewsDigest).order_by(NewsDigest.generated_at.desc()).limit(1)
                    )).scalar_one_or_none()
                    
                    # Assume generated_at is utc naive or aware
                    dt_now = datetime.now(timezone.utc)
                    is_stale = True
                    if last_digest and last_digest.generated_at:
                        l_gen = last_digest.generated_at
                        if l_gen.tzinfo is None:
                            l_gen = l_gen.replace(tzinfo=timezone.utc)
                        is_stale = (dt_now - l_gen).total_seconds() > 4 * 3600
                    
                    if is_stale:
                        logger.info('[Recovery] News digest stale/missing, generating fresh digest...')
                        processor = NewsDigestProcessor(self.settings)
                        async with get_session() as digest_session:
                            await processor.create_news_digest(digest_session, hours_back=12)
            except Exception as e:
                logger.error(f'[Recovery] News digest recovery failed: {e}')
            
            # 3. Send recovery notification
            try:
                await asyncio.sleep(30)  # Wait for Telegram bot to be ready
                if self.telegram_bot:
                    open_pos_count = 0
                    try:
                        if self.execution_service and getattr(self.execution_service, 'mt5', None):
                            positions = await self.execution_service.mt5.get_open_positions()
                            open_pos_count = len(positions) if positions else 0
                    except Exception:
                        pass
                    
                    await self.telegram_bot.send_notification(
                        f"🔄 *Agent Restarted Successfully*\n\n"
                        f"All systems online.\n"
                        f"Open positions synced: {open_pos_count}\n"
                        f"EA dead-man's switch: Reset\n\n"
                        f"Use /status to verify all systems."
                    )
            except Exception as e:
                logger.debug(f"Recovery notification failed: {e}")
        finally:
            logger.info("[Recovery] Post-restart recovery complete")
            # Signal to cycle scheduler that startup recovery is complete.
            self._recovery_complete.set()
            logger.info("[Recovery] _recovery_complete event set — cycle scheduler may now start.")

    def _register_signals(self):
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
                except (NotImplementedError, RuntimeError):
                    # Windows: add_signal_handler not supported for all signals
                    signal.signal(sig, lambda s, f, n=sig.name: _signal_handler(n))
            else:
                signal.signal(sig, lambda s, f, n=sig.name: _signal_handler(n))

        # SIGHUP (systemd ExecReload / config reload, Unix only)
        if hasattr(signal, "SIGHUP"):
            def _sighup_handler():
                logger.info("SIGHUP received — reloading configuration...")
                try:
                    from config.settings import load_all_config
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
                    except (NotImplementedError, RuntimeError):
                        signal.signal(sighup, lambda s, f: _sighup_handler())
                else:
                    signal.signal(sighup, lambda s, f: _sighup_handler())

    async def start(self):
        """
        Full startup sequence — blocks until shutdown.
        """
        import sys
        reconfig = getattr(sys.stdout, 'reconfigure', None)
        if callable(reconfig) and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
            try:
                reconfig(encoding='utf-8')
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
        from agent.monitors.startup_watchdog import global_startup_watchdog
        global_startup_watchdog.start()

        # Register signal handlers
        self._register_signals()

        # Initialize components
        self._init_components()

        # Connect MT5 / Broker Gateway Adapter
        try:
            connected = False
            from execution.broker_adapter import MT5LiveAdapter
            custom_adapter = getattr(self.execution_service, "broker_adapter", None) if self.execution_service else None
            if custom_adapter and not isinstance(custom_adapter, MT5LiveAdapter):
                connected = await custom_adapter.ensure_connected()
                if connected:
                    logger.info(f"Broker Adapter ({type(custom_adapter).__name__}) connected successfully")
                else:
                    logger.warning(f"Broker Adapter ({type(custom_adapter).__name__}) connection failed — live execution disabled")
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
            from agent.monitors.startup_watchdog import run_cold_start_preflight
            preflight = await run_cold_start_preflight(self)
            logger.info(f"[Preflight] Cold-start verification: broker_ping={preflight.get('broker_ping')}, "
                        f"positions_reconciled={preflight.get('positions_reconciled')}, "
                        f"ready={preflight.get('ready')}")
        except Exception as preflight_err:
            logger.warning(f"[Preflight] Cold-start pre-flight note (non-fatal): {preflight_err}")

        # Launch all concurrent tasks
        logger.info("Launching concurrent tasks...")
        tasks_list: list[asyncio.Task] = []

        def _launch_task(name: str, runner: Callable, task_name: str) -> asyncio.Task:
            if hasattr(self, "task_registry") and self.task_registry:
                try:
                    self.task_registry.register(name, runner)
                except Exception:
                    pass
            t = asyncio.create_task(_run_with_restart(name, runner, self.shutdown_event), name=task_name)
            tasks_list.append(t)
            return t

        if self.market_data_scheduler and hasattr(self.market_data_scheduler, "start"):
            _launch_task("MarketDataScheduler", self.market_data_scheduler.start, "market_data_scheduler")
        if self.macro_data_scheduler and hasattr(self.macro_data_scheduler, "start"):
            _launch_task("MacroDataScheduler", self.macro_data_scheduler.start, "macro_data_scheduler")
        if self.edge_strategy_runner and hasattr(self.edge_strategy_runner, "start"):
            _launch_task("EdgeStrategyRunner", self.edge_strategy_runner.start, "edge_strategy_runner")
        if self.cycle_scheduler:
            _launch_task("CycleScheduler", self.cycle_scheduler.start, "cycle_scheduler")
            _launch_task("DailyReportScheduler", self.cycle_scheduler.run_scheduled_reports_loop, "daily_report_scheduler")
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
            _launch_task("StrategySynthesisScheduler", self.strategy_synthesis_scheduler.start, "strategy_synthesis_scheduler")
        if hasattr(self, "background_review_engine") and self.background_review_engine:
            _launch_task("BackgroundReviewEngine", self.background_review_engine.run, "background_review_engine")
        if hasattr(self, "playbook_curator") and self.playbook_curator:
            _launch_task("PlaybookCurator", self.playbook_curator.start, "playbook_curator")

        if self.telegram_bot:
            self._tg_task = _launch_task("TelegramBot", self.telegram_bot.start, "telegram_bot")

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
        from database.db import get_session
        interval = int(self.settings.get("trading", {}).get("risk", {}).get("flash_crash", {}).get("check_interval_seconds", 30))
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
        logger.info('What-If resolver started (interval: 1h)')
        
        from analysis.memory.outcome_linker import OutcomeLinker
        from database.db import get_session
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
        await run_paper_trade_monitor(self)


    async def _run_micro_playbook_compiler_loop(self) -> None:
        """
        Autonomous micro-playbook compilation loop.
        Evaluates trade memories and promotes high-performing strategies (>=3 consecutive wins or >=65% win rate).
        """
        from analysis.memory.skill_evolution import MicroPlaybookCompiler
        from database.db import get_session
        compiler = MicroPlaybookCompiler(self.settings)
        check_interval_seconds = 21600  # Run every 6 hours
        logger.info("Micro-playbook compiler loop started (interval: 6h)")
        while not self.shutdown_event.is_set():
            try:
                async with get_session() as session:
                    promoted = await compiler.evaluate_and_compile(session, settings=self.settings)
                    if promoted:
                        logger.info(f"[MicroPlaybookCompiler] Promoted {len(promoted)} autonomous micro-playbooks: {promoted}")
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
        from analysis.memory.skill_curator import SkillCurator
        from database.db import get_session
        curator = SkillCurator(self.settings)
        check_interval_seconds = 86400  # Run every 24 hours
        logger.info("Skill curator loop started (interval: 24h)")
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

    async def _run_dashboard(self):
        """Run the FastAPI dashboard server as an asyncio task with bind-retry resilience."""
        from logging_observability.dashboard.api import run_dashboard_async, set_dashboard_dependencies
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

    async def _run_position_sync_loop(self):
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
                await asyncio.wait_for(
                    self.shutdown_event.wait(), timeout=sync_interval
                )
            except asyncio.TimeoutError:
                pass

    async def _run_scraper_loop(self) -> None:
        await run_scraper_loop(self)

    async def _run_risk_parameter_reloader(self) -> None:
        if hasattr(self, "risk_parameter_reloader") and self.risk_parameter_reloader:
            await self.risk_parameter_reloader.watch_and_reload(self.shutdown_event)


    async def _run_mt5_health_monitor(self):
        """Monitor MT5 connection health and auto-heal market data on reconnect."""
        consecutive_failures = 0
        max_failures_before_alert = 1
        was_disconnected = False
        
        while not self.shutdown_event.is_set():
            await asyncio.sleep(60)  # Check every 60s for faster reconnection recovery
            try:
                if self.mt5_health_checker is not None:
                    is_conn = await self.mt5_health_checker.is_healthy()
                elif self.execution_service and hasattr(self.execution_service, "broker_adapter") and self.execution_service.broker_adapter:
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
                    logger.warning(
                        f"MT5 health check failed ({consecutive_failures}/{max_failures_before_alert})"
                    )
                    if consecutive_failures == max_failures_before_alert:
                        if self.mt5_health_checker is not None:
                            self.mt5_health_checker.record_failure()
                        from utils.infra.notifier import AgentNotifier
                        await AgentNotifier().send_critical(
                            f"🔌 <b>MT5 Connection Lost</b>\n"
                            f"MT5 has been disconnected for ~{consecutive_failures} minutes.\n"
                            f"⚠️ EA dead-man switch may trigger in ~2 minutes if not reconnected!\n"
                            f"Price data is stale. Analysis quality is degraded.\n"
                            f"Please check MT5 terminal immediately!"
                        )
                else:
                    if was_disconnected:
                        # Auto-Healing: Reconnection detected!
                        logger.info("[MT5HealthMonitor] MT5 reconnected! Triggering instant auto-healing market data sync...")
                        was_disconnected = False
                        if self.mt5_health_checker is not None:
                            self.mt5_health_checker.record_success()
                        if self.market_data_scheduler:
                            asyncio.create_task(self.market_data_scheduler.sync_now())
                        try:
                            from utils.infra.notifier import AgentNotifier
                            await AgentNotifier().send_info("✅ <b>MT5 Reconnected</b> — Market data auto-healing sync dispatched.")
                        except Exception:
                            pass
                    consecutive_failures = 0  # Reset on successful connection
            except Exception as e:
                logger.debug(f"MT5 health monitor error (non-fatal): {e}")

    async def _run_friday_close_monitor(self):
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
        import asyncio
        if hasattr(self, "_recovery_complete") and self._recovery_complete:
            try:
                await asyncio.wait_for(self._recovery_complete.wait(), timeout=180.0)
            except asyncio.TimeoutError:
                pass
        guardian_cfg = self.settings.get("trading", {}).get("position_guardian", {})
        interval = int(guardian_cfg.get("check_interval_seconds") or self.settings.get("trading", {}).get("position_guardian_interval_seconds", 60))
        while not self.shutdown_event.is_set():
            try:
                if self.position_guardian:
                    await self.position_guardian.check_and_protect()
            except Exception as e:
                logger.debug(f'PositionGuardian check failed (non-fatal): {e}')
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _run_floating_drawdown_monitor(self):
        """Monitor floating drawdown."""
        await run_floating_drawdown_monitor(self)

    async def _run_db_health_check(self):
        """Monitor Database connection pool health."""
        await run_db_health_check(self)


    async def _shutdown(self):
        """Graceful shutdown sequence."""
        logger.info("=" * 62)
        logger.info("Shutdown sequence starting...")

        try:
            from database.db import get_session
            from database.models import Position
            from sqlalchemy import select
            import json
            
            async with get_session() as session:
                open_positions = (await session.execute(
                    select(Position).where(Position.status == "open")
                )).scalars().all()

                try:
                    from database.event_store import TradingEventStore
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
                os.makedirs('data', exist_ok=True)
                snapshot = {
                    'shutdown_at': datetime.now(timezone.utc).isoformat(),
                    'open_positions': [
                        {
                            'ticket': p.mt5_ticket,
                            'symbol': p.symbol,
                            'direction': p.direction,
                            'entry': p.entry_price,
                            'sl': p.sl,
                            'tp': p.tp
                        }
                        for p in open_positions
                    ]
                }
                
                with open('data/last_shutdown_snapshot.json', 'w') as f:
                    json.dump(snapshot, f, indent=2)
                logger.info(f'Shutdown snapshot saved: {len(open_positions)} open positions')
                
                if open_positions:
                    pos_summary = "\n".join([
                        f"• {p.symbol} {p.direction.upper()} {p.volume}L @ {p.entry_price} (SL:{p.sl})"
                        for p in open_positions
                    ])
                    if self.telegram_bot:
                        await self.telegram_bot.send_notification(
                            f"⚠️ *Agent SHUTDOWN dengan posisi terbuka:*\n{pos_summary}\n\n"
                            f"EA Dead-Man's Switch akan memproteksi posisi ini.\n"
                            f"MT5 terminal JANGAN ditutup!"
                        )
        except Exception as e:
            logger.warning(f"Shutdown position check/snapshot failed: {e}")

        # Stop schedulers
        import inspect
        for comp, name in [
            (self.cycle_scheduler,  "CycleScheduler"),
            (self.news_watcher,     "NewsWatcher"),
            (self.digest_slice_scheduler, "DigestSliceScheduler"),
            (self.active_calendar_poller, "ActiveCalendarPoller"),
            (self.trigger_checker,  "TriggerChecker"),
            (self.heartbeat_mgr,    "HeartbeatManager"),
            (self.position_supervisor, "PositionSupervisor"),
            (self.position_exit_reviewer, 'PositionExitReviewer'),
            (self.position_guardian, "PositionGuardian"),
            (self.order_reconciler, "OrderReconciler"),
            (self.trailing_stop_manager, "TrailingStopManager"),
            (self.edge_strategy_runner, "EdgeStrategyRunner"),
            (self.market_data_scheduler, "MarketDataScheduler"),
            (self.macro_data_scheduler,  "MacroDataScheduler"),
            (self.post_release_analyzer, "PostReleaseAnalyzer"),
            (self.alpha_discovery_scheduler, "AlphaDiscoveryScheduler"),
            (getattr(self, "strategy_synthesis_scheduler", None), "StrategySynthesisScheduler"),
            (getattr(self, "background_review_engine", None), "BackgroundReviewEngine"),
            (getattr(self, "playbook_curator", None), "PlaybookCurator"),
            (self._active_scraper_runner, "ActiveScraperRunner"),
            (getattr(self, "execution_service", None), "ExecutionService"),
            (getattr(self, "mt5_health_checker", None), "MT5HealthChecker"),
        ]:
            try:
                if comp and hasattr(comp, "stop"):
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

        # Notify Telegram admin
        try:
            if self.telegram_bot:
                await self.telegram_bot.send_notification(
                    "🔴 *Agent stopped.* Graceful shutdown complete."
                )
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
            if hasattr(self, 'mt5_client') and self.mt5_client:
                await asyncio.wait_for(self.mt5_client.disconnect(), timeout=5.0)
                logger.info("  [OK] MT5 disconnected")
        except Exception as e:
            logger.warning(f"  [WARN] MT5 disconnect error or timeout: {e}")

        # Stop EventBus workers
        if hasattr(self, 'event_bus') and self.event_bus and hasattr(self.event_bus, 'stop_workers'):
            try:
                self.event_bus.stop_workers()
                logger.info("  [OK] EventBus workers stopped")
            except Exception as e:
                logger.warning(f"  [WARN] EventBus stop workers error: {e}")

        # Close DB pool
        try:
            await close_db()
            logger.info("  [OK] DB connection pool closed")
        except Exception as e:
            logger.warning(f"  [WARN] DB close error: {e}")

        # Shutdown Telegram bot after all notifications are sent
        if hasattr(self, '_tg_task') and self._tg_task and not self._tg_task.done():
            self._tg_task.cancel()
            try:
                await asyncio.wait_for(self._tg_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Cancel and await residual background tasks
        if hasattr(self, '_background_tasks') and self._background_tasks:
            pending_bg = [t for t in self._background_tasks if not t.done()]
            for t in pending_bg:
                t.cancel()
            if pending_bg:
                await asyncio.gather(*pending_bg, return_exceptions=True)
                logger.info("  [OK] Residual background tasks cancelled")

        logger.info("Shutdown complete. Goodbye.")
        logger.info("=" * 62)

    async def _send_startup_notification(self):
        """Send startup notification to Telegram admin (best-effort)."""
        try:
            await asyncio.sleep(5)  # Wait for bot to be online
            if self.telegram_bot:
                env  = self.settings.get("environment", "dev")
                assets = ", ".join(
                    self.settings.get("trading", {}).get("asset_universe", [])
                )
                now  = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
                await self.telegram_bot.send_notification(
                    f"🟢 *Agent Online*\n\n"
                    f"Environment: `{env}`\n"
                    f"Assets: {assets}\n"
                    f"Started: {now}\n\n"
                    f"Use /status for live dashboard."
                )
        except Exception as e:
            logger.debug(f"Startup notification failed: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

PID_FILE = os.path.join(os.getenv("LOG_DIR", "logs"), "trading_agent.pid")

def release_single_instance_lock():
    """Explicitly release single instance lock file."""
    try:
        current_pid = os.getpid()
        should_remove = False
        if os.path.exists(PID_FILE):
            with open(PID_FILE, "r", encoding="utf-8") as f:
                if f.read().strip() == str(current_pid):
                    should_remove = True
            if should_remove and os.path.exists(PID_FILE):
                os.remove(PID_FILE)
    except Exception:
        pass

def acquire_single_instance_lock() -> bool:
    """
    Ensure only one instance of TradingAgent runs at a time.
    Returns True if lock acquired, False if another instance is actively running.
    """
    import psutil
    import atexit
    current_pid = os.getpid()
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    existing_pid = int(content)
                    if existing_pid != current_pid and psutil.pid_exists(existing_pid):
                        try:
                            proc = psutil.Process(existing_pid)
                            if proc.is_running() and "python" in proc.name().lower():
                                logger.warning(
                                    f"[LOCK] Another instance of TradingAgent is already running (PID: {existing_pid}). "
                                    f"Aborting startup of PID {current_pid} to prevent port/MT5/Telegram conflicts."
                                )
                                return False
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
        except Exception as e:
            logger.debug(f"[LOCK] Error inspecting PID file: {e}")

    try:
        os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(current_pid))
        
        atexit.register(release_single_instance_lock)
        return True
    except Exception as e:
        logger.warning(f"[LOCK] Failed to write PID file: {e}")
        return True


async def _amain():
    """Async main — sets up DB then runs the agent."""
    if not acquire_single_instance_lock():
        sys.exit(0)

    # Load settings (loads settings.yaml; scraping sources reside in settings.yaml:scraping.sources)
    settings = load_all_config()
    
    # Configure Gemini Rate Limiter limits from settings
    from utils.api.gemini_rate_limiter import configure_from_settings
    configure_from_settings(settings)

    # Init DB (create tables)
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database ready")

    # Startup health checks
    logger.info("Running startup health checks...")
    checks_ok = await run_startup_checks(settings)
    if not checks_ok:
        logger.critical("Critical startup check failed — aborting")
        sys.exit(1)

    # Launch agent
    parser = argparse.ArgumentParser(description="Monika: Autonomous MT5 Trading Agent")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (skip MT5 execution)")
    args = parser.parse_args()
    if not getattr(args, 'action', None):
        args.action = 'execute'

    agent = TradingAgent(settings, dry_run=args.dry_run)
    try:
        await agent.start()
    finally:
        await close_db()


def main():
    """Synchronous entry point."""
    try:
        # Python 3.14+: gunakan loop_factory (policy system deprecated).
        # Psycopg (LangGraph checkpointer) butuh SelectorEventLoop di Windows
        # karena ProactorEventLoop tidak support add_reader()/add_writer().
        # asyncpg (SQLAlchemy) tetap kompatibel dengan SelectorEventLoop.
        if sys.platform == "win32":
            asyncio.run(_amain(), loop_factory=asyncio.SelectorEventLoop)
        else:
            asyncio.run(_amain())
        emerg_code = get_emergency_exit_code() or _EMERGENCY_EXIT_CODE
        release_single_instance_lock()
        if emerg_code is not None and emerg_code != 0:
            sys.exit(emerg_code)
        mark_clean_shutdown()
        sys.exit(0)
    except KeyboardInterrupt:
        # Already handled by signal handler — this is just a safety net
        release_single_instance_lock()
        mark_clean_shutdown()
        sys.exit(0)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 0
        release_single_instance_lock()
        if code == 0:
            mark_clean_shutdown()
        sys.exit(code)
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
        release_single_instance_lock()
        emerg_code = get_emergency_exit_code() or _EMERGENCY_EXIT_CODE
        if emerg_code is not None:
            sys.exit(emerg_code)
        sys.exit(1)


if __name__ == "__main__":
    main()
