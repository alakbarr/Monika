# ==============================================================================
# File: utils/plugins/manager.py
# ==============================================================================

"""
Lightweight Plugin & Extension Architecture.
Provides lifecycle hooks (pre/post tool call, pre/post llm call, pre risk gate, post cycle)
with safe execution and async/sync handler support.
"""

import asyncio
import inspect
import logging
from collections import defaultdict
from typing import Callable, Dict, List, Any, Optional

logger = logging.getLogger("TradingAgent.PluginManager")


class PluginHook:
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    PRE_LLM_CALL = "pre_llm_call"
    POST_LLM_CALL = "post_llm_call"
    ON_LLM_ERROR = "on_llm_error"
    PRE_RISK_GATE = "pre_risk_gate"
    POST_CYCLE = "post_cycle"
    PRE_ORDER = "pre_order"
    POST_ORDER = "post_order"
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"

    # Core workflow lifecycle hooks
    PRE_STAGE1 = "pre_stage1"
    POST_STAGE1 = "post_stage1"
    PRE_STAGE2 = "pre_stage2"
    POST_STAGE2 = "post_stage2"
    ON_TOOL_EXECUTION = "on_tool_execution"
    ON_RISK_CHECK = "on_risk_check"


class BasePlugin:
    """
    Abstract base class for modular plugins.
    Allows plugins to cleanly encapsulate lifecycle hooks, custom tools, and state.
    """
    name: str = ""
    version: str = "1.0.0"
    description: str = ""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def setup(self, manager: "PluginManager") -> None:
        """Register hooks and tools with PluginManager."""
        pass

    def teardown(self, manager: "PluginManager") -> None:
        """Cleanup hooks and tools registered by this plugin."""
        pass


