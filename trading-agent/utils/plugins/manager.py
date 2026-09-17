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



class PluginManager:
    """Manages dynamic extensions and lifecycle hooks."""

    def __init__(self):
        self._hooks: Dict[str, List[Callable]] = defaultdict(list)

    def register_hook(self, event: str, handler: Callable) -> None:
        """Register a sync or async callback for a specific lifecycle event."""
        if handler not in self._hooks[event]:
            self._hooks[event].append(handler)
            logger.debug(f"[PluginManager] Registered hook for '{event}': {getattr(handler, '__name__', str(handler))}")

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

    def clear(self) -> None:
        """Clear all registered hooks."""
        self._hooks.clear()


_GLOBAL_PLUGIN_MANAGER: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Returns the singleton instance of PluginManager."""
    global _GLOBAL_PLUGIN_MANAGER
    if _GLOBAL_PLUGIN_MANAGER is None:
        _GLOBAL_PLUGIN_MANAGER = PluginManager()
    return _GLOBAL_PLUGIN_MANAGER
