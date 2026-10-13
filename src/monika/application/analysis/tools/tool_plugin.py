# ==============================================================================
# File: analysis/tools/tool_plugin.py
# ==============================================================================

"""
Pluggable LLM Tool Plugin Interface (Phase 3e).
Enables swappable custom toolsets to be packaged as TradingPlugins and dispatched via ToolRegistry.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Union

from monika.application.harness.contract import PluginCategory, PluginMetadata, TradingPlugin

logger = logging.getLogger("TradingAgent.ToolPlugin")


class ToolPlugin(TradingPlugin, ABC):
    """
    Contract for pluggable LLM tools in Monika.
    Bridges between the harness plugin lifecycle and the agent ToolRegistry / unified_tool_registry.
    """

    metadata: PluginMetadata

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, "metadata"):
            self.metadata.category = PluginCategory.TOOL

    @abstractmethod
    def get_tool_definitions(self) -> List[Any]:
        """
        Return list of tool schema definitions (ToolDefinition instances or Anthropic/OpenAI schema dicts).
        """
        pass

    @abstractmethod
    def get_handlers(self) -> Dict[str, Callable]:
        """
        Return dictionary mapping tool_name -> executable callable (sync or async).
        """
        pass

    async def on_register(self, container: Any, event_bus: Any = None) -> None:
        """Auto-register tool definitions and handlers into the centralized ToolRegistry."""
        if event_bus is not None:
            await super().on_register(container, event_bus)

        from monika.application.analysis.tools.registry import ToolRegistry

        registry = ToolRegistry.get_instance()
        defs = self.get_tool_definitions()
        handlers = self.get_handlers()

        for d in defs:
            try:
                registry.register(d)
            except Exception as e:
                logger.debug(f"[ToolPlugin] Registration note for definition {d}: {e}")

        for name, handler in handlers.items():
            try:
                registry.register_handler(name, handler)
            except Exception as e:
                logger.debug(f"[ToolPlugin] Registration note for handler {name}: {e}")

        logger.info(f"[ToolPlugin] Registered tool plugin '{self.metadata.id}' with {len(handlers)} handlers")
