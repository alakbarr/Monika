import pytest
from utils.plugins.manager import PluginManager, PluginHook, get_plugin_manager


@pytest.mark.asyncio
async def test_plugin_manager_lifecycle():
    pm = PluginManager()
    events_received = []

    def sync_pre_tool(tool_name, args, **kwargs):
        events_received.append(("sync_pre", tool_name, args))

    async def async_post_tool(tool_name, args, result, **kwargs):
        events_received.append(("async_post", tool_name, result))

    pm.register_hook(PluginHook.PRE_TOOL_CALL, sync_pre_tool)
    pm.register_hook(PluginHook.POST_TOOL_CALL, async_post_tool)

    # Emit pre-tool
    await pm.emit(PluginHook.PRE_TOOL_CALL, tool_name="get_price_data", args={"symbol": "EURUSD"})
    assert len(events_received) == 1
    assert events_received[0] == ("sync_pre", "get_price_data", {"symbol": "EURUSD"})

    # Emit post-tool
    await pm.emit(PluginHook.POST_TOOL_CALL, tool_name="get_price_data", args={"symbol": "EURUSD"}, result={"price": 1.085})
    assert len(events_received) == 2
    assert events_received[1] == ("async_post", "get_price_data", {"price": 1.085})

    # Test error isolation: faulty hook does not break emit
    def faulty_hook(**kwargs):
        raise RuntimeError("Plugin crashed deliberately")

    pm.register_hook(PluginHook.PRE_TOOL_CALL, faulty_hook)
    # Should not raise exception
    res = await pm.emit(PluginHook.PRE_TOOL_CALL, tool_name="test_tool", args={})
    assert len(events_received) == 3

    # Test unregister
    assert pm.unregister_hook(PluginHook.PRE_TOOL_CALL, sync_pre_tool) is True
    pm.clear()
    assert len(pm._hooks) == 0


def test_singleton_getter():
    pm1 = get_plugin_manager()
    pm2 = get_plugin_manager()
    assert pm1 is pm2
