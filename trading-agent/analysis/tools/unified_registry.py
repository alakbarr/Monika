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
import logging
from typing import Any, Callable, Dict, List, Optional, Type, Union
from pydantic import BaseModel
from analysis.tools.kernel.output_spiller import truncate_and_spill_output

logger = logging.getLogger("TradingAgent.Tools.UnifiedRegistry")


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
                item for item in v
                if isinstance(item, dict) and str(item.get("type", "")).lower() != "null"
            ]
            has_null = any(
                isinstance(item, dict) and str(item.get("type", "")).lower() == "null"
                for item in v
            )
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
        """Return base JSON schema parameters dictionary."""
        if self.input_model is not None:
            schema = self.input_model.model_json_schema()
            schema.pop("title", None)
            schema.pop("$defs", None)
            return schema
        if self.parameters_schema:
            schema = dict(self.parameters_schema)
            schema.pop("title", None)
            schema.pop("$defs", None)
            return schema
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
        return None

    def list_tools(self, category: Optional[str] = None, only_available: bool = True) -> List[ToolEntry]:
        """List all registered tools, optionally filtered by category and availability."""
        res: List[ToolEntry] = []
        for t in self._tools.values():
            if category and t.category.upper() != category.upper():
                continue
            if only_available and not t.is_available():
                continue
            res.append(t)
        return sorted(res, key=lambda t: t.name)

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
        call_kwargs: Dict[str, Any] = {}
        if "context" in sig.parameters and context is not None:
            call_kwargs["context"] = context
        if "session" in sig.parameters and session is not None:
            call_kwargs["session"] = session
        if "executor" in sig.parameters and executor is not None:
            call_kwargs["executor"] = executor
        for k, v in extra_kwargs.items():
            if k in sig.parameters:
                call_kwargs[k] = v

        coro_or_val: Any
        # Check if handler expects positional args or kwargs
        params_list = list(sig.parameters.values())
        if params_list and params_list[0].kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
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
            result_str = str(raw_result)
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

