# ==============================================================================
# File: analysis/tools/unified_registry.py
# Description: Unified Type-Safe Tool Registry with Pydantic v2 Schema Generation
# ==============================================================================

"""
Single Source of Truth Tool Registry for Monika.
Replaces manual dictionary schemas with declarative, type-safe Pydantic v2 models.
Automatically translates to Anthropic, OpenAI, and Gemini tool calling formats.
"""

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel
from analysis.tools.kernel.output_spiller import truncate_and_spill_output

logger = logging.getLogger("TradingAgent.Tools.UnifiedRegistry")


class ToolEntry:
    """Registered tool definition metadata."""

    def __init__(
        self,
        name: str,
        category: str,
        description: str,
        input_model: Type[BaseModel],
        handler: Callable,
        check_fn: Optional[Callable[[], bool]] = None,
        is_async: bool = True,
    ):
        self.name = name
        self.category = category
        self.description = description
        self.input_model = input_model
        self.handler = handler
        self.check_fn = check_fn
        self.is_async = is_async

    def get_anthropic_schema(self) -> Dict[str, Any]:
        """Convert Pydantic v2 model to Anthropic tool schema format."""
        schema = self.input_model.model_json_schema()
        # Clean up pydantic metadata titles if present
        schema.pop("title", None)
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema,
        }

    def get_openai_schema(self) -> Dict[str, Any]:
        """Convert Pydantic v2 model to OpenAI tool function format."""
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
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
    """Central registry and dispatcher for all trading analysis tools."""

    def __init__(self):
        self._tools: Dict[str, ToolEntry] = {}

    def register(
        self,
        name: str,
        category: str,
        input_model: Type[BaseModel],
        check_fn: Optional[Callable[[], bool]] = None,
    ) -> Callable:
        """Decorator to register a tool handler function."""
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
            )
            self._tools[name] = entry
            return fn
        return decorator

    def get_tool(self, name: str) -> Optional[ToolEntry]:
        """Retrieve registered tool entry by name."""
        return self._tools.get(name)

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

    async def dispatch(self, name: str, arguments: Dict[str, Any], context: Any = None) -> str:
        """
        Validate input via Pydantic model, execute handler, and truncate/spill output.
        """
        entry = self.get_tool(name)
        if not entry:
            raise KeyError(f"Tool '{name}' is not registered in UnifiedToolRegistry.")

        # Validate arguments against Pydantic schema
        try:
            validated_args = entry.input_model.model_validate(arguments or {})
        except Exception as val_err:
            return f"Error: Invalid arguments for tool '{name}': {val_err}"

        try:
            if entry.is_async:
                # Pass context if handler accepts it
                sig = inspect.signature(entry.handler)
                if "context" in sig.parameters:
                    raw_result = await entry.handler(validated_args, context=context)
                else:
                    raw_result = await entry.handler(validated_args)
            else:
                raw_result = entry.handler(validated_args)

            result_str = str(raw_result)
        except Exception as exec_err:
            logger.error(f"Execution of tool '{name}' failed: {exec_err}", exc_info=True)
            result_str = f"Error executing tool '{name}': {exec_err}"

        # Bound and spill oversized output
        processed_result, _ = truncate_and_spill_output(result_str, tool_name=name)
        return processed_result


# Global singleton instance
unified_tool_registry = UnifiedToolRegistry()
