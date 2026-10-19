# ==============================================================================
# File: analysis/tools/unified_registry.py
# Description: Unified Type-Safe Tool Registry with Pydantic v2 Schema Generation
# ==============================================================================

"""
Single Source of Truth Tool Registry for Monika.
Replaces manual dictionary schemas with declarative, type-safe Pydantic v2 models or dynamic JSON schemas.
Automatically translates to Anthropic, OpenAI, and Gemini tool calling formats.
"""

import asyncio
import inspect
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from pydantic import BaseModel

from monika.application.analysis.tools.kernel.output_spiller import truncate_and_spill_output

logger = logging.getLogger("TradingAgent.Tools.UnifiedRegistry")

# ==============================================================================
# Standard Modular Toolset Definitions (Phase 4)
# ==============================================================================
TRADING_TOOLSET: Set[str] = {
    # Market Data & Analysis
    "get_market_data",
    "fetch_market_data",
    "get_economic_calendar",
    "fetch_economic_calendar",
    "calculate_technical_indicators",
    "get_smc_levels",
    "get_order_flow",
    # Position & Execution
    "get_open_positions",
    "get_account_balance",
    "propose_trade",
    "modify_position",
    "close_position",
    # Alpha Factors
    "evaluate_alpha_factors",
    "get_alpha_catalog",
}

DEVELOPER_TOOLSET: Set[str] = {
    # Code Execution & Sandboxing
    "execute_python_code",
    "execute_code",
    "run_terminal_command",
    # File Operations
    "read_file",
    "write_file",
    "patch_file",
    "list_directory",
    "search_files",
    # Workspace & Tasks
    "manage_todo",
    "update_kanban_board",
    "retrieve_spilled_context",
}

RESEARCH_TOOLSET: Set[str] = {
    # Web & Academic Research
    "web_search",
    "web_fetch",
    "search_academic_papers",
    "summarize_document",
    # Visual & Multimodal
    "inspect_chart_image",
    "describe_image",
    "browse_web_page",
    # Skills & Knowledge
    "search_skills",
    "invoke_skill",
    "ask_clarification",
}

TOOLSETS: Dict[str, Set[str]] = {
    "TRADING": TRADING_TOOLSET,
    "DEVELOPER": DEVELOPER_TOOLSET,
    "RESEARCH": RESEARCH_TOOLSET,
}


def _sanitize_schema_for_gemini(schema: dict) -> dict:
    """Sanitize JSON Schema for Google Gemini Function Calling format."""
    if not isinstance(schema, dict):
        return schema

    sanitized = {}
    for k, v in schema.items():
        if k in ("additionalProperties", "$defs", "$schema"):
            continue
        if k == "anyOf" and isinstance(v, list):
            non_null_items = [
                item for item in v if isinstance(item, dict) and str(item.get("type", "")).lower() != "null"
            ]
            has_null = any(isinstance(item, dict) and str(item.get("type", "")).lower() == "null" for item in v)
            if has_null and len(non_null_items) == 1:
                inner = _sanitize_schema_for_gemini(non_null_items[0])
                for ik, iv in inner.items():
                    sanitized[ik] = iv
                sanitized["nullable"] = True
                continue
        if k == "type" and isinstance(v, list):
            valid_types = [t for t in v if t != "null"]
            sanitized[k] = valid_types[0].upper() if valid_types else "STRING"
            if "null" in v:
                sanitized["nullable"] = True
            continue
        if k == "type" and isinstance(v, str):
            sanitized[k] = v.upper()
            continue

        if isinstance(v, dict):
            sanitized[k] = _sanitize_schema_for_gemini(v)
        elif isinstance(v, list):
            sanitized[k] = [_sanitize_schema_for_gemini(item) if isinstance(item, dict) else item for item in v]
        else:
            sanitized[k] = v

    return sanitized


