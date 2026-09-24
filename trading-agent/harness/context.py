# ==============================================================================
# File: harness/context.py
# ==============================================================================

"""
Universal Plugin Context for Monika Trading Harness.
Provides a unified facade for native class plugins and functional script extensions (register(ctx)).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

logger = logging.getLogger("TradingAgent.Harness.Context")


class PluginContext:
    """
    Universal Plugin Context provided to all plugins during registration.
    Exposes hook subscriptions, tool registrations, system prompt sections,
    slash commands, background concurrency, and runtime discovery.
    """

    def __init__(
        self,
        plugin_id: str,
        engine: Any,
        manifest: Any = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self._plugin_id = plugin_id
        self._engine = engine
        self._manifest = manifest
        self._config: Dict[str, Any] = config or {}
        self._state: Dict[str, Any] = {}
        self._disposers: List[Callable[[], Any]] = []
        self._logger = logging.getLogger(f"TradingAgent.Plugin.{plugin_id}")

    @property
    def plugin_id(self) -> str:
        """Unique ID of the owning plugin."""
        return self._plugin_id

    @property
    def manifest(self) -> Any:
        """Manifest or metadata associated with this plugin."""
        return self._manifest

    @property
    def config(self) -> Dict[str, Any]:
        """Plugin-specific configuration dictionary."""
        return self._config

    @property
    def state(self) -> Dict[str, Any]:
        """In-memory key-value state for this plugin."""
        return self._state

    @property
    def logger(self) -> logging.Logger:
        """Scoped logger for this plugin."""
        return self._logger

    @property
    def container(self) -> Any:
        """ServiceContainer dependency injection locator."""
        return getattr(self._engine, "container", None)

    @property
    def event_bus(self) -> Any:
        """Typed async EventBus for market data and system events."""
        return getattr(self._engine, "event_bus", None)

    @property
    def task_registry(self) -> Any:
        """TaskRegistry for monitored background tasks."""
        return getattr(self._engine, "task_registry", None)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value by key."""
        return self._config.get(key, default)

    def set_config(self, key: str, value: Any) -> None:
        """Update a configuration value in-memory."""
        self._config[key] = value

    def has_plugin(self, plugin_id: str) -> bool:
        """Check if another plugin is currently registered and enabled."""
        if hasattr(self._engine, "plugins"):
            p = self._engine.plugins.get(plugin_id)
            return p is not None and getattr(p, "is_enabled", True)
        return False

    def on_unload(self, callback: Callable[[], Any]) -> Callable[[], Any]:
        """Register a teardown disposer executed when the plugin stops (LIFO)."""
        self._disposers.append(callback)
        return callback

    def register_hook(
        self,
        hook_name: str,
        callback: Callable,
        priority: int = 0,
    ) -> Callable[[], None]:
        """
        Register a callback for a specific lifecycle hook (e.g., pre_tool_call, post_llm_call).
        Returns a disposer unregistering the hook.
        """
        if hasattr(self._engine, "register_hook"):
            disposer = self._engine.register_hook(hook_name, callback, priority=priority, plugin_id=self.plugin_id)
            self.on_unload(disposer)
            return disposer
        return lambda: None

    def register_tool(
        self,
        name: str,
        handler: Callable,
        schema: Optional[Dict[str, Any]] = None,
        override: bool = False,
        description: str = "",
        toolset: str = "custom_plugins",
    ) -> bool:
        """
        Register a tool callable to Monika's ToolRegistry.
        Supports tool override protection via engine capabilities.
        """
        if hasattr(self._engine, "register_tool_from_plugin"):
            success = self._engine.register_tool_from_plugin(
                plugin_id=self.plugin_id,
                name=name,
                handler=handler,
                schema=schema,
                override=override,
                description=description,
                toolset=toolset,
            )
            if success:
                self.on_unload(lambda: self._engine.unregister_tool_from_plugin(name))
            return success
        return False

    def register_system_prompt_section(
        self,
        id: str,
        content: Union[str, Callable[[Mapping[str, Any]], str]],
        position: str = "after_memory",
        max_chars: int = 2000,
    ) -> bool:
        """
        Register a modular system prompt section injected into LLM instructions.
        Positions: 'before_instructions', 'after_memory', 'system_append'.
        Supports both (id, content, position=...) and shorthand (position, content).
        """
        if id in ("before_instructions", "after_memory", "system_append") and position == "after_memory":
            actual_position = id
            actual_id = f"{self.plugin_id}_{id}"
        else:
            actual_position = position
            actual_id = id

        if hasattr(self._engine, "register_prompt_section"):
            success = self._engine.register_prompt_section(
                plugin_id=self.plugin_id,
                section_id=actual_id,
                content=content,
                position=actual_position,
                max_chars=max_chars,
            )
            if success:
                self.on_unload(lambda: self._engine.unregister_prompt_section(actual_id))
            return success
        return False

    def register_command(
        self,
        name: str,
        handler: Callable[[str], Any],
        description: str = "",
    ) -> bool:
        """
        Register an in-session slash command (e.g. /disk-cleanup or /custom).
        """
        clean = name.lower().strip().lstrip("/").replace(" ", "-")
        if hasattr(self._engine, "register_command"):
            success = self._engine.register_command(clean, handler, description, self.plugin_id)
            if success:
                self.on_unload(lambda: self._engine.unregister_command(clean))
            return success
        return False

    def register_cli_command(
        self,
        name: str,
        help: str,
        setup_fn: Callable,
        handler_fn: Optional[Callable] = None,
        description: str = "",
    ) -> bool:
        """
        Register a CLI subcommand for Monika.
        """
        if hasattr(self._engine, "register_cli_command"):
            return self._engine.register_cli_command(name, help, setup_fn, handler_fn, description, self.plugin_id)
        return False

    def spawn_task(
        self,
        coro: Any,
        name: Optional[str] = None,
    ) -> asyncio.Task:
        """
        Spawn a supervised asyncio task tracked by the harness engine.
        Automatically cancelled when the plugin unloads.
        """
        if not asyncio.iscoroutine(coro):
            raise TypeError("spawn_task requires an awaitable coroutine object.")

        loop = asyncio.get_running_loop()
        task_name = name or f"plugin:{self.plugin_id}:task"
        task = loop.create_task(coro, name=task_name)

        def _cancel():
            if not task.done():
                task.cancel()

        self.on_unload(_cancel)
        return task

    def emit(self, event: str, payload: Optional[Dict[str, Any]] = None) -> int:
        """
        Publish a plugin-scoped event into the harness dispatcher.
        """
        if hasattr(self._engine, "emit_plugin_event"):
            return self._engine.emit_plugin_event(self.plugin_id, event, payload or {})
        return 0

    async def call_mcp(
        self,
        server: str,
        tool: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Execute an MCP tool via Monika's MCP client with error and timeout boundaries.
        """
        try:
            from analysis.mcp.client import MCPClientManager
            manager = MCPClientManager.get_instance()
            if manager:
                return await manager.call_tool(server, tool, arguments or {}, timeout=timeout)
        except Exception as e:
            self._logger.warning(f"call_mcp error for {server}/{tool}: {e}")
        return {"ok": False, "error": f"MCP tool {server}/{tool} unavailable."}

    async def teardown(self) -> None:
        """Execute registered teardown disposers in LIFO order."""
        for disposer in reversed(self._disposers):
            try:
                res = disposer()
                if inspect.isawaitable(res):
                    await res
            except Exception as e:
                self._logger.debug(f"Disposer exception during teardown: {e}")
        self._disposers.clear()
