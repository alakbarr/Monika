# ==============================================================================
# File: tests/harness/test_plugin_engine.py
# ==============================================================================

import pytest
import asyncio
from typing import Tuple, List, Dict, Any

from harness.contract import (
    TradingPlugin,
    PluginMetadata,
    PluginCategory,
    PluginOrigin,
)
from harness.engine import (
    PluginEngine,
    topological_sort_plugins,
    MissingDependencyError,
    CircularDependencyError,
)
from utils.infra.container import ServiceContainer
from utils.protocol.event_bus import EventBus, TickPriceEvent


class DummyPluginA(TradingPlugin):
    metadata = PluginMetadata(
        id="plugin_a",
        name="Plugin A",
        version="1.0.0",
        category=PluginCategory.MIDDLEWARE,
    )

    def __init__(self, config=None):
        super().__init__(config)
        self.registered = False
        self.preflighted = False
        self.started = False
        self.stopped = False
        self.ticks_received = []

    async def on_register(self, container: ServiceContainer, event_bus: EventBus) -> None:
        self.registered = True

    async def on_preflight(self, container: ServiceContainer) -> Tuple[bool, List[str]]:
        self.preflighted = True
        return True, []

    async def on_start(self, container: ServiceContainer, task_registry: Any) -> None:
        self.started = True

    async def on_stop(self) -> None:
        self.stopped = True

    async def on_tick(self, event: TickPriceEvent) -> None:
        self.ticks_received.append(event.symbol)


class DummyPluginB(TradingPlugin):
    metadata = PluginMetadata(
        id="plugin_b",
        name="Plugin B",
        version="1.0.0",
        category=PluginCategory.SCHEDULER,
        dependencies=["plugin_a"],  # B depends on A
    )

    def __init__(self, config=None):
        super().__init__(config)
        self.registered = False

    async def on_register(self, container: ServiceContainer, event_bus: EventBus) -> None:
        self.registered = True


class DummyPluginC(TradingPlugin):
    metadata = PluginMetadata(
        id="plugin_c",
        name="Plugin C",
        version="1.0.0",
        category=PluginCategory.SCHEDULER,
        dependencies=["plugin_b"],  # C depends on B (A -> B -> C)
    )


class CyclicPluginX(TradingPlugin):
    metadata = PluginMetadata(
        id="plugin_x",
        name="Plugin X",
        dependencies=["plugin_y"],
    )


class CyclicPluginY(TradingPlugin):
    metadata = PluginMetadata(
        id="plugin_y",
        name="Plugin Y",
        dependencies=["plugin_x"],
    )


@pytest.mark.asyncio
async def test_topological_sort_success():
    a = DummyPluginA()
    b = DummyPluginB()
    c = DummyPluginC()

    # Pass in reverse order: c, b, a
    sorted_plugins = topological_sort_plugins([c, b, a])
    assert [p.metadata.id for p in sorted_plugins] == ["plugin_a", "plugin_b", "plugin_c"]


@pytest.mark.asyncio
async def test_topological_sort_missing_dependency():
    b = DummyPluginB()  # Requires plugin_a which is not provided
    with pytest.raises(MissingDependencyError) as exc_info:
        topological_sort_plugins([b])
    assert "requires missing dependency 'plugin_a'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_topological_sort_circular_dependency():
    x = CyclicPluginX()
    y = CyclicPluginY()
    with pytest.raises(CircularDependencyError) as exc_info:
        topological_sort_plugins([x, y])
    assert "Circular dependency detected" in str(exc_info.value)


@pytest.mark.asyncio
async def test_plugin_engine_lifecycle():
    container = ServiceContainer()
    event_bus = EventBus()
    engine = PluginEngine(container=container, event_bus=event_bus)

    plugin_a = DummyPluginA()
    plugin_b = DummyPluginB()

    engine.register_plugin_instance(plugin_b)
    engine.register_plugin_instance(plugin_a)

    settings = {
        "plugins": {
            "enabled": True,
            "directories": [],
        }
    }

    # Initialize
    success = await engine.initialize(settings)
    assert success is True
    assert [p.metadata.id for p in engine.ordered_plugins] == ["plugin_a", "plugin_b"]
    assert plugin_a.registered is True
    assert plugin_a.preflighted is True
    assert plugin_b.registered is True

    # Start
    await engine.start()
    assert plugin_a.started is True
    assert plugin_a.status == "RUNNING"

    # Test reactive event wiring
    await event_bus.publish(TickPriceEvent(symbol="EURUSD", bid=1.1000, ask=1.1002))
    await asyncio.sleep(0.05)
    assert "EURUSD" in plugin_a.ticks_received

    # Stop
    await engine.stop()
    assert plugin_a.stopped is True


