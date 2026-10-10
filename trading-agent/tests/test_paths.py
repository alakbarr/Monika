"""
Unit tests for canonical path resolution in utils.infra.paths.
Verifies CWD-invariance and regression prevention against ghost directory nesting.
"""

from pathlib import Path
from utils.infra.paths import (
    CONFIG_DIR,
    DATA_DIR,
    LOGS_DIR,
    REPO_ROOT,
    SUBAGENT_LOGS_DIR,
    TRADING_AGENT_DIR,
    get_data_dir,
    get_logs_dir,
    get_subagent_logs_dir,
    resolve_data_path,
)


def test_core_paths_are_absolute():
    assert TRADING_AGENT_DIR.is_absolute()
    assert REPO_ROOT.is_absolute()
    assert DATA_DIR.is_absolute()
    assert LOGS_DIR.is_absolute()
    assert CONFIG_DIR.is_absolute()
    assert SUBAGENT_LOGS_DIR.is_absolute()


def test_hierarchy_relationships():
    assert TRADING_AGENT_DIR.name == "trading-agent"
    assert DATA_DIR == TRADING_AGENT_DIR / "data"
    assert LOGS_DIR == TRADING_AGENT_DIR / "logs"
    assert CONFIG_DIR == TRADING_AGENT_DIR / "config"
    assert SUBAGENT_LOGS_DIR == LOGS_DIR / "subagents"
    assert REPO_ROOT == TRADING_AGENT_DIR.parent


def test_dir_getters_exist_and_return_path():
    data_dir = get_data_dir()
    assert isinstance(data_dir, Path)
    assert data_dir.exists()
    assert data_dir.is_dir()

    logs_dir = get_logs_dir()
    assert isinstance(logs_dir, Path)
    assert logs_dir.exists()
    assert logs_dir.is_dir()

    subagent_dir = get_subagent_logs_dir()
    assert isinstance(subagent_dir, Path)
    assert subagent_dir.exists()
    assert subagent_dir.is_dir()


def test_resolve_data_path_normalizes_redundant_prefixes():
    # Direct filename
    p1 = resolve_data_path("state.json")
    assert p1 == DATA_DIR / "state.json"

    # Redundant trading-agent/data forward slash
    p2 = resolve_data_path("trading-agent/data/sessions/test.json")
    assert p2 == DATA_DIR / "sessions" / "test.json"

    # Redundant trading-agent\data backslash
    p3 = resolve_data_path("trading-agent\\data\\sessions\\test.json")
    assert p3 == DATA_DIR / "sessions" / "test.json"
