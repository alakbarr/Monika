# ==============================================================================
# File: harness/engine.py
# ==============================================================================

"""
Plugin Engine for Monika Trading Harness.
Provides entry-point & directory discovery, dependency resolution (Kahn's topological sort),
lifecycle orchestration, and clean teardown via disposer stacks.
"""

import os
import sys
import yaml
import asyncio
import inspect
import logging
import importlib
import importlib.util
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional, Any, Callable, Type, Set

from harness.contract import (
    TradingPlugin,
    PluginMetadata,
    PluginCategory,
    PluginOrigin,
    PluginState,
)
from harness.context import PluginContext
from utils.plugins.manager import PluginManager, get_plugin_manager
from analysis.prompt_sections import get_prompt_section_registry
from utils.infra.container import ServiceContainer, get_container
from utils.protocol.event_bus import (
    EventBus,
    get_event_bus,
    TickPriceEvent,
    BarClosedEvent,
    OrderStateChangedEvent,
    RiskBreachEvent,
    CircuitBreakerEvent,
)

try:
    from agent.task_registry import TaskRegistry
except ImportError:
    TaskRegistry = None  # type: ignore

logger = logging.getLogger("TradingAgent.Harness.Engine")


class FunctionalPluginAdapter(TradingPlugin):
    """
    Wraps a functional plugin exposing `register(ctx)` script entry point
    into Monika's TradingPlugin lifecycle contract.
    """
    def __init__(
        self,
        metadata: Optional[PluginMetadata] = None,
        register_fn: Optional[Callable[[Any], Any]] = None,
        config: Optional[dict] = None,
        *,
        plugin_id: Optional[str] = None,
        name: Optional[str] = None,
        version: str = "1.0.0",
        category: PluginCategory = PluginCategory.MIDDLEWARE,
        author: Optional[str] = None,
        description: str = "",
    ):
        if metadata is None:
            pid = plugin_id or "functional_plugin"
            metadata = PluginMetadata(
                id=pid,
                name=name or pid,
                version=version,
                category=category,
                author=author,
                description=description,
                origin=PluginOrigin.LOCAL_DIRECTORY,
            )
        super().__init__(config=config)
        self.metadata = metadata
        self.register_fn = register_fn
        self.is_functional = True

    def on_context_ready(self, ctx: Any) -> None:
        self.context = ctx
        if callable(self.register_fn):
            res = self.register_fn(ctx)
            if inspect.isawaitable(res):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(res)
                except RuntimeError:
                    pass

    async def on_register(self, container: Any, event_bus: Any) -> None:
        if not self.context and callable(self.register_fn):
            res = self.register_fn(container)
            if inspect.isawaitable(res):
                await res

# Standard lifecycle timeouts (in seconds)
LIFECYCLE_TIMEOUT_REGISTER = 10.0
LIFECYCLE_TIMEOUT_PREFLIGHT = 15.0
LIFECYCLE_TIMEOUT_RECOVERY = 15.0
LIFECYCLE_TIMEOUT_START = 15.0
LIFECYCLE_TIMEOUT_STOP = 10.0
LIFECYCLE_TIMEOUT_CONFIG_RELOAD = 5.0


class PluginDependencyError(Exception):
    """Base error for plugin dependency failures."""
    pass


class MissingDependencyError(PluginDependencyError):
    """Raised when a required plugin dependency is missing."""
    pass


class CircularDependencyError(PluginDependencyError):
    """Raised when circular dependencies exist between plugins."""
    pass


def topological_sort_plugins(plugins: List[TradingPlugin]) -> List[TradingPlugin]:
    """
    Sort a list of TradingPlugin instances topologically based on their dependencies.
    Dependencies must load before the plugins that depend on them.
    """
    name_map: Dict[str, TradingPlugin] = {p.metadata.id: p for p in plugins}

    adj: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = {p.metadata.id: 0 for p in plugins}

    for p in plugins:
        for dep in p.metadata.dependencies:
            if dep not in name_map:
                raise MissingDependencyError(
                    f"Plugin '{p.metadata.id}' requires missing dependency '{dep}'"
                )
            adj[dep].append(p.metadata.id)
            in_degree[p.metadata.id] += 1

    queue = deque([name for name, deg in in_degree.items() if deg == 0])
    sorted_ids: List[str] = []

    while queue:
        curr = queue.popleft()
        sorted_ids.append(curr)

        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_ids) != len(plugins):
        cyclic = [name for name, deg in in_degree.items() if deg > 0]
        raise CircularDependencyError(
            f"Circular dependency detected involving plugins: {', '.join(cyclic)}"
        )

    return [name_map[pid] for pid in sorted_ids]


_GLOBAL_ENGINE: Optional["PluginEngine"] = None


def get_plugin_engine() -> Optional["PluginEngine"]:
    """Retrieve active global PluginEngine instance."""
    return _GLOBAL_ENGINE


