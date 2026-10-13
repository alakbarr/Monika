"""
Plugin System for Monika Trading Agent.
Provides manifest validation, dependency resolution, topological loading, and lifecycle hook dispatching.
"""

from monika.application.plugins.loader import (
    CircularDependencyError,
    MissingDependencyError,
    PluginDependencyError,
    PluginLoader,
    topological_sort_plugins,
)
from monika.application.plugins.manifest import SUPPORTED_HOOKS, PluginManifest

__all__ = [
    "PluginManifest",
    "SUPPORTED_HOOKS",
    "PluginLoader",
    "PluginDependencyError",
    "CircularDependencyError",
    "MissingDependencyError",
    "topological_sort_plugins",
]
