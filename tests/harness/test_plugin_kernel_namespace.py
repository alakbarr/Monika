"""
Unit tests for plugin_kernel namespace re-export bridge.
"""

def test_plugin_kernel_exports():
    import plugin_kernel as pk

    assert hasattr(pk, "TradingPlugin")
    assert hasattr(pk, "PluginMetadata")
    assert hasattr(pk, "PluginCategory")
    assert hasattr(pk, "PluginOrigin")
    assert hasattr(pk, "PluginState")
    assert hasattr(pk, "PluginEngine")
    assert hasattr(pk, "get_plugin_engine")
    assert hasattr(pk, "list_all_plugins_status")
    assert hasattr(pk, "toggle_plugin_state")

    # Verify Protocol types
    assert hasattr(pk, "ServiceContainerProtocol")
    assert hasattr(pk, "EventBusProtocol")
    assert hasattr(pk, "TaskRegistryProtocol")


def test_plugin_kernel_instantiation():
    from plugin_kernel import PluginMetadata, PluginCategory, PluginOrigin, PluginState

    meta = PluginMetadata(
        id="test_kernel_plugin",
        name="Test Kernel Plugin",
        category=PluginCategory.MIDDLEWARE,
        origin=PluginOrigin.BUILTIN,
    )
    assert meta.id == "test_kernel_plugin"
    assert PluginState.ACTIVE.value == "ACTIVE"