@pytest.mark.asyncio
async def test_plugin_missing_package_degraded():
    container = ServiceContainer()
    event_bus = EventBus()
    engine = PluginEngine(container=container, event_bus=event_bus)

    class PluginWithMissingPkg(TradingPlugin):
        metadata = PluginMetadata(
            id="plugin_dep_test",
            name="Dep Test",
            required_packages=["definitely_non_existent_package_xyz123"],
        )

    plugin = PluginWithMissingPkg()
    engine.register_plugin_instance(plugin)

    settings = {"plugins": {"enabled": True, "directories": []}}
    await engine.initialize(settings)

    assert plugin.is_enabled is False
    assert plugin.status == "DEGRADED_MISSING_DEPENDENCIES"
    assert "definitely_non_existent_package_xyz123" in plugin.status_message


@pytest.mark.asyncio
async def test_plugin_slot_options_available_fallback():
    container = ServiceContainer()
    event_bus = EventBus()
    engine = PluginEngine(container=container, event_bus=event_bus)

    class CustomBrokerPlugin(TradingPlugin):
        metadata = PluginMetadata(
            id="test_broker",
            name="Test Broker",
            category=PluginCategory.BROKER,
        )

    plugin = CustomBrokerPlugin()
    engine.register_plugin_instance(plugin)

    settings = {
        "plugins": {
            "enabled": True,
            "directories": [],
            "broker": {
                "active": "test_broker",
                "available": {
                    "test_broker": {"slippage_pips": 1.5, "mock_fill": True}
                }
            }
        }
    }
    await engine.initialize(settings)

    assert plugin.is_enabled is True
    assert plugin.config.get("slippage_pips") == 1.5
    assert plugin.config.get("mock_fill") is True


@pytest.mark.asyncio
async def test_plugin_disposer_lifo_execution():
    container = ServiceContainer()
    event_bus = EventBus()
    engine = PluginEngine(container=container, event_bus=event_bus)

    disposer_order = []

    class DisposerTestPlugin(TradingPlugin):
        metadata = PluginMetadata(
            id="disposer_test",
            name="Disposer Test",
            category=PluginCategory.MIDDLEWARE,
        )

        async def on_register(self, c, eb):
            self.add_disposer(lambda: disposer_order.append("first_registered"))
            self.add_disposer(lambda: disposer_order.append("second_registered"))

    plugin = DisposerTestPlugin()
    engine.register_plugin_instance(plugin)

    settings = {"plugins": {"enabled": True, "directories": []}}
    await engine.initialize(settings)
    await engine.start()
    await engine.stop()

    # LIFO order: second registered should run before first registered
    assert disposer_order == ["second_registered", "first_registered"]
    assert plugin.status == "STOPPED"


@pytest.mark.asyncio
async def test_plugin_config_reload_propagation():
    container = ServiceContainer()
    event_bus = EventBus()
    engine = PluginEngine(container=container, event_bus=event_bus)

    class ReloadTestPlugin(TradingPlugin):
        metadata = PluginMetadata(
            id="reload_test",
            name="Reload Test",
            category=PluginCategory.BROKER,
        )

    plugin = ReloadTestPlugin()
    engine.register_plugin_instance(plugin)

    settings = {
        "plugins": {
            "enabled": True,
            "directories": [],
            "broker": {
                "active": "reload_test",
                "available": {"reload_test": {"lot_size": 0.05}}
            }
        }
    }
    await engine.initialize(settings)
    assert plugin.config.get("lot_size") == 0.05

    # Propagate reload
    new_settings = {
        "plugins": {
            "enabled": True,
            "broker": {
                "active": "reload_test",
                "available": {"reload_test": {"lot_size": 0.10, "max_slippage": 2.0}}
            }
        }
    }
    await engine.propagate_config_reload(new_settings)
    assert plugin.config.get("lot_size") == 0.10
    assert plugin.config.get("max_slippage") == 2.0


@pytest.mark.asyncio
async def test_plugin_timeout_isolation_non_core(monkeypatch):
    import harness.engine as eng
    monkeypatch.setattr(eng, "LIFECYCLE_TIMEOUT_PREFLIGHT", 0.05)

    container = ServiceContainer()
    event_bus = EventBus()
    engine = PluginEngine(container=container, event_bus=event_bus)

    class HangingPlugin(TradingPlugin):
        metadata = PluginMetadata(
            id="hanging_plugin",
            name="Hanging Plugin",
            category=PluginCategory.MIDDLEWARE,
            is_core=False,
        )

        async def on_preflight(self, c):
            await asyncio.sleep(1.0)
            return True, []

    plugin = HangingPlugin()
    engine.register_plugin_instance(plugin)

    settings = {"plugins": {"enabled": True, "directories": []}}
    success = await engine.initialize(settings)

    # Non-core plugin should be disabled without crashing initialization
    assert success is True
    assert plugin.is_enabled is False
    assert plugin.status == "PREFLIGHT_TIMEOUT"


