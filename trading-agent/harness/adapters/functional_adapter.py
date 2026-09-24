# ==============================================================================
# File: harness/adapters/functional_adapter.py
# ==============================================================================

"""
Functional Script Plugin Adapter for Monika Trading Harness.
Enables plug-and-play execution of standalone script plugins (register(ctx)) inside Monika,
providing synthetic module shims and manifest translation.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from harness.contract import PluginCategory, PluginMetadata, PluginOrigin, TradingPlugin
from harness.context import PluginContext

logger = logging.getLogger("TradingAgent.Harness.FunctionalAdapter")


def install_compatibility_shims() -> None:
    """
    Install lightweight synthetic modules in sys.modules so standalone script plugins
    referencing legacy constants or tools.registry resolve transparently in Monika.
    """
    monika_root = Path(__file__).resolve().parent.parent.parent

    # 1. runtime constants shim
    if "script_constants" not in sys.modules:
        mod = types.ModuleType("script_constants")
        mod.DEFAULT_TIMEOUT = 5.0
        mod.CORE_TOOLS = {"execute_order", "risk_check"}
        mod.get_plugin_home = lambda: monika_root
        mod.get_process_home = lambda: monika_root
        mod.plugin_home_key = lambda p: str(p)
        sys.modules["script_constants"] = mod
        logger.debug("[FunctionalAdapter] Installed synthetic constants shim.")

    # 2. tools.registry bridge to Monika ToolRegistry
    if "tools" not in sys.modules:
        tools_pkg = types.ModuleType("tools")
        sys.modules["tools"] = tools_pkg

    if "tools.registry" not in sys.modules:
        reg_mod = types.ModuleType("tools.registry")

        class _RegistryProxy:
            def __init__(self):
                self._tools: Dict[str, Callable] = {}

            def register_tool(self, name: str, handler: Callable, **kwargs: Any) -> None:
                self._tools[name] = handler
                try:
                    from analysis.tools.registry import ToolRegistry
                    ToolRegistry.get_instance().register_handler(name, handler)
                except Exception as e:
                    logger.debug(f"[FunctionalAdapter] tools.registry.register note: {e}")

            def register(self, name: str, handler: Callable, **kwargs: Any) -> None:
                self.register_tool(name, handler, **kwargs)

            def has_tool(self, name: str) -> bool:
                return name in self._tools

            def get_tool(self, name: str) -> Optional[Callable]:
                return self._tools.get(name)

            def dispatch(self, tool_name: str, args: dict, **kwargs: Any) -> Any:
                if tool_name in self._tools:
                    return self._tools[tool_name](**args)
                try:
                    from analysis.tools.registry import ToolRegistry
                    return ToolRegistry.get_instance().get(tool_name)
                except Exception:
                    return None

        reg_mod.registry = _RegistryProxy()
        sys.modules["tools.registry"] = reg_mod
        setattr(sys.modules["tools"], "registry", reg_mod)
        logger.debug("[FunctionalAdapter] Installed synthetic 'tools.registry' bridge shim.")


# Install shims on module import and expose top-level references
install_compatibility_shims()
script_constants = sys.modules["script_constants"]
tools = sys.modules["tools"]


class FunctionalPluginBridge:
    """
    Loader and bridge for functional script plugins.
    Wraps directory plugins exposing register(ctx) into Monika TradingPlugins.
    """

    @classmethod
    def load_plugin(cls, plugin_dir: Path, engine: Any = None) -> Optional[TradingPlugin]:
        """Convenience loader alias."""
        return cls.load_from_directory(plugin_dir, engine)

    @staticmethod
    def load_from_directory(plugin_dir: Path, engine: Any = None) -> Optional[TradingPlugin]:
        """Load and instantiate a functional plugin directory into Monika."""
        install_compatibility_shims()

        manifest_file = plugin_dir / "plugin.yaml"
        raw: Dict[str, Any] = {}
        entrypoint_name = "plugin.py"

        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                    entrypoint_name = raw.get("entrypoint", "plugin.py")
            except Exception as e:
                logger.warning(f"[FunctionalAdapter] Failed parsing {manifest_file}: {e}")

        # Locate entrypoint script
        init_file = plugin_dir / entrypoint_name
        if not init_file.exists():
            init_file = plugin_dir / "__init__.py"
        if not init_file.exists():
            init_file = plugin_dir / "plugin.py"

        if not init_file.exists():
            logger.warning(f"[FunctionalAdapter] Missing entrypoint ({entrypoint_name} / __init__.py) in {plugin_dir}")
            return None

        pid = raw.get("name") or raw.get("id") or plugin_dir.name
        version = str(raw.get("version", "1.0.0"))
        desc = raw.get("description", "")
        author = raw.get("author")
        category_str = raw.get("category", "middleware")

        try:
            category = PluginCategory(category_str.lower())
        except ValueError:
            category = PluginCategory.MIDDLEWARE

        meta = PluginMetadata(
            id=pid,
            name=pid,
            version=version,
            category=category,
            description=desc,
            author=author,
            origin=PluginOrigin.LOCAL_DIRECTORY,
            dependencies=raw.get("dependencies", []),
            conflicts=raw.get("conflicts", []),
            required_packages=raw.get("required_packages", []),
        )

        mod_name = f"script_plugin_{pid.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(mod_name, str(init_file))
        if not spec or not spec.loader:
            logger.error(f"[FunctionalAdapter] Could not create spec for {init_file}")
            return None

        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception as e:
            logger.error(f"[FunctionalAdapter] Error executing {mod_name}: {e}", exc_info=True)
            return None

        register_fn = getattr(mod, "register", None)
        if not callable(register_fn):
            logger.warning(f"[FunctionalAdapter] Module {mod_name} does not expose a callable register(ctx) function.")
            return None

        from harness.engine import FunctionalPluginAdapter
        inst = FunctionalPluginAdapter(
            metadata=meta,
            register_fn=register_fn,
            config=raw.get("config", {}),
        )
        setattr(inst, "_module", mod)

        if engine is not None:
            ctx = PluginContext(plugin_id=pid, engine=engine, manifest=meta, config=inst.config)
            inst.on_context_ready(ctx)
            engine.register_plugin(inst)

        logger.info(f"[FunctionalAdapter] Successfully adapted functional plugin '{pid}' v{version}")
        return inst
