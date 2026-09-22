"""
Tests for PR-19: Plugin Manifest System & Topological Loader.
Verifies manifest schema validation, dependency resolution, topological sorting, and error handling.
"""

import os
import yaml
import pytest
from pydantic import ValidationError

from plugins.manifest import PluginManifest, SUPPORTED_HOOKS
from plugins.loader import (
    PluginLoader,
    PluginDependencyError,
    CircularDependencyError,
    MissingDependencyError,
    topological_sort_plugins,
    load_manifest_file,
)
from utils.plugins.manager import PluginManager


def test_plugin_manifest_valid():
    manifest = PluginManifest(
        name="test_plugin",
        version="1.2.0",
        description="A test plugin",
        dependencies=["base_plugin"],
        hooks={"pre_order": "handlers.order:pre_check"},
    )
    assert manifest.name == "test_plugin"
    assert manifest.version == "1.2.0"
    assert manifest.dependencies == ["base_plugin"]
    assert "pre_order" in manifest.hooks


def test_plugin_manifest_invalid_hook_raises():
    with pytest.raises(ValidationError):
        PluginManifest(
            name="bad_plugin",
            hooks={"invalid_fake_hook": "handlers:run"},
        )


def test_plugin_manifest_invalid_hook_target_format():
    with pytest.raises(ValidationError):
        PluginManifest(
            name="bad_plugin",
            hooks={"pre_tool_call": "no_colon_target"},
        )


def test_topological_sort_simple_dependency():
    p_base = PluginManifest(name="base_plugin")
    p_child = PluginManifest(name="child_plugin", dependencies=["base_plugin"])

    entries = [(p_child, "/path/child"), (p_base, "/path/base")]
    sorted_entries = topological_sort_plugins(entries)

    order = [m.name for m, _ in sorted_entries]
    assert order == ["base_plugin", "child_plugin"]


def test_topological_sort_multi_level_dag():
    p1 = PluginManifest(name="p1")
    p2 = PluginManifest(name="p2", dependencies=["p1"])
    p3 = PluginManifest(name="p3", dependencies=["p2"])
    p4 = PluginManifest(name="p4", dependencies=["p1"])

    entries = [(p3, "/p3"), (p4, "/p4"), (p2, "/p2"), (p1, "/p1")]
    sorted_entries = topological_sort_plugins(entries)

    order = [m.name for m, _ in sorted_entries]
    assert order.index("p1") < order.index("p2")
    assert order.index("p2") < order.index("p3")
    assert order.index("p1") < order.index("p4")


def test_topological_sort_missing_dependency_raises():
    p1 = PluginManifest(name="orphan_plugin", dependencies=["missing_lib"])
    entries = [(p1, "/path")]

    with pytest.raises(MissingDependencyError) as exc:
        topological_sort_plugins(entries)
    assert "missing dependency 'missing_lib'" in str(exc.value)


def test_topological_sort_circular_dependency_raises():
    p_a = PluginManifest(name="plugin_a", dependencies=["plugin_b"])
    p_b = PluginManifest(name="plugin_b", dependencies=["plugin_a"])
    entries = [(p_a, "/a"), (p_b, "/b")]

    with pytest.raises(CircularDependencyError) as exc:
        topological_sort_plugins(entries)
    assert "Circular dependency detected" in str(exc.value)


def test_plugin_loader_discover_and_load_from_directory(tmp_path):
    # Setup dummy plugins in tmp_path
    plugin1_dir = tmp_path / "plugin_alpha"
    plugin1_dir.mkdir()
    alpha_yaml = {
        "name": "plugin_alpha",
        "version": "1.0.0",
        "enabled": True,
    }
    with open(plugin1_dir / "plugin.yaml", "w", encoding="utf-8") as f:
        yaml.dump(alpha_yaml, f)

    plugin2_dir = tmp_path / "plugin_beta"
    plugin2_dir.mkdir()
    beta_yaml = {
        "name": "plugin_beta",
        "version": "1.0.0",
        "dependencies": ["plugin_alpha"],
        "enabled": True,
    }
    with open(plugin2_dir / "plugin.yaml", "w", encoding="utf-8") as f:
        yaml.dump(beta_yaml, f)

    mgr = PluginManager()
    loader = PluginLoader(manager=mgr)

    discovered = loader.discover_plugins(str(tmp_path))
    assert len(discovered) == 2

    loaded = loader.load_plugins_from_directory(str(tmp_path))
    assert len(loaded) == 2
    assert loaded[0].name == "plugin_alpha"
    assert loaded[1].name == "plugin_beta"
