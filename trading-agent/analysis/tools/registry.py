"""
Self-registering tool registry with availability gating and bounded output (Phase 5).
Fully backward-compatible with legacy ToolHandler decorators, categories, and parallel safety.
"""

import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union, cast

from analysis.tools.base_handler import ToolHandler

logger = logging.getLogger("TradingAgent.ToolRegistry")


@dataclass
class ToolDefinition:
    """Metadata, JSON schema, and execution handler for an agent tool."""
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable
    toolset: str = "default"
    check_fn: Optional[Callable[[], bool]] = None  # Availability gate
    max_output_chars: int = 10000
    requires_db: bool = False

    def is_available(self) -> bool:
        """Check whether tool is currently available for LLM binding."""
        if self.check_fn is None:
            return True
        try:
            return bool(self.check_fn())
        except Exception as e:
            logger.debug(f"Availability check failed for tool {self.name}: {e}")
            return False

    async def execute(self, arguments: dict, session=None, executor=None, **context) -> Any:
        """Adapter method for unified duck-typing with ToolHandler.execute."""
        ctx = dict(context)
        if session is not None:
            ctx["session"] = session
        if executor is not None:
            ctx["executor"] = executor
        if inspect.iscoroutinefunction(self.handler):
            return await self.handler(arguments, **ctx)
        return self.handler(arguments, **ctx)


