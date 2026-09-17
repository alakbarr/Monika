"""
Unit and regression tests for Dynamic Subagent Spawner Pool.
Verifies SubagentWorker sandboxing, timeout enforcement, distillation token contracts,
and dynamic query decomposition.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.subagent_spawner import (
    SubagentSpec,
    SubagentResult,
    SubagentWorker,
    DynamicSubagentPool,
)


@pytest.mark.asyncio
async def test_subagent_worker_success():
    """Verify SubagentWorker executes within sandbox and extracts tokens properly."""
    spec = SubagentSpec(
        worker_id="w_test_1",
        role="Macro Specialist",
        system_prompt="You are Macro Specialist",
        query="Analyze inflation outlook",
        tools=[{"name": "get_dxy", "description": "Get DXY"}],
        timeout_seconds=5.0,
        max_distilled_tokens=500,
    )

    mock_client = MagicMock()
    mock_client.run_chat_loop = AsyncMock(return_value={
        "reply": "US CPI is stabilizing at 2.4%.",
        "input_tokens": 120,
        "output_tokens": 45,
        "tool_calls_made": 1,
    })

    worker = SubagentWorker(spec=spec, client=mock_client)
    result = await worker.run()

    assert result.success is True
    assert result.worker_id == "w_test_1"
    assert result.role == "Macro Specialist"
    assert "US CPI is stabilizing" in result.content
    assert result.input_tokens == 120
    assert result.output_tokens == 45
    assert result.tool_calls_made == 1
    assert result.error is None


@pytest.mark.asyncio
async def test_subagent_worker_timeout_enforcement():
    """Verify SubagentWorker catches asyncio.TimeoutError and returns structured failure."""
    spec = SubagentSpec(
        worker_id="w_timeout",
        role="Slow Specialist",
        system_prompt="Slow prompt",
        query="Slow query",
        timeout_seconds=0.1,  # Fast timeout
    )

    mock_client = MagicMock()
    async def _hang(*args, **kwargs):
        await asyncio.sleep(1.0)
        return {"reply": "Done"}

    mock_client.run_chat_loop = AsyncMock(side_effect=_hang)

    worker = SubagentWorker(spec=spec, client=mock_client)
    result = await worker.run()

    assert result.success is False
    assert "Timeout" in result.content
    assert "Timeout" in (result.error or "")


@pytest.mark.asyncio
async def test_subagent_worker_distillation_contract():
    """Verify SubagentWorker truncates verbose output exceeding max_distilled_tokens."""
    spec = SubagentSpec(
        worker_id="w_verbose",
        role="Verbose Specialist",
        system_prompt="Prompt",
        query="Query",
        max_distilled_tokens=50,  # Strict low limit
        timeout_seconds=5.0,
    )

    long_reply = "Word " * 500  # 500 words is well over 50 tokens
    mock_client = MagicMock()
    mock_client.run_chat_loop = AsyncMock(return_value={
        "reply": long_reply,
        "input_tokens": 100,
        "output_tokens": 600,
        "tool_calls_made": 0,
    })

    worker = SubagentWorker(spec=spec, client=mock_client)
    result = await worker.run()

    assert result.success is True
    assert len(result.content) < len(long_reply)


@pytest.mark.asyncio
async def test_dynamic_subagent_pool_decompose_query():
    """Verify DynamicSubagentPool dynamically tailors specialist roster based on query keywords."""
    pool = DynamicSubagentPool(max_concurrency=4)

    dummy_tools = [
        {"name": "get_dxy"},
        {"name": "get_chart"},
        {"name": "get_cot_report"},
        {"name": "get_smc_zones"},
        {"name": "get_news_items"},
    ]

    # 1. Base query -> 3 base specialists
    specs_base = pool.decompose_research_query(
        query="Analisis fundamental dan teknikal EURUSD minggu ini",
        base_system_prompt="Base Sys",
        available_tools=dummy_tools,
    )
    assert len(specs_base) >= 3
    roles = [s.role for s in specs_base]
    assert any("Macro" in r for r in roles)
    assert any("Technical" in r for r in roles)
    assert any("Sentiment" in r for r in roles)

    # 2. Query with correlation -> spawns Cross-Asset Specialist
    specs_corr = pool.decompose_research_query(
        query="Bagaimana korelasi yield Treasury 10Y vs DXY mempengaruhi XAUUSD?",
        base_system_prompt="Base Sys",
        available_tools=dummy_tools,
    )
    assert len(specs_corr) == 4
    roles_corr = [s.role for s in specs_corr]
    assert any("Cross-Asset" in r for r in roles_corr)

    # 3. Query with order flow / sweep -> spawns Order Flow Specialist
    specs_of = pool.decompose_research_query(
        query="Cek order flow dan liquidity sweep di level 2400 BTCUSD",
        base_system_prompt="Base Sys",
        available_tools=dummy_tools,
    )
    assert len(specs_of) == 4
    roles_of = [s.role for s in specs_of]
    assert any("Order Flow" in r for r in roles_of)


@pytest.mark.asyncio
async def test_dynamic_subagent_pool_run_parallel():
    """Verify DynamicSubagentPool executes multiple workers concurrently with progress callback."""
    pool = DynamicSubagentPool(max_concurrency=3)

    specs = [
        SubagentSpec(
            worker_id=f"w_{i}",
            role=f"Specialist {i}",
            system_prompt="Prompt",
            query=f"Task {i}",
            timeout_seconds=5.0,
        )
        for i in range(3)
    ]

    mock_client = MagicMock()
    mock_client.run_chat_loop = AsyncMock(side_effect=lambda **kw: {
        "reply": f"Report for {kw.get('new_user_message')}",
        "input_tokens": 50,
        "output_tokens": 30,
        "tool_calls_made": 1,
    })

    progress_messages = []
    def _progress(msg):
        progress_messages.append(msg)

    results = await pool.run_parallel(specs, client=mock_client, progress_callback=_progress)

    assert len(results) == 3
    assert all(r.success for r in results)
    assert len(progress_messages) >= 6  # Start and complete events for 3 workers


@pytest.mark.asyncio
async def test_subagent_pool_depth_control_and_role_restriction():
    pool = DynamicSubagentPool(max_spawn_depth=2)

    # Spec exceeding max depth
    spec_deep = SubagentSpec(
        worker_id="deep_worker",
        role="Specialist",
        system_prompt="sys",
        query="query",
        spawn_depth=2,  # >= max_spawn_depth (2)
    )
    res_deep = await pool.spawn_worker(spec_deep)
    assert res_deep.success is False
    assert "Max spawn depth 2 exceeded" in res_deep.error

    # Leaf spec restricted from spawning
    spec_leaf = SubagentSpec(
        worker_id="leaf_worker",
        role="Leaf Specialist",
        system_prompt="sys",
        query="query",
        spawn_depth=1,
        can_spawn=False,
    )
    res_leaf = await pool.spawn_worker(spec_leaf)
    assert res_leaf.success is False
    assert "restricted from spawning" in res_leaf.error


@pytest.mark.asyncio
async def test_macro_specialist_receives_full_macro_toolset_and_checklist():
    """Verify Macro Specialist receives FedWatch, Treasury yields, Interest rates, EIA oil inventory, and checklist."""
    pool = DynamicSubagentPool()
    available_tools = [
        {"name": "get_fedwatch_probabilities"},
        {"name": "get_treasury_yields"},
        {"name": "get_interest_rates"},
        {"name": "get_eia_oil_inventory"},
        {"name": "get_dxy"},
        {"name": "get_vix"},
        {"name": "get_chart"},
    ]
    specs = pool.decompose_research_query(
        query="Analisis probabilitas kenaikan suku bunga Fed dan yield curve",
        base_system_prompt="Base Sys",
        available_tools=available_tools,
    )
    macro_spec = next(s for s in specs if "Macro" in s.role)
    macro_tool_names = [t["name"] for t in macro_spec.tools]
    assert "get_fedwatch_probabilities" in macro_tool_names
    assert "get_treasury_yields" in macro_tool_names
    assert "get_interest_rates" in macro_tool_names
    assert "get_eia_oil_inventory" in macro_tool_names
    assert "MANDATORY MACRO SEARCH CHECKLIST" in macro_spec.system_prompt
    assert "Rate Probabilities: Call `get_fedwatch_probabilities`" in macro_spec.system_prompt
    assert "Yield Curve & Spreads: Call `get_treasury_yields`" in macro_spec.system_prompt
    assert "Central Bank Baseline Rates: Call `get_interest_rates`" in macro_spec.system_prompt
    assert "Energy / Inventory: Call `get_eia_oil_inventory`" in macro_spec.system_prompt


@pytest.mark.asyncio
async def test_fedwatch_probabilities_web_search_fallback():
    """Verify handle_get_fedwatch_probabilities returns web_search fallback on missing session or empty data."""
    from analysis.tools.handlers.macro_tools import handle_get_fedwatch_probabilities

    # 1. Without session
    res_no_session = await handle_get_fedwatch_probabilities({})
    assert res_no_session.get("fallback_tool") == "web_search"
    assert "suggested_query" in res_no_session
    assert "CME FedWatch" in res_no_session.get("suggested_query", "")

    # 2. With session but empty database rows
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)

    res_empty = await handle_get_fedwatch_probabilities({}, session=mock_session)
    assert res_empty.get("count") == 0
    assert res_empty.get("meetings") == []
    assert res_empty.get("fallback_tool") == "web_search"
    assert "suggested_query" in res_empty
    assert "note" in res_empty


