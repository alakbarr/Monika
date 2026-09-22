# ==============================================================================
# File: plugins/loader.py
# ==============================================================================

"""
Plugin Dependency Resolver and Topological Loader.
Orders plugins by dependency graph before initialization, preventing missing dependency
failures and detecting circular dependency cycles at startup.
"""

import os
import yaml
import logging
from typing import Dict, List, Tuple, Optional, Any, Set
from collections import defaultdict, deque

from plugins.manifest import PluginManifest
from utils.plugins.manager import PluginManager, get_plugin_manager
from utils.plugins.extension_loader import load_single_plugin, teardown_single_plugin

logger = logging.getLogger("TradingAgent.Plugins.Loader")


class PluginDependencyError(Exception):
    """Base error for plugin dependency issues."""
    pass


class MissingDependencyError(PluginDependencyError):
    """Raised when a required plugin dependency is missing."""
    pass


class CircularDependencyError(PluginDependencyError):
    """Raised when circular dependencies exist between plugins."""
    pass


def load_manifest_file(manifest_path: str) -> PluginManifest:
    """Read and validate a plugin.yaml file into a PluginManifest instance."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f) or {}
    return PluginManifest(**raw_data)


def topological_sort_plugins(
    plugin_entries: List[Tuple[PluginManifest, str]]
) -> List[Tuple[PluginManifest, str]]:
    """
    Sort a list of (PluginManifest, plugin_dir) tuples topologically based on dependencies.
    Dependencies must load before the plugins that depend on them.
    Raises MissingDependencyError if a required dependency is missing.
    Raises CircularDependencyError if cycles are detected.
    """
    name_map: Dict[str, Tuple[PluginManifest, str]] = {
        m.name: (m, path) for m, path in plugin_entries
    }

    # Graph construction: edge from dep -> dependant (dep must be loaded before dependant)
    adj: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = {m.name: 0 for m, _ in plugin_entries}

    for manifest, _ in plugin_entries:
        for dep in manifest.dependencies:
            if dep not in name_map:
                raise MissingDependencyError(
                    f"Plugin '{manifest.name}' requires missing dependency '{dep}'"
                )
            adj[dep].append(manifest.name)
            in_degree[manifest.name] += 1

    # Kahn's algorithm
    queue = deque([name for name, deg in in_degree.items() if deg == 0])
    sorted_names: List[str] = []

    while queue:
        curr = queue.popleft()
        sorted_names.append(curr)

        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_names) != len(plugin_entries):
        cyclic_plugins = [name for name, deg in in_degree.items() if deg > 0]
        raise CircularDependencyError(
            f"Circular dependency detected involving plugins: {', '.join(cyclic_plugins)}"
        )

    return [name_map[name] for name in sorted_names]


class PluginLoader:
    """
    High-level orchestrator for discovering, verifying, and loading plugins.
    """

    def __init__(self, manager: Optional[PluginManager] = None):
        self.manager = manager or get_plugin_manager()
        self._loaded_manifests: Dict[str, PluginManifest] = {}

    def discover_plugins(self, plugins_dir: str) -> List[Tuple[PluginManifest, str]]:
        """Scan a directory for valid plugin subdirectories containing plugin.yaml, supporting nested categories."""
        if not os.path.isdir(plugins_dir):
            return []

        discovered = []
        for root, dirs, files in os.walk(plugins_dir):
            if "plugin.yaml" in files:
                manifest_file = os.path.join(root, "plugin.yaml")
                try:
                    manifest = load_manifest_file(manifest_file)
                    if manifest.enabled:
                        discovered.append((manifest, root))
                    else:
                        logger.info(f"Skipping disabled plugin: {manifest.name}")
                except Exception as e:
                    logger.warning(f"Invalid plugin manifest in {root}: {e}")
        return discovered

    def load_plugins_from_directory(self, plugins_dir: str) -> List[PluginManifest]:
        """
        Discover, topologically sort, and initialize all enabled plugins in a directory.
        """
        discovered = self.discover_plugins(plugins_dir)
        if not discovered:
            return []

        sorted_plugins = topological_sort_plugins(discovered)
        loaded = []

        for manifest, plugin_path in sorted_plugins:
            try:
                raw_manifest = load_single_plugin(plugin_path, manager=self.manager)
                if raw_manifest:
                    self._loaded_manifests[manifest.name] = manifest
                    loaded.append(manifest)
                    logger.info(f"Successfully loaded plugin: {manifest.name} v{manifest.version}")
            except Exception as e:
                logger.error(f"Failed to initialize plugin '{manifest.name}': {e}", exc_info=True)

        return loaded

    def unload_plugin(self, plugin_name: str, plugin_dir: str) -> bool:
        """Tear down a plugin and its registered tools."""
        success = teardown_single_plugin(plugin_dir, manager=self.manager)
        if success and plugin_name in self._loaded_manifests:
            del self._loaded_manifests[plugin_name]
        return success

    @property
    def loaded_plugins(self) -> Dict[str, PluginManifest]:
        return dict(self._loaded_manifests)
