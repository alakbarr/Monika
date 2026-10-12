"""
Plugin System for Monika Trading Agent.
Provides manifest validation, dependency resolution, topological loading, and lifecycle hook dispatching.
"""

from monika.application.plugins.manifest import PluginManifest, SUPPORTED_HOOKS
from monika.application.plugins.loader import (
    PluginLoader,
    PluginDependencyError,
    CircularDependencyError,
    MissingDependencyError,
    topological_sort_plugins,
)

__all__ = [
    "PluginManifest",
    "SUPPORTED_HOOKS",
    "PluginLoader",
    "PluginDependencyError",
    "CircularDependencyError",
    "MissingDependencyError",
    "topological_sort_plugins",
]
