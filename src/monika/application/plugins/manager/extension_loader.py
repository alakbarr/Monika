# ==============================================================================
# File: utils/plugins/extension_loader.py
# ==============================================================================

"""
Plugin Extension Loader (M1).
Discovers and loads external extensions via `plugin.yaml` manifests.
"""

import importlib.util
import logging
import os
import sys
from typing import Any, Dict, List, Optional

import yaml

from monika.application.plugins.manager.manager import PluginManager, get_plugin_manager

logger = logging.getLogger("TradingAgent.PluginLoader")


def _import_from_path(module_name: str, file_path: str):
    """Dynamically import a module from a specific file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_single_plugin(plugin_dir: str, manager: Optional[PluginManager] = None) -> Optional[Dict[str, Any]]:
    """
    Load a plugin from its directory containing `plugin.yaml`.
    """
    manifest_path = os.path.join(plugin_dir, "plugin.yaml")
    if not os.path.isfile(manifest_path):
        return None

    mgr = manager or get_plugin_manager()
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f) or {}

        name = manifest.get("name", os.path.basename(plugin_dir))
        enabled = manifest.get("enabled", True)
        if not enabled:
            logger.info(f"[PluginLoader] Plugin '{name}' is disabled in manifest.")
            return None

        # Call entrypoint if specified
        entrypoint = manifest.get("entrypoint")
        if entrypoint:
            mod_name, func_name = entrypoint.split(":")
            mod_file = os.path.join(plugin_dir, *mod_name.split(".")) + ".py"
            if not os.path.isfile(mod_file):
                mod_file = os.path.join(plugin_dir, f"{mod_name}.py")
            if os.path.isfile(mod_file):
                module = _import_from_path(f"plugin_{name}_{mod_name.replace('.', '_')}", mod_file)
            else:
                module = importlib.import_module(mod_name)
            target = getattr(module, func_name)
            from monika.application.plugins.manager.manager import BasePlugin

            if isinstance(target, type) and issubclass(target, BasePlugin):
                plugin_instance = target(config=manifest.get("config", {}))
                plugin_instance.setup(mgr)
            elif callable(target):
                target(mgr, manifest.get("config", {}))

        # Register explicit hook mappings
        hooks = manifest.get("hooks", {})
        for hook_event, hook_target in hooks.items():
            mod_name, func_name = hook_target.split(":")
            mod_file = os.path.join(plugin_dir, *mod_name.split(".")) + ".py"
            if not os.path.isfile(mod_file):
                mod_file = os.path.join(plugin_dir, f"{mod_name}.py")
            if os.path.isfile(mod_file):
                module = _import_from_path(f"plugin_{name}_{mod_name.replace('.', '_')}", mod_file)
            else:
                module = importlib.import_module(mod_name)
            handler = getattr(module, func_name)
            mgr.register_hook(hook_event, handler)
            logger.info(f"[PluginLoader] Registered '{name}' handler '{hook_target}' for hook '{hook_event}'")

        # Register declarative custom tools
        tools = manifest.get("tools", [])
        for tool_def in tools:
            tool_name = tool_def.get("name")
            tool_cat = tool_def.get("category", "custom")
            tool_desc = tool_def.get("description")
            handler_ref = tool_def.get("entrypoint")
            model_ref = tool_def.get("model")

            if not tool_name or not handler_ref:
                continue

            h_mod_name, h_func_name = handler_ref.split(":")
            h_mod_file = os.path.join(plugin_dir, *h_mod_name.split(".")) + ".py"
            if not os.path.isfile(h_mod_file):
                h_mod_file = os.path.join(plugin_dir, f"{h_mod_name}.py")
            if os.path.isfile(h_mod_file):
                h_module = _import_from_path(f"plugin_{name}_{h_mod_name.replace('.', '_')}", h_mod_file)
            else:
                h_module = importlib.import_module(h_mod_name)
            handler_fn = getattr(h_module, h_func_name)

            if model_ref:
                m_mod_name, m_cls_name = model_ref.split(":")
                m_mod_file = os.path.join(plugin_dir, *m_mod_name.split(".")) + ".py"
                if not os.path.isfile(m_mod_file):
                    m_mod_file = os.path.join(plugin_dir, f"{m_mod_name}.py")
                if os.path.isfile(m_mod_file):
                    m_module = _import_from_path(f"plugin_{name}_{m_mod_name.replace('.', '_')}", m_mod_file)
                else:
                    m_module = importlib.import_module(m_mod_name)
                model_cls = getattr(m_module, m_cls_name)
            else:
                from pydantic import BaseModel

                model_cls = BaseModel

            mgr.register_tool(
                name=tool_name,
                category=tool_cat,
                input_model=model_cls,
                handler=handler_fn,
                description=tool_desc,
            )
            logger.info(f"[PluginLoader] Registered custom tool '{tool_name}' for plugin '{name}'")

        logger.info(f"[PluginLoader] Successfully loaded plugin '{name}' v{manifest.get('version', '1.0.0')}")
        return manifest
    except Exception as e:
        logger.error(f"[PluginLoader] Failed to load plugin from {plugin_dir}: {e}", exc_info=True)
        return None


def teardown_single_plugin(plugin_dir: str, manager: Optional[PluginManager] = None) -> bool:
    """Unload tools and handlers associated with a plugin."""
    manifest_path = os.path.join(plugin_dir, "plugin.yaml")
    if not os.path.isfile(manifest_path):
        return False
    mgr = manager or get_plugin_manager()
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f) or {}

        name = manifest.get("name", os.path.basename(plugin_dir))

        # 1. Unload registered tools
        for tool_def in manifest.get("tools", []):
            tool_name = tool_def.get("name")
            if tool_name:
                mgr.unregister_tool(tool_name)

        # 2. Unregister hooks
        hooks = manifest.get("hooks", {})
        if isinstance(hooks, dict):
            hook_items = list(hooks.items())
        elif isinstance(hooks, list):
            hook_items = [(h.get("event"), h.get("handler")) for h in hooks if isinstance(h, dict)]
        else:
            hook_items = []

        for hook_event, hook_target in hook_items:
            if not hook_event or not hook_target:
                continue
            try:
                mod_name, func_name = hook_target.split(":")
                mod_file = os.path.join(plugin_dir, *mod_name.split(".")) + ".py"
                if not os.path.isfile(mod_file):
                    mod_file = os.path.join(plugin_dir, f"{mod_name}.py")
                if os.path.isfile(mod_file):
                    module = _import_from_path(f"plugin_{name}_{mod_name.replace('.', '_')}", mod_file)
                else:
                    module = importlib.import_module(mod_name)
                handler = getattr(module, func_name, None)
                if handler:
                    mgr.unregister_hook(hook_event, handler)
            except Exception as hook_err:
                logger.warning(f"[PluginLoader] Error unregistering hook '{hook_event}' for '{name}': {hook_err}")

        # 3. Call teardown on BasePlugin entrypoint if implemented
        entrypoint = manifest.get("entrypoint")
        if entrypoint:
            try:
                mod_name, func_name = entrypoint.split(":")
                mod_file = os.path.join(plugin_dir, *mod_name.split(".")) + ".py"
                if not os.path.isfile(mod_file):
                    mod_file = os.path.join(plugin_dir, f"{mod_name}.py")
                if os.path.isfile(mod_file):
                    module = _import_from_path(f"plugin_{name}_{mod_name.replace('.', '_')}", mod_file)
                else:
                    module = importlib.import_module(mod_name)
                target = getattr(module, func_name, None)
                from monika.application.plugins.manager.manager import BasePlugin

                if isinstance(target, type) and issubclass(target, BasePlugin):
                    inst = target(config=manifest.get("config", {}))
                    inst.teardown(mgr)
            except Exception as entry_err:
                logger.warning(f"[PluginLoader] Error tearing down entrypoint for '{name}': {entry_err}")

        return True
    except Exception as e:
        logger.error(f"[PluginLoader] Error tearing down plugin {plugin_dir}: {e}")
        return False


def load_plugins(plugins_dir: Optional[str] = None, manager: Optional[PluginManager] = None) -> List[Dict[str, Any]]:
    """
    Discover and load all plugins within a base directory.
    """
    if plugins_dir is None:
        # Default search locations
        possible_dirs = [
            os.path.abspath("plugins"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "plugins")),
        ]
        for candidate in possible_dirs:
            if os.path.isdir(candidate):
                plugins_dir = candidate
                break

    if not plugins_dir or not os.path.isdir(plugins_dir):
        logger.debug(f"[PluginLoader] No plugins directory found at {plugins_dir}")
        return []

    mgr = manager or get_plugin_manager()
    loaded = []
    for item in os.listdir(plugins_dir):
        item_path = os.path.join(plugins_dir, item)
        if os.path.isdir(item_path):
            manifest = load_single_plugin(item_path, manager=mgr)
            if manifest:
                loaded.append(manifest)

    return loaded
