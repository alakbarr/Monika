"""
Self-registering tool registry with availability gating and bounded output (Phase 5).
Fully backward-compatible with legacy ToolHandler decorators, categories, and parallel safety.
"""

import ast
import importlib
import inspect
import logging
import os
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union, cast

from analysis.tools.base_handler import ToolHandler

logger = logging.getLogger("TradingAgent.ToolRegistry")

_AST_REGISTRATION_CACHE: Dict[str, tuple[float, bool]] = {}


def _module_has_tool_registration(file_path: str) -> bool:
    """Pre-scan a python module file AST to verify if it contains tool registrations (Phase 4.4).
    Prevents eager importing of heavy/optional dependencies at startup.
    """
    try:
        mtime = os.path.getmtime(file_path)
        cached = _AST_REGISTRATION_CACHE.get(file_path)
        if cached is not None and cached[0] == mtime:
            return cached[1]

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            source = f.read()

        tree = ast.parse(source, filename=file_path)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for dec in node.decorator_list:
                    dec_name = ""
                    if isinstance(dec, ast.Name):
                        dec_name = dec.id
                    elif isinstance(dec, ast.Attribute):
                        dec_name = dec.attr
                    elif isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Name):
                            dec_name = dec.func.id
                        elif isinstance(dec.func, ast.Attribute):
                            dec_name = dec.func.attr
                    if "register" in dec_name.lower():
                        _AST_REGISTRATION_CACHE[file_path] = (mtime, True)
                        return True

            if isinstance(node, ast.Call):
                fn_name = ""
                if isinstance(node.func, ast.Name):
                    fn_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    fn_name = node.func.attr
                if "register" in fn_name.lower():
                    _AST_REGISTRATION_CACHE[file_path] = (mtime, True)
                    return True

            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    b_name = ""
                    if isinstance(base, ast.Name):
                        b_name = base.id
                    elif isinstance(base, ast.Attribute):
                        b_name = base.attr
                    if "ToolHandler" in b_name or "BaseHandler" in b_name:
                        _AST_REGISTRATION_CACHE[file_path] = (mtime, True)
                        return True

        _AST_REGISTRATION_CACHE[file_path] = (mtime, False)
        return False
    except Exception as e:
        logger.debug(f"[AST Pre-Scan] Error scanning {file_path}, falling back to import: {e}")
        return True


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
    timeout_seconds: float = 30.0
    protected: bool = False
    _last_check_time: float = field(default=0.0, init=False, repr=False)
    _last_check_result: bool = field(default=True, init=False, repr=False)
    _last_healthy_time: float = field(default=0.0, init=False, repr=False)

    def is_available(self) -> bool:
        """Check whether tool is currently available for LLM binding with 30s TTL and 60s grace."""
        if self.check_fn is None:
            return True
        import time
        now = time.time()
        if now - self._last_check_time < 30.0:
            return self._last_check_result

        self._last_check_time = now
        try:
            res = bool(self.check_fn())
            if res:
                self._last_healthy_time = now
            elif self._last_healthy_time > 0.0 and (now - self._last_healthy_time < 60.0):
                # 60s grace window for transient glitches
                res = True
            self._last_check_result = res
            return res
        except Exception as e:
            logger.debug(f"Availability check failed for tool {self.name}: {e}")
            if self._last_healthy_time > 0.0 and (now - self._last_healthy_time < 60.0):
                return True
            self._last_check_result = False
            return False

    async def execute(self, arguments: dict, session=None, executor=None, timeout_seconds: Optional[float] = None, **context) -> Any:
        """Adapter method with cooperative deadline timeout."""
        import asyncio
        ctx = dict(context)
        if session is not None:
            ctx["session"] = session
        if executor is not None:
            ctx["executor"] = executor

        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        try:
            if inspect.iscoroutinefunction(self.handler):
                return await asyncio.wait_for(self.handler(arguments, **ctx), timeout=effective_timeout)
            return self.handler(arguments, **ctx)
        except asyncio.TimeoutError:
            logger.error(f"[ToolTimeout] Tool '{self.name}' exceeded {effective_timeout:.1f}s deadline.")
            return {
                "error": "TOOL_TIMEOUT",
                "message": f"Tool '{self.name}' timed out after {effective_timeout:.1f}s deadline.",
                "tool_name": self.name,
                "timeout_seconds": effective_timeout,
            }