class ToolRegistry:
    """Central registry for all agent tools with dynamic availability, routing, and legacy support."""

    _instance: Optional["ToolRegistry"] = None

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._toolsets: Dict[str, Set[str]] = {}
        self._handlers: Dict[str, ToolHandler] = {}
        self._handler_classes: Dict[str, Type[ToolHandler]] = {}
        self._aliases: Dict[str, str] = {}
        self._categories: Dict[str, List[str]] = {}

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (primarily for test isolation)."""
        cls._instance = None

    def register(
        self,
        handler_cls_or_instance: Union[Type[ToolHandler], ToolHandler, ToolDefinition, Any],
        name: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        category: Optional[str] = None,
        parallel_safe: Optional[bool] = None,
    ):
        """Register a tool definition, handler class, or handler instance."""
        if isinstance(handler_cls_or_instance, ToolDefinition):
            tool = handler_cls_or_instance
            tool_name = name or tool.name
            self._tools[tool_name] = tool
            toolset = getattr(tool, "toolset", "default")
            self._toolsets.setdefault(toolset, set()).add(tool_name)
            tool_category = (category or toolset).upper()
            if tool_category not in self._categories:
                self._categories[tool_category] = []
            if tool_name not in self._categories[tool_category]:
                self._categories[tool_category].append(tool_name)
            logger.debug(f"Registered ToolDefinition: {tool_name} (toolset={toolset})")
            return tool

        # Otherwise handle ToolHandler class or instance
        if inspect.isclass(handler_cls_or_instance):
            handler_cls = handler_cls_or_instance
            instance = None
        else:
            instance = handler_cls_or_instance
            handler_cls = instance.__class__

        tool_name = name or getattr(instance or handler_cls, "name", "")
        if not tool_name:
            raise ValueError(f"Tool name must be specified for handler {handler_cls}")

        tool_aliases = aliases if aliases is not None else list(getattr(instance or handler_cls, "aliases", []))
        tool_category = category or getattr(instance or handler_cls, "category", "GENERAL")
        tool_parallel_safe = parallel_safe if parallel_safe is not None else getattr(instance or handler_cls, "parallel_safe", True)

        self._handler_classes[tool_name] = cast(Type[ToolHandler], handler_cls)
        if instance is not None:
            instance.name = tool_name
            instance.aliases = tool_aliases
            instance.category = tool_category
            instance.parallel_safe = tool_parallel_safe
            self._handlers[tool_name] = instance

        for alias in tool_aliases:
            self._aliases[alias] = tool_name

        cat_key = tool_category.upper()
        if cat_key not in self._categories:
            self._categories[cat_key] = []
        if tool_name not in self._categories[cat_key]:
            self._categories[cat_key].append(tool_name)

        return handler_cls_or_instance

    def unregister(self, tool_name: str) -> None:
        """Remove a tool from registry."""
        canonical = self.resolve_name(tool_name)
        if canonical in self._tools:
            tool = self._tools.pop(canonical)
            if tool.toolset in self._toolsets:
                self._toolsets[tool.toolset].discard(canonical)
        self._handlers.pop(canonical, None)
        self._handler_classes.pop(canonical, None)

    def get(self, name: str, settings: Optional[dict] = None) -> Any:
        """Resolve canonical name and return an instantiated ToolHandler or ToolDefinition."""
        canonical = self.resolve_name(name)
        if canonical in self._tools:
            return self._tools[canonical]
        if canonical in self._handlers:
            return self._handlers[canonical]
        if canonical in self._handler_classes:
            handler_cls = self._handler_classes[canonical]
            instance = handler_cls(settings=settings)
            self._handlers[canonical] = instance
            return instance
        return None

    def resolve_name(self, name: str) -> str:
        """Resolve alias to canonical tool name."""
        if not name:
            return ""
        return self._aliases.get(name, name)

    def is_parallel_safe(self, name: str) -> bool:
        """Check if a tool can safely run concurrently in a batch segment."""
        canonical = self.resolve_name(name)
        if canonical in ("submit_asset_analysis", "propose_action", "submit_fundamental_brief"):
            return False
        handler = self.get(canonical)
        if handler is not None and hasattr(handler, "parallel_safe"):
            return bool(getattr(handler, "parallel_safe"))
        return True

    def list_tools(self) -> List[str]:
        """Return all registered canonical tool names."""
        names = set(self._handlers.keys()) | set(self._handler_classes.keys()) | set(self._tools.keys())
        return sorted(list(names))

    def get_by_category(self, category: str) -> List[str]:
        """Return tool names under a given category."""
        return self._categories.get(category.upper(), self._categories.get(category, []))

    def get_available_tools(self, toolsets: Optional[Set[str]] = None) -> List[ToolDefinition]:
        """Get tools filtered by toolset and availability."""
        tools = list(self._tools.values())
        if toolsets:
            tools = [t for t in tools if t.toolset in toolsets]
        return [t for t in tools if t.is_available()]

    def get_schemas(self, toolsets: Optional[Set[str]] = None) -> List[dict]:
        """Get JSON schemas for available tools formatted for LLM function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self.get_available_tools(toolsets)
        ]

    async def dispatch(self, tool_name: str, arguments: dict, **context) -> dict:
        """Execute a tool by name with error boundary and output clamping."""
        canonical = self.resolve_name(tool_name)
        tool = self._tools.get(canonical)
        handler = self.get(canonical)

        if not tool and not handler:
            return {"error": f"Unknown tool: {tool_name}", "is_error": True}

        try:
            if tool:
                if not tool.is_available():
                    return {"error": f"Tool {tool_name} is currently unavailable", "is_error": True}
                if inspect.iscoroutinefunction(tool.handler):
                    result = await tool.handler(arguments, **context)
                else:
                    result = tool.handler(arguments, **context)
                max_chars = tool.max_output_chars
            else:
                session = context.get("session")
                executor = context.get("executor")
                result = await handler.execute(arguments, session=session, executor=executor, **context)
                max_chars = 10000

            # Output length clamping
            if isinstance(result, str) and len(result) > max_chars:
                result = (
                    result[:max_chars]
                    + f"\n[... truncated at {max_chars} characters for context safety]"
                )
            return {"content": result, "is_error": False}
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            return {"error": str(e)[:2048], "is_error": True}

    def auto_discover(self, package_name: str = "analysis.tools.handlers"):
        """Dynamically import all handler submodules to trigger registration decorators."""
        try:
            pkg = importlib.import_module(package_name)
            if hasattr(pkg, "__path__"):
                for _, modname, _ in pkgutil.iter_modules(pkg.__path__):
                    full_modname = f"{package_name}.{modname}"
                    try:
                        importlib.import_module(full_modname)
                    except Exception as e:
                        logger.warning(f"Failed to auto-discover tool handler {full_modname}: {e}")
        except Exception as e:
            logger.warning(f"Error during tool auto-discovery in {package_name}: {e}")


# Global default instance
default_tool_registry: ToolRegistry = ToolRegistry.get_instance()


def register_tool(
    name: str,
    aliases: Optional[List[str]] = None,
    category: Optional[str] = None,
    parallel_safe: bool = True,
):
    """Decorator to register tool handlers into the default_tool_registry."""
    def decorator(cls_or_instance):
        default_tool_registry.register(
            cls_or_instance,
            name=name,
            aliases=aliases,
            category=category,
            parallel_safe=parallel_safe,
        )
        return cls_or_instance
    return decorator