class PluginEngine:
    """
    Central orchestrator for discovering, loading, and managing plugin lifecycles.
    """

    def __init__(
        self,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        task_registry: Optional[TaskRegistry] = None,
    ):
        global _GLOBAL_ENGINE
        self.container = container or get_container()
        self.event_bus = event_bus or get_event_bus()
        self.task_registry = task_registry
        self.plugins: Dict[str, TradingPlugin] = {}
        self.contexts: Dict[str, PluginContext] = {}
        self.hook_manager: PluginManager = get_plugin_manager()
        self.prompt_registry = get_prompt_section_registry()
        self.ordered_plugins: List[TradingPlugin] = []
        self._disposers: Dict[str, List[Callable[[], Any]]] = defaultdict(list)
        self._system_commands: Dict[str, Tuple[Callable, str, str]] = {}
        self._cli_commands: Dict[str, Dict[str, Any]] = {}
        self._is_started = False
        _GLOBAL_ENGINE = self

    @property
    def registry(self) -> Dict[str, TradingPlugin]:
        """Alias for self.plugins for backward compatibility."""
        return self.plugins

    @property
    def manager(self) -> PluginManager:
        """Alias for self.hook_manager for unified access."""
        return self.hook_manager

    @classmethod
    def get_instance(cls) -> Optional["PluginEngine"]:
        """Retrieve singleton PluginEngine."""
        return _GLOBAL_ENGINE

    def get_context(self, plugin_id: str) -> Optional[PluginContext]:
        """Retrieve PluginContext for a plugin."""
        return self.contexts.get(plugin_id)

    # --- Unified Hook Emitter and Registration ---

    def register_hook(self, hook_name: str, callback: Callable, priority: int = 0, plugin_id: str = "") -> Callable[[], None]:
        """Register a lifecycle hook with the unified PluginManager."""
        return self.hook_manager.register_hook(hook_name, callback)

    def unregister_hook(self, hook_name: str, callback: Callable) -> bool:
        """Unregister a lifecycle hook."""
        return self.hook_manager.unregister_hook(hook_name, callback)

    async def emit_hook(self, hook_name: str, timeout_seconds: float = 5.0, **kwargs: Any) -> List[Any]:
        """Emit a lifecycle event across all registered plugin hooks with timeout boundary."""
        return await self.hook_manager.emit(hook_name, timeout_seconds=timeout_seconds, **kwargs)

    async def emit_waterfall(self, hook_name: str, payload: Any, timeout_seconds: float = 5.0, **kwargs: Any) -> Tuple[bool, Any]:
        """Execute sequential waterfall interceptor hooks (e.g. pre_order, pre_risk_gate)."""
        return await self.hook_manager.emit_waterfall(hook_name, payload, timeout_seconds=timeout_seconds, **kwargs)

    # --- Tool Registration & Override Protection ---

    def register_tool_from_plugin(
        self,
        plugin_id: str,
        name: str,
        handler: Callable,
        schema: Optional[Dict[str, Any]] = None,
        override: bool = False,
        description: str = "",
        toolset: str = "custom_plugins",
    ) -> bool:
        """Register tool into ToolRegistry with core override protection."""
        try:
            from analysis.tools.registry import ToolRegistry, ToolDefinition, CORE_PROTECTED_TOOLS
            reg = ToolRegistry.get_instance()

            # Check core protected tools
            if name in CORE_PROTECTED_TOOLS:
                plugin = self.plugins.get(plugin_id)
                has_override_grant = False
                if plugin:
                    caps = getattr(plugin.metadata, "capabilities", [])
                    if "tools.override" in caps or getattr(plugin, "config", {}).get("allow_tool_override", False):
                        has_override_grant = True

                if not override or not has_override_grant:
                    logger.warning(
                        f"[PluginEngine] Plugin '{plugin_id}' attempted to override core tool '{name}' "
                        f"without operator consent (allow_tool_override: true). Rejected."
                    )
                    raise PermissionError(
                        f"Plugin '{plugin_id}' attempted to override protected core tool '{name}' "
                        f"without operator consent."
                    )

            params = {}
            if schema and isinstance(schema, dict):
                params = schema.get("parameters", schema)

            tool_def = ToolDefinition(
                name=name,
                description=description or f"Plugin tool '{name}' registered by {plugin_id}",
                parameters=params,
                handler=handler,
                toolset=toolset,
            )
            reg.register_definition(tool_def, allow_override=override)
            reg.register_handler(name, handler)
            if name not in self.manager._registered_tools:
                self.manager._registered_tools.append(name)
            logger.info(f"[PluginEngine] Registered tool '{name}' from plugin '{plugin_id}'")
            return True
        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"[PluginEngine] Failed registering tool '{name}' from '{plugin_id}': {e}", exc_info=True)
            return False

    def unregister_tool_from_plugin(self, name: str) -> None:
        """Unregister a plugin-provided tool from ToolRegistry."""
        try:
            from analysis.tools.registry import ToolRegistry
            ToolRegistry.get_instance().unregister(name)
            logger.debug(f"[PluginEngine] Unregistered tool '{name}'")
        except Exception as e:
            logger.debug(f"[PluginEngine] Error unregistering tool '{name}': {e}")

    # --- System Prompt Section Registration ---

    def register_prompt_section(
        self,
        plugin_id: str,
        section_id: str,
        content: Any,
        position: str = "after_memory",
        max_chars: int = 2048,
    ) -> bool:
        """Register a modular system prompt section."""
        return self.prompt_registry.register(
            section_id=section_id,
            content=content,
            position=position,
            max_chars=max_chars,
            plugin_id=plugin_id,
        )

    def unregister_prompt_section(self, section_id: str) -> bool:
        """Unregister a prompt section."""
        return self.prompt_registry.unregister(section_id)

    # --- Slash & CLI Commands ---

    def register_command(self, name: str, handler: Callable, description: str = "", plugin_id: str = "") -> bool:
        """Register in-session slash command."""
        self._system_commands[name] = (handler, description, plugin_id)
        logger.debug(f"[PluginEngine] Registered slash command '/{name}' from '{plugin_id}'")
        return True

    def unregister_command(self, name: str) -> bool:
        """Unregister slash command."""
        return self._system_commands.pop(name, None) is not None

    def register_cli_command(self, name: str, help: str, setup_fn: Callable, handler_fn: Optional[Callable] = None, description: str = "", plugin_id: str = "") -> bool:
        """Register CLI subcommand."""
        self._cli_commands[name] = {
            "name": name, "help": help, "setup_fn": setup_fn, "handler_fn": handler_fn, "description": description, "plugin_id": plugin_id
        }
        return True

    def emit_plugin_event(self, plugin_id: str, event: str, payload: dict) -> int:
        """Publish plugin-scoped event into EventBus or logs."""
        logger.debug(f"[PluginEvent] {plugin_id}:{event} -> {payload}")
        return 1

    def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> bool:
        """Dynamically toggle plugin state and update status in-memory."""
        if plugin_id in self.plugins:
            p = self.plugins[plugin_id]
            p.is_enabled = enabled
            if not enabled:
                p.status = "DISABLED"
            else:
                p.status = "RUNNING" if self._is_started else "READY"
            logger.info(f"[PluginEngine] Set plugin '{plugin_id}' enabled={enabled} (status={p.status})")
            return True
        return False

    def register_plugin_instance(self, plugin: TradingPlugin) -> None:
        """Register a pre-instantiated plugin (e.g. builtins) and bind PluginContext."""
        pid = plugin.metadata.id
        self.plugins[pid] = plugin
        
        # Bind or create PluginContext
        def _invoke_context_ready(p: TradingPlugin, context_obj: PluginContext):
            try:
                res = p.on_context_ready(context_obj)
                if inspect.isawaitable(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        asyncio.run(res)
            except Exception as ex:
                logger.error(f"[PluginEngine] Error in on_context_ready for {p.metadata.id}: {ex}", exc_info=True)

        if pid not in self.contexts:
            ctx = PluginContext(plugin_id=pid, engine=self, manifest=plugin.metadata, config=plugin.config)
            self.contexts[pid] = ctx
            _invoke_context_ready(plugin, ctx)
        elif not getattr(plugin, "context", None):
            _invoke_context_ready(plugin, self.contexts[pid])

        # Auto-wire declared hooks and tools from manifest if present
        manifest_data = getattr(plugin, "manifest", None) or {}
        if isinstance(manifest_data, dict):
            hooks = manifest_data.get("hooks", {})
            if isinstance(hooks, dict):
                for hook_name, method_name in hooks.items():
                    handler = getattr(plugin, method_name, None)
                    if callable(handler):
                        self.register_hook(hook_name, handler, plugin_id=pid)
            elif isinstance(hooks, list):
                for hook_name in hooks:
                    handler = getattr(plugin, hook_name, None) or getattr(plugin, f"on_{hook_name}", None)
                    if callable(handler):
                        self.register_hook(hook_name, handler, plugin_id=pid)

            tools = manifest_data.get("tools", {})
            if isinstance(tools, dict):
                for tool_name, method_or_desc in tools.items():
                    if isinstance(method_or_desc, str) and hasattr(plugin, method_or_desc):
                        handler = getattr(plugin, method_or_desc)
                    elif callable(method_or_desc):
                        handler = method_or_desc
                    else:
                        handler = getattr(plugin, tool_name, None)
                    if callable(handler):
                        self.register_tool_from_plugin(pid, tool_name, handler)

        logger.debug(f"[PluginEngine] Registered plugin instance: {pid} v{plugin.metadata.version}")
        self._dispatch_domain_registration(plugin)

    register_plugin = register_plugin_instance

    def _dispatch_domain_registration(self, plugin: TradingPlugin) -> None:
        """Bridge loaded plugins to their specialized domain registries."""
        cat = getattr(plugin.metadata, "category", None)
        # 1. Broker Plugins
        if cat == PluginCategory.BROKER or hasattr(plugin, "submit_order"):
            try:
                from execution.broker_registry import BrokerAdapterRegistry
                BrokerAdapterRegistry.register(plugin.metadata.id, plugin)
            except Exception as e:
                logger.debug(f"[PluginEngine] Broker domain dispatch note: {e}")

        # 2. LLM Provider Plugins
        if cat == PluginCategory.LLM_PROVIDER or hasattr(plugin, "create_client"):
            try:
                from analysis.providers.provider_registry import ProviderRegistry
                ProviderRegistry.register(plugin.metadata.id, plugin)
            except Exception as e:
                logger.debug(f"[PluginEngine] LLM provider domain dispatch note: {e}")

        # 3. Strategy Plugins
        if cat == PluginCategory.STRATEGY and hasattr(plugin, "get_strategy_class"):
            try:
                from analysis.strategies.registry import StrategyRegistry
                strat_cls = plugin.get_strategy_class()
                StrategyRegistry.register(strat_cls)
            except Exception as e:
                logger.debug(f"[PluginEngine] Strategy domain dispatch note: {e}")

        # 4. Risk Rule / Dynamic Sizing Plugins
        if cat in (PluginCategory.RISK_RULE, PluginCategory.DYNAMIC_SIZING):
            try:
                from risk.risk_rule_plugin import ModularRiskRegistry
                risk_reg = ModularRiskRegistry.get_instance()
                if cat == PluginCategory.RISK_RULE and hasattr(risk_reg, "register_rule"):
                    risk_reg.register_rule(plugin)
                elif cat == PluginCategory.DYNAMIC_SIZING and hasattr(risk_reg, "register_sizing_plugin"):
                    risk_reg.register_sizing_plugin(plugin)
            except Exception as e:
                logger.debug(f"[PluginEngine] Risk domain dispatch note: {e}")

        # 5. Tool Plugins
        if cat == PluginCategory.TOOL and hasattr(plugin, "get_handlers"):
            try:
                from analysis.tools.registry import ToolRegistry
                tool_reg = ToolRegistry.get_instance()
                for name, handler in plugin.get_handlers().items():
                    tool_reg.register_handler(name, handler)
            except Exception as e:
                logger.debug(f"[PluginEngine] Tool domain dispatch note: {e}")

    @property
    def active_pipeline(self) -> Optional[TradingPlugin]:
        """Retrieve active analysis pipeline plugin."""
        for p in self.plugins.values():
            if getattr(p.metadata, "category", None) == PluginCategory.ANALYSIS_PIPELINE and getattr(p, "is_enabled", True):
                return p
        return None

    def discover_entrypoints(self) -> List[TradingPlugin]:
        """
        Discover plugins installed via pip using `entry_points(group='monika.plugins')`.
        """
        discovered: List[TradingPlugin] = []
        try:
            if sys.version_info >= (3, 10):
                from importlib.metadata import entry_points
                eps = entry_points(group="monika.plugins")
            else:
                import pkg_resources
                eps = [ep for ep in pkg_resources.iter_entry_points("monika.plugins")]

            for ep in eps:
                try:
                    plugin_cls = ep.load()
                    if isinstance(plugin_cls, type) and issubclass(plugin_cls, TradingPlugin):
                        inst = plugin_cls()
                        inst.metadata.origin = PluginOrigin.PIP_PACKAGE
                        self.register_plugin_instance(inst)
                        discovered.append(inst)
                        logger.info(f"[PluginEngine] Discovered pip plugin via entry_point: {inst.metadata.id} ({ep.name})")
                    elif callable(plugin_cls):
                        inst = plugin_cls()
                        if isinstance(inst, TradingPlugin):
                            inst.metadata.origin = PluginOrigin.PIP_PACKAGE
                            self.register_plugin_instance(inst)
                            discovered.append(inst)
                            logger.info(f"[PluginEngine] Discovered pip plugin factory via entry_point: {inst.metadata.id}")
                except Exception as ep_err:
                    logger.warning(f"[PluginEngine] Failed loading entry_point '{ep.name}': {ep_err}")
        except Exception as ex:
            logger.debug(f"[PluginEngine] Entry point discovery note: {ex}")
        return discovered

    def discover_directory_plugins(self, directory: str) -> List[TradingPlugin]:
        """
        Scan a local directory for `plugin.yaml` manifests and instantiate plugins.
        """
        discovered: List[TradingPlugin] = []
        if not os.path.isdir(directory):
            return discovered

        for root, _, files in os.walk(directory):
            if "plugin.yaml" in files:
                manifest_path = os.path.join(root, "plugin.yaml")
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        raw = yaml.safe_load(f) or {}

                    pid = raw.get("id") or raw.get("name") or os.path.basename(root)
                    name = raw.get("name", pid)
                    version = str(raw.get("version", "1.0.0"))
                    cat_str = raw.get("category", "middleware").lower()
                    try:
                        category = PluginCategory(cat_str)
                    except ValueError:
                        category = PluginCategory.MIDDLEWARE

                    desc = raw.get("description", "")
                    author = raw.get("author")
                    is_core = bool(raw.get("is_core", False))
                    deps = raw.get("dependencies", [])
                    conflicts = raw.get("conflicts", [])
                    req_pkgs = raw.get("required_packages", [])

                    meta = PluginMetadata(
                        id=pid,
                        name=name,
                        version=version,
                        category=category,
                        description=desc,
                        author=author,
                        origin=PluginOrigin.LOCAL_DIRECTORY,
                        is_core=is_core,
                        dependencies=deps,
                        conflicts=conflicts,
                        required_packages=req_pkgs,
                    )

                    entrypoint = raw.get("entrypoint")
                    mod = None
                    target = None

                    if entrypoint and ":" in entrypoint:
                        mod_part, cls_part = entrypoint.split(":")
                        mod_file = os.path.join(root, *mod_part.split(".")) + ".py"
                        if not os.path.isfile(mod_file):
                            mod_file = os.path.join(root, f"{mod_part}.py")

                        if os.path.isfile(mod_file):
                            spec = importlib.util.spec_from_file_location(f"plugin_{pid}", mod_file)
                            if spec and spec.loader:
                                mod = importlib.util.module_from_spec(spec)
                                sys.modules[f"plugin_{pid}"] = mod
                                spec.loader.exec_module(mod)
                                target = getattr(mod, cls_part, None)
                    else:
                        init_file = os.path.join(root, "__init__.py")
                        named_file = os.path.join(root, f"{pid}.py")
                        mod_file = init_file if os.path.isfile(init_file) else (named_file if os.path.isfile(named_file) else None)
                        if mod_file:
                            spec = importlib.util.spec_from_file_location(f"plugin_{pid}", mod_file)
                            if spec and spec.loader:
                                mod = importlib.util.module_from_spec(spec)
                                sys.modules[f"plugin_{pid}"] = mod
                                spec.loader.exec_module(mod)
                                if hasattr(mod, "register") and callable(getattr(mod, "register")):
                                    target = getattr(mod, "register")
                                else:
                                    for attr_name in dir(mod):
                                        attr = getattr(mod, attr_name)
                                        if isinstance(attr, type) and issubclass(attr, TradingPlugin) and attr is not TradingPlugin and attr is not FunctionalPluginAdapter:
                                            target = attr
                                            break

                    inst = None
                    if target:
                        if isinstance(target, type) and issubclass(target, TradingPlugin):
                            inst = target(config=raw.get("config", {}))
                        elif callable(target):
                            inst = FunctionalPluginAdapter(meta, target, config=raw.get("config", {}))

                    if inst:
                        inst.metadata = meta
                        self.register_plugin_instance(inst)
                        discovered.append(inst)
                        logger.info(f"[PluginEngine] Discovered directory plugin: {pid} v{version}")

                    # Auto-wire declared manifest hooks
                    raw_hooks = raw.get("hooks", {})
                    if mod and raw_hooks:
                        if isinstance(raw_hooks, dict):
                            for h_name, h_target in raw_hooks.items():
                                try:
                                    if ":" in h_target:
                                        m_name, f_name = h_target.split(":")
                                        fn = getattr(mod, f_name, None)
                                        if fn and callable(fn):
                                            self.register_hook(h_name, fn, plugin_id=pid)
                                except Exception as h_err:
                                    logger.warning(f"[PluginEngine] Error binding hook '{h_name}' for {pid}: {h_err}")
                        elif isinstance(raw_hooks, list):
                            for h_name in raw_hooks:
                                fn = getattr(mod, h_name, None) or getattr(mod, f"on_{h_name}", None) or getattr(mod, f"_{h_name}", None) or getattr(mod, f"_on_{h_name}", None)
                                if fn and callable(fn):
                                    self.register_hook(h_name, fn, plugin_id=pid)

                    # Auto-wire declared manifest tools
                    raw_tools = raw.get("tools", [])
                    if mod and isinstance(raw_tools, list):
                        for t_info in raw_tools:
                            if isinstance(t_info, dict) and "name" in t_info:
                                t_name = t_info["name"]
                                h_name = t_info.get("handler", t_name)
                                fn_name = h_name.split(":")[-1] if ":" in h_name else h_name
                                fn = getattr(mod, fn_name, None)
                                if fn and callable(fn):
                                    self.register_tool_from_plugin(
                                        plugin_id=pid,
                                        name=t_name,
                                        handler=fn,
                                        schema=t_info.get("parameters", {}),
                                        description=t_info.get("description", ""),
                                    )

                    # Legacy initialize(manager, config) invocation
                    if mod and hasattr(mod, "initialize") and callable(getattr(mod, "initialize")):
                        try:
                            mod.initialize(self.hook_manager, raw.get("config", {}))
                        except Exception as init_err:
                            logger.debug(f"[PluginEngine] Legacy initialize notice for {pid}: {init_err}")
                except Exception as ex:
                    logger.warning(f"[PluginEngine] Error loading plugin from {root}: {ex}")
        return discovered

    discover_directory = discover_directory_plugins

    def check_required_packages(self, plugin: TradingPlugin) -> bool:
        """
        Verify that third-party packages required by this plugin are installed.
        Returns False and marks DEGRADED if any package is missing.
        """
        missing = []
        for pkg in plugin.metadata.required_packages:
            try:
                if not importlib.util.find_spec(pkg):
                    missing.append(pkg)
            except Exception:
                missing.append(pkg)

        if missing:
            plugin.is_enabled = False
            plugin.status = "DEGRADED_MISSING_DEPENDENCIES"
            plugin.status_message = f"Missing required packages: {', '.join(missing)}. Fix: pip install {' '.join(missing)}"
            logger.warning(f"[PluginEngine] Plugin '{plugin.metadata.id}' marked DEGRADED: {plugin.status_message}")
            return False
        return True

    def apply_settings_overrides(self, settings: dict) -> None:
        """
        Apply configuration, toggles, and slot assignments from `settings.yaml:plugins`.
        """
        plugins_cfg = settings.get("plugins", {})
        if not plugins_cfg.get("enabled", True):
            for p in self.plugins.values():
                if not p.metadata.is_core:
                    p.is_enabled = False
            return

        # 1. Active Analysis Pipeline Slot
        active_pipeline = plugins_cfg.get("analysis_pipeline", {}).get("active")
        if active_pipeline:
            for p in self.plugins.values():
                if p.metadata.category == PluginCategory.ANALYSIS_PIPELINE:
                    p.is_enabled = (p.metadata.id == active_pipeline)
            # Inject options if provided
            ap_sec = plugins_cfg.get("analysis_pipeline", {})
            opts = ap_sec.get("available", {}).get(active_pipeline, {}) or ap_sec.get("options", {}).get(active_pipeline, {})
            if active_pipeline in self.plugins and isinstance(opts, dict):
                self.plugins[active_pipeline].config.update(opts)

        # 2. Active Broker Slot
        active_broker = plugins_cfg.get("broker", {}).get("active")
        if active_broker:
            for p in self.plugins.values():
                if p.metadata.category == PluginCategory.BROKER:
                    p.is_enabled = (p.metadata.id == active_broker)
            br_sec = plugins_cfg.get("broker", {})
            opts = br_sec.get("available", {}).get(active_broker, {}) or br_sec.get("options", {}).get(active_broker, {})
            if active_broker in self.plugins and isinstance(opts, dict):
                self.plugins[active_broker].config.update(opts)

        # 3. Schedulers overrides
        schedulers_cfg = plugins_cfg.get("schedulers", {})
        for sid, scfg in schedulers_cfg.items():
            if sid in self.plugins:
                p = self.plugins[sid]
                if isinstance(scfg, dict):
                    if "enabled" in scfg:
                        p.is_enabled = bool(scfg["enabled"])
                    p.config.update(scfg)
                elif isinstance(scfg, bool):
                    p.is_enabled = scfg

        # 4. General plugins overrides
        reg_cfg = plugins_cfg.get("registry", {})
        for pid, pcfg in reg_cfg.items():
            if pid in self.plugins:
                p = self.plugins[pid]
                if isinstance(pcfg, dict):
                    if "enabled" in pcfg:
                        p.is_enabled = bool(pcfg["enabled"])
                    p.config.update(pcfg)
                elif isinstance(pcfg, bool):
                    p.is_enabled = pcfg

    async def initialize(self, settings: dict) -> bool:
        """
        Full initialization sequence:
        1. Discover entrypoints & directories
        2. Merge config overrides
        3. Check dependencies & sort topologically
        4. Execute on_register & on_preflight
        """
        plugins_cfg = settings.get("plugins", {})
        auto_dirs = plugins_cfg.get("directories", ["trading-agent/plugins", "custom_plugins"])

        # 1. Discover
        for ep_plugin in self.discover_entrypoints():
            self.register_plugin_instance(ep_plugin)

        for d in auto_dirs:
            abs_d = d if os.path.isabs(d) else os.path.join(os.getcwd(), d)
            for dir_plugin in self.discover_directory_plugins(abs_d):
                self.register_plugin_instance(dir_plugin)

        # 2. Overrides
        self.apply_settings_overrides(settings)

        # 3. Filter enabled & check package dependencies
        active_list = []
        for p in self.plugins.values():
            if not p.is_enabled:
                logger.info(f"[PluginEngine] Plugin disabled by configuration: {p.metadata.id}")
                continue
            if not self.check_required_packages(p):
                continue
            active_list.append(p)

        # 4. Topological sort
        try:
            self.ordered_plugins = topological_sort_plugins(active_list)
        except PluginDependencyError as dep_err:
            logger.error(f"[PluginEngine] Dependency resolution error: {dep_err}")
            return False

        # 5. Execute on_register
        for plugin in self.ordered_plugins:
            try:
                plugin.state = PluginState.LOADING
                async with asyncio.timeout(LIFECYCLE_TIMEOUT_REGISTER):
                    await plugin.on_register(self.container, self.event_bus)
                self._wire_reactive_events(plugin)
                logger.debug(f"[PluginEngine] on_register complete for {plugin.metadata.id}")
            except TimeoutError:
                logger.error(f"[PluginEngine] Timeout ({LIFECYCLE_TIMEOUT_REGISTER}s) in on_register for {plugin.metadata.id}")
                plugin.status = "REGISTER_TIMEOUT"
                plugin.state = PluginState.FAILED
                if plugin.metadata.is_core:
                    return False
                plugin.is_enabled = False
            except Exception as e:
                logger.error(f"[PluginEngine] Error in on_register for {plugin.metadata.id}: {e}", exc_info=True)
                plugin.status = "REGISTER_FAILED"
                plugin.state = PluginState.FAILED
                if plugin.metadata.is_core:
                    return False
                plugin.is_enabled = False

        # 6. Execute on_preflight
        all_passed = True
        for plugin in self.ordered_plugins:
            if not plugin.is_enabled:
                continue
            try:
                async with asyncio.timeout(LIFECYCLE_TIMEOUT_PREFLIGHT):
                    passed, warnings = await plugin.on_preflight(self.container)
                for w in warnings:
                    logger.warning(f"[PluginEngine] Preflight warning from {plugin.metadata.id}: {w}")
                if not passed:
                    logger.error(f"[PluginEngine] Preflight FAILED for {plugin.metadata.id}")
                    plugin.status = "PREFLIGHT_FAILED"
                    plugin.state = PluginState.PREFLIGHT_FAILED
                    if plugin.metadata.is_core:
                        all_passed = False
                    else:
                        plugin.is_enabled = False
                else:
                    plugin.state = PluginState.PENDING
            except TimeoutError:
                logger.error(f"[PluginEngine] Timeout ({LIFECYCLE_TIMEOUT_PREFLIGHT}s) in on_preflight for {plugin.metadata.id}")
                plugin.status = "PREFLIGHT_TIMEOUT"
                plugin.state = PluginState.FAILED
                if plugin.metadata.is_core:
                    all_passed = False
                else:
                    plugin.is_enabled = False
            except Exception as e:
                logger.error(f"[PluginEngine] Preflight exception in {plugin.metadata.id}: {e}", exc_info=True)
                plugin.status = "PREFLIGHT_EXCEPTION"
                plugin.state = PluginState.FAILED
                if plugin.metadata.is_core:
                    all_passed = False
                else:
                    plugin.is_enabled = False

        return all_passed

    def _wire_reactive_events(self, plugin: TradingPlugin) -> None:
        """Subscribe plugin reactive methods to EventBus if overridden."""
        pid = plugin.metadata.id

        # on_tick
        if type(plugin).on_tick is not TradingPlugin.on_tick:
            async def _tick_handler(evt: TickPriceEvent):
                if plugin.is_enabled:
                    await plugin.on_tick(evt)
            self.event_bus.subscribe(TickPriceEvent, _tick_handler)
            self._disposers[pid].append(lambda: self.event_bus.unsubscribe(TickPriceEvent, _tick_handler))

        # on_bar
        if type(plugin).on_bar is not TradingPlugin.on_bar:
            async def _bar_handler(evt: BarClosedEvent):
                if plugin.is_enabled:
                    await plugin.on_bar(evt)
            self.event_bus.subscribe(BarClosedEvent, _bar_handler)
            self._disposers[pid].append(lambda: self.event_bus.unsubscribe(BarClosedEvent, _bar_handler))

        # on_order_state
        if type(plugin).on_order_state is not TradingPlugin.on_order_state:
            async def _order_handler(evt: OrderStateChangedEvent):
                if plugin.is_enabled:
                    await plugin.on_order_state(evt)
            self.event_bus.subscribe(OrderStateChangedEvent, _order_handler)
            self._disposers[pid].append(lambda: self.event_bus.unsubscribe(OrderStateChangedEvent, _order_handler))

        # on_risk_breach
        if type(plugin).on_risk_breach is not TradingPlugin.on_risk_breach:
            async def _breach_handler(evt: RiskBreachEvent):
                if plugin.is_enabled:
                    await plugin.on_risk_breach(evt)
            self.event_bus.subscribe(RiskBreachEvent, _breach_handler)
            self._disposers[pid].append(lambda: self.event_bus.unsubscribe(RiskBreachEvent, _breach_handler))

        # on_circuit_breaker
        if type(plugin).on_circuit_breaker is not TradingPlugin.on_circuit_breaker:
            async def _cb_handler(evt: CircuitBreakerEvent):
                if plugin.is_enabled:
                    await plugin.on_circuit_breaker(evt)
            self.event_bus.subscribe(CircuitBreakerEvent, _cb_handler)
            self._disposers[pid].append(lambda: self.event_bus.unsubscribe(CircuitBreakerEvent, _cb_handler))

    async def start(self) -> None:
        """Execute on_recovery then on_start for all enabled plugins in topological order."""
        if self._is_started:
            return

        # 1. Recovery stage
        for plugin in self.ordered_plugins:
            if not plugin.is_enabled:
                continue
            try:
                async with asyncio.timeout(LIFECYCLE_TIMEOUT_RECOVERY):
                    await plugin.on_recovery(self.container)
            except TimeoutError:
                logger.error(f"[PluginEngine] Timeout ({LIFECYCLE_TIMEOUT_RECOVERY}s) in on_recovery for {plugin.metadata.id}")
                plugin.status = "RECOVERY_TIMEOUT"
                plugin.state = PluginState.FAILED
            except Exception as e:
                logger.error(f"[PluginEngine] Error in on_recovery for {plugin.metadata.id}: {e}", exc_info=True)
                plugin.status = "RECOVERY_FAILED"
                plugin.state = PluginState.FAILED

        # 2. Start stage
        if self.task_registry is not None:
            tr = self.task_registry
        elif TaskRegistry is not None:
            tr = TaskRegistry(asyncio.Event())
        else:
            tr = None

        for plugin in self.ordered_plugins:
            if not plugin.is_enabled:
                continue
            try:
                async with asyncio.timeout(LIFECYCLE_TIMEOUT_START):
                    await plugin.on_start(self.container, tr)
                plugin.status = PluginState.RUNNING.value
                plugin.state = PluginState.RUNNING
                logger.info(f"[PluginEngine] Started plugin: {plugin.metadata.id} v{plugin.metadata.version}")
            except TimeoutError:
                logger.error(f"[PluginEngine] Timeout ({LIFECYCLE_TIMEOUT_START}s) in on_start for {plugin.metadata.id}")
                plugin.status = "START_TIMEOUT"
                plugin.state = PluginState.START_FAILED
            except Exception as e:
                logger.error(f"[PluginEngine] Error in on_start for {plugin.metadata.id}: {e}", exc_info=True)
                plugin.status = "START_FAILED"
                plugin.state = PluginState.START_FAILED

        self._is_started = True

    async def stop(self) -> None:
        """Stop all plugins in reverse topological order and execute all disposers."""
        self._is_started = False
        for plugin in reversed(self.ordered_plugins):
            pid = plugin.metadata.id
            try:
                async with asyncio.timeout(LIFECYCLE_TIMEOUT_STOP):
                    await plugin.on_stop()
                logger.debug(f"[PluginEngine] on_stop complete for {pid}")
            except TimeoutError:
                logger.error(f"[PluginEngine] Timeout ({LIFECYCLE_TIMEOUT_STOP}s) in on_stop for {pid}")
                plugin.status = "STOP_TIMEOUT"
                plugin.state = PluginState.STOPPED
            except Exception as e:
                logger.error(f"[PluginEngine] Error in on_stop for {pid}: {e}", exc_info=True)
                plugin.status = "STOP_FAILED"
                plugin.state = PluginState.STOPPED

            # Run registered engine disposers
            for disposer in self._disposers.get(pid, []):
                try:
                    res = disposer()
                    if inspect.isawaitable(res):
                        await res
                except Exception as d_err:
                    logger.debug(f"[PluginEngine] Disposer note for {pid}: {d_err}")

        # Tear down all active PluginContext instances
        for pid, ctx in list(self.contexts.items()):
            try:
                await ctx.teardown()
            except Exception as ctx_err:
                logger.debug(f"[PluginEngine] Context teardown note for {pid}: {ctx_err}")
        self.contexts.clear()

        self._disposers.clear()
        logger.info("[PluginEngine] All plugins stopped and resources disposed cleanly.")

    def on_config_reloaded(self, new_config: dict) -> None:
        """Synchronous callback for ConfigReloader, scheduling async propagation."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.propagate_config_reload(new_config))
        except RuntimeError:
            asyncio.run(self.propagate_config_reload(new_config))

    async def propagate_config_reload(self, new_config: dict) -> None:
        """Propagate configuration reload to active plugins."""
        self.apply_settings_overrides(new_config)
        plugins_cfg = new_config.get("plugins", {})
        target_plugins = self.ordered_plugins if self.ordered_plugins else list(self.plugins.values())
        for plugin in target_plugins:
            if not plugin.is_enabled:
                continue
            pid = plugin.metadata.id
            cat = getattr(plugin.metadata.category, "value", str(plugin.metadata.category))
            p_conf = (
                plugins_cfg.get(pid, {})
                or plugins_cfg.get(cat, {}).get("available", {}).get(pid, {})
                or plugins_cfg.get(cat, {}).get("options", {}).get(pid, {})
                or plugins_cfg.get("registry", {}).get(pid, {})
                or new_config
            )
            try:
                async with asyncio.timeout(LIFECYCLE_TIMEOUT_CONFIG_RELOAD):
                    if hasattr(plugin, "on_config_reloaded"):
                        res = plugin.on_config_reloaded(p_conf)
                        if inspect.isawaitable(res):
                            await res
                    if hasattr(plugin, "on_config_reload"):
                        res = plugin.on_config_reload(p_conf)
                        if inspect.isawaitable(res):
                            await res
                logger.info(f"[PluginEngine] Config reloaded for {pid}")
            except Exception as e:
                logger.error(f"[PluginEngine] Config reload error in {pid}: {e}", exc_info=True)

    def get_plugin(self, plugin_id: str) -> Optional[TradingPlugin]:
        """Retrieve plugin by ID."""
        return self.plugins.get(plugin_id)

    def get_plugins_by_category(self, category: PluginCategory) -> List[TradingPlugin]:
        """List active plugins for a specific category."""
        return [p for p in self.ordered_plugins if p.metadata.category == category and p.is_enabled]