class PluginManager:
    """Manages dynamic extensions, custom tools, and lifecycle hooks."""

    def __init__(self):
        self._hooks: Dict[str, List[Callable]] = defaultdict(list)
        self._registered_tools: List[str] = []

    def register_hook(self, event: str, handler: Callable) -> Callable[[], bool]:
        """
        Register a sync or async callback for a specific lifecycle event.
        Returns a disposer function that unregisters the hook when called.
        """
        if handler not in self._hooks[event]:
            self._hooks[event].append(handler)
            logger.debug(f"[PluginManager] Registered hook for '{event}': {getattr(handler, '__name__', str(handler))}")

        def disposer() -> bool:
            return self.unregister_hook(event, handler)
        return disposer

    def unregister_hook(self, event: str, handler: Callable) -> bool:
        """Unregister a previously registered hook."""
        if event in self._hooks and handler in self._hooks[event]:
            self._hooks[event].remove(handler)
            return True
        return False

    async def emit(self, event: str, **kwargs: Any) -> List[Any]:
        """
        Emit a lifecycle event to all registered hooks.
        Executes each handler safely; exceptions in hooks are logged and isolated.
        """
        handlers = list(self._hooks.get(event, []))
        results = []
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    res = await handler(**kwargs)
                else:
                    res = handler(**kwargs)
                results.append(res)
            except Exception as e:
                handler_name = getattr(handler, '__name__', str(handler))
                logger.error(f"[PluginManager] Error executing hook '{handler_name}' on event '{event}': {e}", exc_info=True)
        return results

    async def emit_waterfall(self, event: str, payload: Any, **kwargs: Any) -> tuple[bool, Any]:
        """
        Waterfall interceptor middleware for critical lifecycle events (e.g. PRE_ORDER, PRE_RISK_GATE).
        Handlers execute sequentially. If any handler returns False or (False, reason),
        execution short-circuits immediately and returns (False, reason).
        If handler returns a modified payload, it cascades to subsequent handlers.
        """
        handlers = list(self._hooks.get(event, []))
        current = payload
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    res = await handler(current, **kwargs)
                else:
                    res = handler(current, **kwargs)

                if res is False:
                    handler_name = getattr(handler, '__name__', str(handler))
                    logger.warning(f"[PluginManager] Waterfall event '{event}' vetoed by '{handler_name}'.")
                    return False, f"Vetoed by {handler_name}"
                if isinstance(res, tuple) and len(res) == 2 and res[0] is False:
                    handler_name = getattr(handler, '__name__', str(handler))
                    logger.warning(f"[PluginManager] Waterfall event '{event}' vetoed by '{handler_name}': {res[1]}")
                    return False, res[1]
                if res is not None and not isinstance(res, bool):
                    current = res
            except Exception as e:
                handler_name = getattr(handler, '__name__', str(handler))
                logger.error(f"[PluginManager] Error executing waterfall handler '{handler_name}' on '{event}': {e}", exc_info=True)
        return True, current

    async def apply_filter(self, event: str, payload: Any, **kwargs: Any) -> Any:
        """
        Execute filter pipeline for an event.
        Passes payload through registered handlers in sequence, allowing transformations.
        Errors in individual filters are caught and logged, preserving the current payload.
        """
        handlers = list(self._hooks.get(event, []))
        current = payload
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    res = await handler(current, **kwargs)
                else:
                    res = handler(current, **kwargs)
                if res is not None:
                    current = res
            except Exception as e:
                handler_name = getattr(handler, '__name__', str(handler))
                logger.error(f"[PluginManager] Error executing filter '{handler_name}' on '{event}': {e}", exc_info=True)
        return current

    def register_tool(
        self,
        name: str,
        category: str,
        input_model: Any,
        handler: Callable,
        check_fn: Optional[Callable[[], bool]] = None,
        description: Optional[str] = None,
    ) -> Callable[[], bool]:
        """
        Dynamically register a custom tool into UnifiedToolRegistry.
        Returns a disposer function that unregisters the tool when called.
        """
        try:
            from analysis.tools.unified_registry import unified_tool_registry, ToolEntry
            desc = description or (getattr(input_model, "__doc__", None) or getattr(handler, "__doc__", "")).strip()
            is_async = inspect.iscoroutinefunction(handler)
            entry = ToolEntry(
                name=name,
                category=category,
                description=desc,
                input_model=input_model,
                handler=handler,
                check_fn=check_fn,
                is_async=is_async,
            )
            unified_tool_registry._tools[name] = entry
            if name not in self._registered_tools:
                self._registered_tools.append(name)
            logger.info(f"[PluginManager] Registered custom tool '{name}' ({category})")
            return lambda: self.unregister_tool(name)
        except Exception as e:
            logger.error(f"[PluginManager] Failed to register custom tool '{name}': {e}", exc_info=True)
            raise

    def unregister_tool(self, name: str) -> bool:
        """Unregister a previously registered custom tool."""
        try:
            from analysis.tools.unified_registry import unified_tool_registry
            if name in unified_tool_registry._tools:
                del unified_tool_registry._tools[name]
                if name in self._registered_tools:
                    self._registered_tools.remove(name)
                logger.info(f"[PluginManager] Unregistered tool '{name}'")
                return True
        except Exception as e:
            logger.error(f"[PluginManager] Error unregistering tool '{name}': {e}")
        return False

    def list_registered_tools(self) -> List[str]:
        """Return list of tool names registered through this PluginManager."""
        return list(self._registered_tools)

    def clear(self) -> None:
        """Clear all registered hooks and custom tools."""
        self._hooks.clear()
        for tool_name in list(self._registered_tools):
            self.unregister_tool(tool_name)
        self._registered_tools.clear()


_GLOBAL_PLUGIN_MANAGER: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Returns the singleton instance of PluginManager."""
    global _GLOBAL_PLUGIN_MANAGER
    if _GLOBAL_PLUGIN_MANAGER is None:
        _GLOBAL_PLUGIN_MANAGER = PluginManager()
    return _GLOBAL_PLUGIN_MANAGER
