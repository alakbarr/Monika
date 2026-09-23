# ==============================================================================
# File: harness/contract.py
# ==============================================================================

"""
Universal Plugin Contract for Monika Trading Harness.
Provides standardized interfaces, lifecycle stages, and typed reactive hooks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Dict, Any, Optional
import inspect
import logging

from utils.infra.container import ServiceContainer
from utils.protocol.event_bus import (
    EventBus,
    TickPriceEvent,
    BarClosedEvent,
    OrderStateChangedEvent,
    RiskBreachEvent,
    CircuitBreakerEvent,
)
from agent.task_registry import TaskRegistry

logger = logging.getLogger("TradingAgent.Harness.Contract")


class PluginCategory(str, Enum):
    ANALYSIS_PIPELINE = "analysis_pipeline"  # Full Analysis Cycle / Trading Style
    BROKER = "broker"                        # Broker connectivity & execution
    SCHEDULER = "scheduler"                  # Periodic / background tasks
    RISK_RULE = "risk_rule"                  # Pre-order risk inspection
    DYNAMIC_SIZING = "dynamic_sizing"        # Lot sizing adjustments
    TOOL = "tool"                            # LLM agent tools
    STRATEGY = "strategy"                    # Quantitative alpha strategies
    LLM_PROVIDER = "llm_provider"            # LLM models & vendors
    DATA_SOURCE = "data_source"              # News, calendar, macro scrapers
    NOTIFICATION = "notification"            # Alert & messaging channels
    DASHBOARD = "dashboard"                  # Web UI routes & panels
    MIDDLEWARE = "middleware"                # Event filters & interceptors


class PluginOrigin(str, Enum):
    BUILTIN = "builtin"
    PIP_PACKAGE = "pip_package"
    LOCAL_DIRECTORY = "local_directory"


@dataclass
class PluginMetadata:
    id: str
    name: str
    version: str = "1.0.0"
    category: PluginCategory = PluginCategory.MIDDLEWARE
    description: str = ""
    author: Optional[str] = None
    origin: PluginOrigin = PluginOrigin.BUILTIN
    is_core: bool = False  # True: failure triggers emergency fail-closed; False: degraded isolation
    dependencies: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    required_packages: List[str] = field(default_factory=list)  # Third-party pip packages


class TradingPlugin(ABC):
    """
    Universal Plugin Contract for Monika Trading Harness.
    All components (broker, schedulers, analysis pipelines, scrapers, tools) extend this class.
    """
    metadata: PluginMetadata

    def __init__(self, *args, **kwargs):
        config = None
        if len(args) == 1 and isinstance(args[0], dict):
            config = args[0]
        elif len(args) >= 2 and isinstance(args[1], dict):
            config = args[1]
        elif "config" in kwargs:
            config = kwargs["config"]
        self.config: Dict[str, Any] = config or {}
        self.is_enabled: bool = True
        self.status: str = "INITIALIZED"
        self.status_message: str = ""

    # 1. Dependency Registration
    async def on_register(self, container: ServiceContainer, event_bus: EventBus) -> None:
        """Register services, singletons, factories into DI container & subscribe to EventBus."""
        pass

    # 2. Modular Pre-flight Health & Environment Checks
    async def on_preflight(self, container: ServiceContainer) -> Tuple[bool, List[str]]:
        """Validate plugin requirements (credentials, DB tables, endpoints). Returns (is_healthy, warnings)."""
        return True, []

    # 3. Post-Restart State Recovery Hook
    async def on_recovery(self, container: ServiceContainer) -> None:
        """Perform crash/restart synchronization (sync positions, reconcile in-flight orders)."""
        pass

    # 4. Background Concurrency Launch
    async def on_start(self, container: ServiceContainer, task_registry: TaskRegistry) -> None:
        """Register persistent background tasks/loops with TaskRegistry."""
        pass

    # 5. Fast-Path Reactive Event Handlers
    async def on_tick(self, event: TickPriceEvent) -> None:
        pass

    async def on_bar(self, event: BarClosedEvent) -> None:
        pass

    async def on_order_state(self, event: OrderStateChangedEvent) -> None:
        pass

    async def on_risk_breach(self, event: RiskBreachEvent) -> None:
        pass

    async def on_circuit_breaker(self, event: CircuitBreakerEvent) -> None:
        pass

    # 6. Configuration Hot-Reload
    async def on_config_reload(self, new_config: Dict[str, Any]) -> None:
        """Handle live configuration updates on SIGHUP or settings watcher."""
        self.config.update(new_config)

    # 7. Graceful Teardown
    async def on_stop(self) -> None:
        """Orderly resource teardown, cancel background loops, flush outbox."""
        self.status = "STOPPED"