CORE_PROTECTED_TOOLS: Set[str] = {
    "submit_order",
    "propose_action",
    "calculate_position_size",
    "get_open_positions",
    "get_account_info",
    "submit_asset_analysis",
    "execute_order",
}


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

    def register_definition(self, definition: ToolDefinition, allow_override: bool = False) -> ToolDefinition:
        """Convenience method to register a ToolDefinition instance."""
        return self.register(definition, allow_override=allow_override)

    def register(
        self,
        handler_cls_or_instance: Union[Type[ToolHandler], ToolHandler, ToolDefinition, Any],
        name: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        category: Optional[str] = None,
        parallel_safe: Optional[bool] = None,
        allow_override: bool = False,
        protected: bool = False,
    ):
        """Register a tool definition, handler class, or handler instance with core shadowing protection."""
        if isinstance(handler_cls_or_instance, ToolDefinition):
            tool = handler_cls_or_instance
            tool_name = name or tool.name

            # Shadowing protection
            existing = self._tools.get(tool_name)
            if existing and not allow_override:
                if getattr(existing, "protected", False) or tool_name in CORE_PROTECTED_TOOLS:
                    raise PermissionError(
                        f"Unauthorized tool override: Core execution tool '{tool_name}' is protected. "
                        f"Pass allow_override=True to explicitly replace this tool."
                    )
            if protected:
                tool.protected = True

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

        # Shadowing protection
        existing = self._tools.get(tool_name) or self._handlers.get(tool_name)
        if existing and not allow_override:
            if getattr(existing, "protected", False) or tool_name in CORE_PROTECTED_TOOLS:
                raise PermissionError(
                    f"Unauthorized tool override: Core execution tool '{tool_name}' is protected. "
                    f"Pass allow_override=True to explicitly replace this tool."
                )

        tool_aliases = aliases if aliases is not None else list(getattr(instance or handler_cls, "aliases", []))
        tool_category = category or getattr(instance or handler_cls, "category", "GENERAL")
        tool_parallel_safe = parallel_safe if parallel_safe is not None else getattr(instance or handler_cls, "parallel_safe", True)

        self._handler_classes[tool_name] = cast(Type[ToolHandler], handler_cls)
        if instance is not None:
            instance.name = tool_name
            instance.aliases = tool_aliases
            instance.category = tool_category
            instance.parallel_safe = tool_parallel_safe
            if protected:
                instance.protected = True
            self._handlers[tool_name] = instance

        for alias in tool_aliases:
            self._aliases[alias] = tool_name

        cat_key = tool_category.upper()
        if cat_key not in self._categories:
            self._categories[cat_key] = []
        if tool_name not in self._categories[cat_key]:
            self._categories[cat_key].append(tool_name)

        return handler_cls_or_instance

    def register_disposable(self, *args, **kwargs) -> tuple[Any, Callable[[], None]]:
        """Register a tool and return (registered_tool, disposer_fn)."""
        res = self.register(*args, **kwargs)
        name = getattr(res, "name", None) or (args[1] if len(args) > 1 else kwargs.get("name"))
        return res, lambda: self.unregister(str(name))

    def unregister(self, tool_name: str) -> None:
        """Remove a tool from registry."""
        canonical = self.resolve_name(tool_name)
        if canonical in self._tools:
            tool = self._tools.pop(canonical)
            if tool.toolset in self._toolsets:
                self._toolsets[tool.toolset].discard(canonical)
        self._handlers.pop(canonical, None)
        self._handler_classes.pop(canonical, None)

    def register_handler(self, name: str, handler: Any) -> None:
        """Register a callable or handler instance directly by name."""
        self._handlers[name] = handler
        if hasattr(handler, "name") and not getattr(handler, "name"):
            try:
                setattr(handler, "name", name)
            except Exception:
                pass

    def has_tool(self, name: str) -> bool:
        """Check if a tool or handler is registered under the given name."""
        canonical = self.resolve_name(name)
        return (
            canonical in self._tools
            or canonical in self._handlers
            or canonical in self._handler_classes
        )

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

        # 1. Pre-tool Hook Interception with fail-closed safety
        try:
            from harness.engine import get_plugin_engine
            engine = get_plugin_engine()
            if engine:
                hook_res = await engine.emit_hook(
                    "pre_tool_call",
                    tool_name=canonical,
                    arguments=arguments,
                    context=context,
                )
                for hr in hook_res:
                    if isinstance(hr, dict) and hr.get("abort"):
                        reason = hr.get("reason", "Vetoed by security hook.")
                        logger.warning(f"[ToolSecurity] Tool '{canonical}' aborted by plugin hook: {reason}")
                        return {"error": f"Tool '{canonical}' execution aborted: {reason}", "is_error": True}
        except Exception as hook_err:
            logger.debug(f"[ToolDispatch] pre_tool_call notice: {hook_err}")

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

            # 2. Post-tool Hook Interception
            try:
                from harness.engine import get_plugin_engine
                engine = get_plugin_engine()
                if engine:
                    await engine.emit_hook(
                        "post_tool_call",
                        tool_name=canonical,
                        arguments=arguments,
                        result=result,
                        context=context,
                    )
            except Exception as hook_err:
                logger.debug(f"[ToolDispatch] post_tool_call notice: {hook_err}")

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
        """Dynamically import all handler submodules with AST pre-filtering (Phase 4.4)."""
        try:
            pkg = importlib.import_module(package_name)
            if hasattr(pkg, "__path__"):
                for _, modname, _ in pkgutil.iter_modules(pkg.__path__):
                    # AST pre-scan: find file path and skip files with no tool registrations
                    should_import = True
                    for p in pkg.__path__:
                        candidate_file = os.path.join(p, f"{modname}.py")
                        if os.path.isfile(candidate_file):
                            if not _module_has_tool_registration(candidate_file):
                                should_import = False
                                logger.debug(f"[AST Pre-Scan] Skipped module {modname} (no tool registrations found)")
                            break
                    if not should_import:
                        continue

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