class ToolEntry:
    """Registered tool definition metadata supporting Pydantic models and dynamic JSON schemas."""

    def __init__(
        self,
        name: str,
        category: str,
        description: str,
        handler: Callable,
        input_model: Optional[Type[BaseModel]] = None,
        parameters_schema: Optional[Dict[str, Any]] = None,
        check_fn: Optional[Callable[[], bool]] = None,
        is_async: bool = True,
        aliases: Optional[List[str]] = None,
        timeout_seconds: float = 30.0,
        parallel_safe: bool = True,
    ):
        self.name = name
        self.category = category
        self.description = description
        self.handler = handler
        self.input_model = input_model
        self.parameters_schema = parameters_schema or {}
        self.check_fn = check_fn
        self.is_async = is_async
        self.aliases = aliases or []
        self.timeout_seconds = timeout_seconds
        self.parallel_safe = parallel_safe

    def get_parameters_schema(self) -> Dict[str, Any]:
        """Return base JSON schema parameters dictionary with inlined references."""
        from monika.application.analysis.schemas.schemas import _inline_refs

        if self.input_model is not None:
            schema = self.input_model.model_json_schema()
            schema.pop("title", None)
            return _inline_refs(schema)
        if self.parameters_schema:
            schema = dict(self.parameters_schema)
            schema.pop("title", None)
            return _inline_refs(schema)
        return {"type": "object", "properties": {}}

    def get_anthropic_schema(self) -> Dict[str, Any]:
        """Convert to Anthropic tool schema format."""
        schema = self.get_parameters_schema()
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema,
        }

    def get_openai_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI tool function format."""
        schema = self.get_parameters_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }

    def get_gemini_schema(self) -> Dict[str, Any]:
        """Convert to Gemini function declaration format."""
        schema = _sanitize_schema_for_gemini(self.get_parameters_schema())
        return {
            "name": self.name,
            "description": self.description,
            "parameters": schema,
        }

    def is_available(self) -> bool:
        """Evaluate availability check function if provided."""
        if self.check_fn is None:
            return True
        try:
            return bool(self.check_fn())
        except Exception as e:
            logger.debug(f"Availability check for {self.name} failed: {e}")
            return False


def run_security_interceptors(name: str, arguments: Dict[str, Any]) -> None:
    """
    Centralized Security Interceptor Pipeline:
    1. PromptInjectionScanner: Evaluates prompt and user message inputs.
    2. SSRFGuard: Validates outbound network URLs against private/metadata IPs.
    3. TerminalGuard: Blocks prohibited host execution commands.
    4. PathReadWriteGuard: Blocks unauthorized read/write access to secret credentials (.env*, *.key, *.pem).
    """
    if not isinstance(arguments, dict):
        return

    # Stage 1: Prompt Injection Scanner
    try:
        from monika.core.security.prompt_injection_scanner import PromptInjectionScanner

        for k, v in arguments.items():
            if isinstance(v, str) and len(v) > 20:
                if k in ("prompt", "query", "text", "message", "instruction", "content", "news_text"):
                    PromptInjectionScanner.assert_safe(v, threshold=0.85)
    except Exception as pi_err:
        if "PromptInjectionThreatDetected" in type(pi_err).__name__:
            raise

    # Stage 2: SSRF Guard
    try:
        from monika.core.security.ssrf_guard import validate_request_url

        for k, v in arguments.items():
            if isinstance(v, str) and (
                k in ("url", "uri", "endpoint", "target_url") or v.startswith(("http://", "https://"))
            ):
                validate_request_url(v)
    except Exception as ssrf_err:
        if "SSRFViolationError" in type(ssrf_err).__name__:
            raise

    # Stage 3: Terminal Guard
    try:
        from monika.core.security.terminal_guard import CommandSecurityViolationError, is_hardline_blocked_command

        for k, v in arguments.items():
            if isinstance(v, str) and k in ("command", "cmd", "exec_cmd"):
                is_blocked, reason = is_hardline_blocked_command(v)
                if is_blocked:
                    raise CommandSecurityViolationError(f"Prohibited terminal command: {reason}")
    except Exception as term_err:
        if "CommandSecurityViolationError" in type(term_err).__name__:
            raise

    # Stage 4: Path Read / Write Guard
    try:
        from monika.core.security.nt_guard import SecurityViolationError
        from monika.core.security.terminal_guard import assert_safe_read_path, assert_safe_write_path

        for k, v in arguments.items():
            if isinstance(v, str) and k in ("path", "file_path", "filepath", "source_path", "target_path"):
                if name in ("write_file", "patch", "delete_file", "append_file", "save_file"):
                    assert_safe_write_path(v)
                elif name in ("read_file", "view_file", "inspect_file", "get_file"):
                    assert_safe_read_path(v)
    except Exception as path_err:
        if "SecurityViolationError" in type(path_err).__name__:
            raise


class UnifiedToolRegistry:
    """Central registry and dispatcher for all trading analysis and general-purpose tools."""

    def __init__(self):
        self._tools: Dict[str, ToolEntry] = {}
        self._aliases: Dict[str, str] = {}

    def register(
        self,
        name: str,
        category: str,
        input_model: Type[BaseModel],
        check_fn: Optional[Callable[[], bool]] = None,
        timeout_seconds: float = 30.0,
        parallel_safe: bool = True,
    ) -> Callable:
        """Decorator to register a tool handler function with a Pydantic model."""

        def decorator(fn: Callable) -> Callable:
            desc = (input_model.__doc__ or fn.__doc__ or "").strip()
            is_async = inspect.iscoroutinefunction(fn)
            entry = ToolEntry(
                name=name,
                category=category,
                description=desc,
                input_model=input_model,
                handler=fn,
                check_fn=check_fn,
                is_async=is_async,
                timeout_seconds=timeout_seconds,
                parallel_safe=parallel_safe,
            )
            self._tools[name] = entry
            return fn

        return decorator

    def register_tool(
        self,
        name: str,
        category: str,
        handler: Callable,
        input_model: Optional[Type[BaseModel]] = None,
        parameters_schema: Optional[Dict[str, Any]] = None,
        description: str = "",
        is_async: Optional[bool] = None,
        check_fn: Optional[Callable[[], bool]] = None,
        aliases: Optional[List[str]] = None,
        timeout_seconds: float = 30.0,
        parallel_safe: bool = True,
    ) -> ToolEntry:
        """Imperative method to register a tool handler function or MCP bridge."""
        if is_async is None:
            is_async = inspect.iscoroutinefunction(handler)
        if not description and input_model:
            description = (input_model.__doc__ or "").strip()
        if not description and hasattr(handler, "__doc__") and handler.__doc__:
            description = handler.__doc__.strip()

        entry = ToolEntry(
            name=name,
            category=category,
            description=description,
            handler=handler,
            input_model=input_model,
            parameters_schema=parameters_schema,
            check_fn=check_fn,
            is_async=is_async,
            aliases=aliases,
            timeout_seconds=timeout_seconds,
            parallel_safe=parallel_safe,
        )
        self._tools[name] = entry
        if aliases:
            for alias in aliases:
                self._aliases[alias] = name
        return entry

    def get_tool(self, name: str) -> Optional[ToolEntry]:
        """Retrieve registered tool entry by name or alias."""
        if name in self._tools:
            return self._tools[name]
        aliased = self._aliases.get(name)
        if aliased and aliased in self._tools:
            return self._tools[aliased]
        # Fallback bridge to default_tool_registry
        try:
            from monika.application.analysis.tools.registry import default_tool_registry

            canonical = default_tool_registry.resolve_name(name)
            def_tool = (
                default_tool_registry._tools.get(canonical)
                or default_tool_registry._handlers.get(canonical)
                or default_tool_registry._handler_classes.get(canonical)
            )
            if def_tool is not None:
                desc = getattr(def_tool, "description", "") or (getattr(def_tool, "__doc__", "") or "").strip()
                raw_handler = getattr(def_tool, "handler", def_tool)
                if inspect.isclass(raw_handler):
                    try:
                        raw_handler = raw_handler()
                    except Exception:
                        pass
                if hasattr(raw_handler, "execute") and callable(getattr(raw_handler, "execute")):
                    handler: Callable[..., Any] = raw_handler.execute
                elif callable(raw_handler):
                    handler = raw_handler
                else:
                    handler = lambda **kw: None
                params_schema = getattr(def_tool, "parameters", {})
                entry = ToolEntry(
                    name=canonical,
                    category=getattr(def_tool, "toolset", "TRADING").upper(),
                    description=desc,
                    handler=handler,
                    parameters_schema=params_schema,
                    is_async=inspect.iscoroutinefunction(handler),
                )
                self._tools[canonical] = entry
                return entry
        except Exception:
            pass
        return None

    def list_tools(self, category: Optional[str] = None, only_available: bool = True) -> List[ToolEntry]:
        """List all registered tools, optionally filtered by category and availability."""
        seen_names: Set[str] = set()
        res: List[ToolEntry] = []
        for t in self._tools.values():
            if t.name in seen_names:
                continue
            seen_names.add(t.name)
            if category and t.category.upper() != category.upper():
                continue
            if only_available and not t.is_available():
                continue
            res.append(t)

        # Bridge all discovered tools from default_tool_registry
        try:
            from monika.application.analysis.tools.registry import default_tool_registry

            if not default_tool_registry._tools and not default_tool_registry._handlers:
                default_tool_registry.auto_discover()

            for def_name in default_tool_registry.list_tools():
                if def_name in seen_names or def_name in self._aliases:
                    continue
                entry = self.get_tool(def_name)
                if entry:
                    seen_names.add(def_name)
                    if category and entry.category.upper() != category.upper():
                        continue
                    if only_available and not entry.is_available():
                        continue
                    res.append(entry)
        except Exception as e:
            logger.debug(f"[UnifiedToolRegistry] Error bridging default tools: {e}")

        return sorted(res, key=lambda t: t.name)

    def get_tools(self, category: Optional[str] = None, only_available: bool = True) -> List[ToolEntry]:
        """Alias for list_tools() ensuring complete API compatibility across callers."""
        return self.list_tools(category=category, only_available=only_available)

    def get_anthropic_tools(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return list of Anthropic-compatible tool schemas, canonically sorted."""
        tools = self.list_tools(category=category, only_available=True)
        return [t.get_anthropic_schema() for t in tools]

    def get_openai_tools(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return list of OpenAI-compatible tool schemas, canonically sorted."""
        tools = self.list_tools(category=category, only_available=True)
        return [t.get_openai_schema() for t in tools]

    def get_gemini_tools(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return list of Gemini-compatible function declarations, canonically sorted."""
        tools = self.list_tools(category=category, only_available=True)
        return [t.get_gemini_schema() for t in tools]

    def list_toolset_names(self, toolset: str) -> List[str]:
        """Return canonical list of tool names belonging to the given toolset ('TRADING', 'DEVELOPER', 'RESEARCH')."""
        key = toolset.upper()
        allowed = TOOLSETS.get(key)
        if allowed is None:
            raise ValueError(f"Unknown toolset: '{toolset}'. Available: {list(TOOLSETS.keys())}")
        return [t.name for t in self.list_tools(only_available=False) if t.name in allowed]

    def get_toolset(self, toolset: str, format: str = "openai") -> List[Dict[str, Any]]:
        """Return serialized tool schemas for specified toolset in specified provider format ('openai', 'anthropic', 'gemini')."""
        key = toolset.upper()
        allowed = TOOLSETS.get(key)
        if allowed is None:
            raise ValueError(f"Unknown toolset: '{toolset}'. Available: {list(TOOLSETS.keys())}")
        tools = [t for t in self.list_tools(only_available=True) if t.name in allowed]
        fmt = format.lower()
        if fmt == "anthropic":
            return [t.get_anthropic_schema() for t in tools]
        elif fmt == "gemini":
            return [t.get_gemini_schema() for t in tools]
        else:
            return [t.get_openai_schema() for t in tools]

    def _run_security_interceptors(self, name: str, arguments: Dict[str, Any]) -> None:
        """Centralized Security Interceptor Pipeline delegator."""
        run_security_interceptors(name, arguments)

    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: Any = None,
        session: Any = None,
        executor: Any = None,
        **extra_kwargs: Any,
    ) -> Any:
        """
        Execute tool natively, passing validated arguments and context as appropriate.
        Returns the raw return value of the tool handler.
        """
        entry = self.get_tool(name)
        if not entry:
            raise KeyError(f"Tool '{name}' is not registered in UnifiedToolRegistry.")

        # Run Centralized Security Interceptor Pipeline before executing handler
        self._run_security_interceptors(name, arguments or {})

        # Validate arguments against Pydantic schema if provided
        args_payload: Any = arguments or {}
        if entry.input_model is not None:
            try:
                args_payload = entry.input_model.model_validate(arguments or {})
            except Exception as val_err:
                # If validation fails, try coercing string dict or fallback
                logger.warning(f"Validation failed for {name} with {arguments}: {val_err}")
                raise ValueError(f"Invalid arguments for tool '{name}': {val_err}")

        # Build invocation kwargs based on handler signature
        sig = inspect.signature(entry.handler)
        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        call_kwargs: Dict[str, Any] = {}
        if ("context" in sig.parameters or has_var_keyword) and context is not None:
            call_kwargs["context"] = context
        if ("session" in sig.parameters or has_var_keyword) and session is not None:
            call_kwargs["session"] = session
        if ("executor" in sig.parameters or has_var_keyword) and executor is not None:
            call_kwargs["executor"] = executor
        for k, v in extra_kwargs.items():
            if k in sig.parameters or has_var_keyword:
                call_kwargs[k] = v

        coro_or_val: Any
        # Check if handler expects positional args or kwargs
        params_list = list(sig.parameters.values())
        if params_list and params_list[0].kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            coro_or_val = entry.handler(args_payload, **call_kwargs)
        else:
            coro_or_val = entry.handler(**call_kwargs)

        if inspect.isawaitable(coro_or_val):
            return await asyncio.wait_for(coro_or_val, timeout=entry.timeout_seconds)
        return coro_or_val

    async def dispatch(self, name: str, arguments: Dict[str, Any], context: Any = None, **kwargs: Any) -> str:
        """
        Validate input via Pydantic model, execute handler, and truncate/spill output.
        Returns string representation bounded by output spiller.
        """
        entry = self.get_tool(name)
        if not entry:
            return f"Error: Tool '{name}' is not registered in UnifiedToolRegistry."

        try:
            raw_result = await self.execute_tool(name, arguments, context=context, **kwargs)
            result_str = raw_result if isinstance(raw_result, str) else str(raw_result)
        except asyncio.TimeoutError:
            result_str = f"Error: Tool '{name}' timed out after {entry.timeout_seconds}s deadline."
        except Exception as exec_err:
            logger.error(f"Execution of tool '{name}' failed: {exec_err}", exc_info=True)
            result_str = f"Error executing tool '{name}': {exec_err}"

        # Bound and spill oversized output
        processed_result, _ = truncate_and_spill_output(result_str, tool_name=name)
        return processed_result

    async def tool_call(self, name: str, arguments: Dict[str, Any], **kwargs: Any) -> str:
        """Direct bridge method for agent loop tool calling."""
        return await self.dispatch(name, arguments, **kwargs)


# Global singleton instance
unified_tool_registry = UnifiedToolRegistry()
