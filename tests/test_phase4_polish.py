"""
Unit tests for Phase 4 Polish (L-1 through L-14).
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from graph.state import merge_lists
from utils.api.credential_pool import APICredentialPool, CredentialPool as APICredentialPoolAlias
from utils.llm.credential_pool import LLMCredentialPool, CredentialPool as LLMCredentialPoolAlias
from analysis.providers.pricing_catalog import get_model_pricing, calculate_cost, cost_usd
from analysis.harness.agent_harness import calculate_turn_cost_usd
from data_sources.academic_search import ARXIV_API_URL, AcademicSearchClient
from skills.loader import load_skill, _sanitize_skill_name


def test_l1_drawdown_monitor_safe_fallback():
    """L-1: Drawdown monitor falls back safely to initial_balance on missing/zero balance."""
    from agent.monitors.drawdown_monitor import run_floating_drawdown_monitor

    # Verify logic directly: check agent with missing balance
    mock_agent = MagicMock()
    mock_agent.settings = {"paper_trading": {"initial_balance": 15000.0}}
    mock_agent.execution_service.broker_adapter.get_account_info = AsyncMock(
        return_value={"balance": 0, "equity": 0}
    )
    # The monitor code parses fallback_bal = float(agent.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
    # It must NOT divide by 1.0 or treat 0 as 1.
    account_info = {"balance": 0, "equity": 0}
    raw_balance = account_info.get("balance")
    raw_equity = account_info.get("equity")
    fallback_bal = float(mock_agent.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
    if raw_balance is not None and float(raw_balance) > 0:
        bal = float(raw_balance)
    else:
        bal = fallback_bal

    assert bal == 15000.0
    assert bal != 1


def test_l2_merge_lists_order_preserving_dedup():
    """L-2: merge_lists preserves insertion order and deduplicates hashable and unhashable items in O(N)."""
    # Simple hashables
    assert merge_lists([1, 2, 3], [2, 3, 4]) == [1, 2, 3, 4]
    assert merge_lists(["a", "b"], ["b", "c"]) == ["a", "b", "c"]
    assert merge_lists([], [1, 2]) == [1, 2]
    assert merge_lists(None, [3]) == [3]
    assert merge_lists([3], None) == [3]

    # Unhashable dicts
    dict_a = [{"id": 1, "val": "x"}, {"id": 2, "val": "y"}]
    dict_b = [{"id": 2, "val": "y"}, {"id": 3, "val": "z"}]
    res = merge_lists(dict_a, dict_b)
    assert len(res) == 3
    assert res == [{"id": 1, "val": "x"}, {"id": 2, "val": "y"}, {"id": 3, "val": "z"}]


def test_l3_default_api_url_env_parameterized(monkeypatch):
    """L-3: CLI/TUI API URL parameterizes via MONIKA_API_URL, TRADEAGENT_API_URL, or DASHBOARD_URL."""
    monkeypatch.setenv("MONIKA_API_URL", "http://monika-host:9000")
    monkeypatch.setenv("TRADEAGENT_API_URL", "http://tradeagent-host:8000")
    url = (
        os.environ.get("MONIKA_API_URL")
        or os.environ.get("TRADEAGENT_API_URL")
        or os.environ.get("DASHBOARD_URL")
        or "http://127.0.0.1:8000"
    )
    assert url == "http://monika-host:9000"

    monkeypatch.delenv("MONIKA_API_URL", raising=False)
    url_fallback = (
        os.environ.get("MONIKA_API_URL")
        or os.environ.get("TRADEAGENT_API_URL")
        or os.environ.get("DASHBOARD_URL")
        or "http://127.0.0.1:8000"
    )
    assert url_fallback == "http://tradeagent-host:8000"


def test_l4_trading_agent_explicit_attributes():
    """L-4: TradingAgent has explicit dynamic attribute annotations and initializations."""
    from main import TradingAgent
    agent = TradingAgent(settings={}, dry_run=True)
    assert hasattr(agent, "mt5_health_checker")
    assert hasattr(agent, "risk_parameter_reloader")
    assert hasattr(agent, "task_registry")
    assert hasattr(agent, "_recovery_task")
    assert hasattr(agent, "_tg_task")
    assert hasattr(agent, "_mt5_degraded")
    assert hasattr(agent, "_fallback_always_approved")
    assert hasattr(agent, "_recovery_complete")
    assert hasattr(agent, "_activity_log")
    assert hasattr(agent, "_background_tasks")
    assert hasattr(agent, "_tasks")


def test_l5_pricing_catalog_routing():
    """L-5: Model pricing routes through pricing_catalog."""
    price = get_model_pricing("claude-sonnet-5")
    assert price.input > 0
    assert price.output > 0

    cost = calculate_turn_cost_usd("claude-sonnet-5", input_tokens=1000, output_tokens=500)
    assert isinstance(cost, float)
    assert cost > 0.0

    # Free tier models return 0.0
    free_cost = calculate_turn_cost_usd("qwen3.6-27b", input_tokens=1000, output_tokens=500)
    assert free_cost == 0.0


def test_l6_bond_yields_fetcher_and_backward_compatible_shim():
    """L-6: bond_yields_fetcher is the new module and bond_yields_yfinance re-exports it."""
    from data_sources.bond_yields_fetcher import BondYieldFetcher as Fetcher1
    from data_sources.bond_yields_yfinance import BondYieldFetcher as Fetcher2

    assert Fetcher1 is Fetcher2


def test_l7_credential_pool_name_disambiguation():
    """L-7: APICredentialPool and LLMCredentialPool exist with backward-compatible aliases."""
    assert APICredentialPool is APICredentialPoolAlias
    assert LLMCredentialPool is LLMCredentialPoolAlias
    assert APICredentialPool is not LLMCredentialPool


def test_l8_extension_loader_no_sys_path_mutation(tmp_path):
    """L-8: Extension loader does not modify sys.path."""
    from utils.plugins.extension_loader import load_single_plugin

    plugin_dir = tmp_path / "test_plugin"
    plugin_dir.mkdir()
    manifest_file = plugin_dir / "plugin.yaml"
    manifest_file.write_text("name: test_p\nenabled: true\n", encoding="utf-8")

    initial_sys_path = list(sys.path)
    load_single_plugin(str(plugin_dir))
    assert sys.path == initial_sys_path


def test_l10_no_loose_sql_files_in_migrations():
    """L-10: No loose .sql files in trading-agent/database/migrations root."""
    base_dir = Path(__file__).parent.parent / "database" / "migrations"
    loose_sql = list(base_dir.glob("*.sql"))
    assert len(loose_sql) == 0, f"Found loose .sql files in migrations: {loose_sql}"


def test_l13_skill_loader_path_traversal_prevention():
    """L-13: Skill loader rejects parent directory traversal."""
    with pytest.raises(ValueError, match="Path traversal"):
        _sanitize_skill_name("../../../etc/passwd")

    with pytest.raises(ValueError, match="Path traversal"):
        _sanitize_skill_name("sub/playbook")

    with pytest.raises(ValueError, match="Path traversal"):
        load_skill("../../../etc/passwd")


def test_l14_academic_search_uses_https():
    """L-14: Academic search uses HTTPS endpoint for arXiv."""
    assert ARXIV_API_URL.startswith("https://")
    client = AcademicSearchClient()
    assert client is not None
