# ==============================================================================
# File: tests/graph/test_debate_timeout_repro.py
# Reproduction and verification tests for debate timeout and fail-closed invariants
# ==============================================================================

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.analysis.debate.investment_judge import evaluate_debate
from monika.application.graph.nodes.debate.bear_dissent_node import bear_dissent_node
from monika.application.graph.nodes.debate.debate_judge_node import debate_judge_node
from monika.application.graph.nodes.debate.helpers import resolve_debate_timeout


def test_resolve_debate_timeout_defaults_and_overrides():
    """Verify resolve_debate_timeout respects settings hierarchies and reasoning floors."""
    # 1. Default when settings empty
    assert resolve_debate_timeout({}) == 360.0

    # 2. Configured in agent_architecture
    settings_aa = {"agent_architecture": {"debate_turn_timeout_seconds": 120.0}}
    assert resolve_debate_timeout(settings_aa) == 120.0

    # 3. Configured in llm per_turn_timeout_seconds
    settings_llm = {"llm": {"per_turn_timeout_seconds": 240.0}}
    assert resolve_debate_timeout(settings_llm) == 240.0

    # 4. Client with high thinking level enforces 600.0s floor
    mock_high_thinking_client = MagicMock()
    mock_high_thinking_client.model = "gemini-3.5-flash-lite"
    mock_high_thinking_client.thinking_level = "high"
    mock_high_thinking_client.thinking_budget = None
    mock_high_thinking_client.capabilities = None

    assert resolve_debate_timeout({}, client=mock_high_thinking_client) == 600.0

    # 5. Client with reasoning model name enforces 360.0s floor
    mock_reasoning_client = MagicMock()
    mock_reasoning_client.model = "deepseek-r1"
    mock_reasoning_client.thinking_level = None
    mock_reasoning_client.thinking_budget = None
    mock_reasoning_client.capabilities = None

    assert (
        resolve_debate_timeout(
            {"agent_architecture": {"debate_turn_timeout_seconds": 60.0}},
            client=mock_reasoning_client,
        )
        == 360.0
    )


@pytest.mark.asyncio
async def test_bear_dissent_node_uses_resolved_timeout():
    """Verify bear_dissent_node applies dynamically resolved timeout instead of hardcoded 45s."""
    state = {
        "actionable_trades": [("EURUSD", {"analysis_id": 101, "decision": "buy"})],
        "debate_states": {
            "EURUSD": {
                "verified_bull_claim": {"strength_score": 9, "thesis": "bull breakout"},
                "original_context": {"decision": "buy", "entry_price": 1.0850},
                "fact_sheet": {"symbol": "EURUSD"},
            }
        },
    }
    # Configure custom timeout of 150.0s with a non-reasoning client
    config = {
        "configurable": {
            "scheduler": MagicMock(
                settings={"agent_architecture": {"enable_debate": True, "debate_turn_timeout_seconds": 150.0}}
            )
        }
    }

    mock_client = MagicMock()
    mock_client.model = "gpt-4o-mini"
    mock_client.thinking_level = None
    mock_client.thinking_budget = None
    mock_client.capabilities = None

    captured_timeouts = []
    original_timeout = asyncio.timeout

    def mock_timeout(delay):
        captured_timeouts.append(delay)
        return original_timeout(delay)

    with (
        patch(
            "monika.application.graph.nodes.debate.bear_dissent_node.get_client_for_task",
            return_value=mock_client,
        ),
        patch("asyncio.timeout", side_effect=mock_timeout),
        patch(
            "monika.application.graph.nodes.debate.bear_dissent_node.generate_bear_dissent",
            new_callable=AsyncMock,
            return_value={"counter_thesis": "test dissent", "risk_severity": 6},
        ),
    ):
        res = await bear_dissent_node(state, config)

    assert "EURUSD" in res["debate_states"]
    assert len(captured_timeouts) >= 1
    # The timeout applied must match the resolved 150.0s, NOT 45.0s!
    assert 150.0 in captured_timeouts


@pytest.mark.asyncio
async def test_debate_judge_node_fails_closed_when_bear_dissent_missing():
    """
    Verification of ripple effect:
    When bear_dissent is missing (e.g. because bear_dissent_node failed or timed out),
    debate_judge_node must fail closed (final_decision='avoid', risk_multiplier=0.0)
    and must NEVER approve or evaluate the trade without adversarial bear review.
    """
    state = {
        "actionable_trades": [("EURUSD", {"analysis_id": 101, "decision": "buy"})],
        "debate_states": {
            "EURUSD": {
                "verified_bull_claim": {"strength_score": 9, "thesis": "bull breakout"},
                "original_context": {"decision": "buy", "entry_price": 1.0850},
                # bear_dissent is intentionally MISSING (None)
                "bear_dissent": None,
                "fact_sheet": {"symbol": "EURUSD"},
            }
        },
    }
    config = {"configurable": {"scheduler": MagicMock(settings={"agent_architecture": {"enable_debate": True}})}}

    mock_evaluate = AsyncMock()
    with patch("monika.application.graph.nodes.debate.debate_judge_node.evaluate_debate", mock_evaluate):
        res = await debate_judge_node(state, config)

    # evaluate_debate must NOT be called without bear dissent!
    mock_evaluate.assert_not_called()

    # Trade must NOT survive (failed closed)
    assert res.get("actionable_trades") == []
    verdict = res.get("investment_verdicts", {}).get("EURUSD", {})
    assert verdict.get("final_decision") == "avoid"
    assert verdict.get("risk_multiplier") == 0.0
    assert "missing_bear_dissent" in verdict.get("reason", "")


@pytest.mark.asyncio
async def test_investment_judge_safeguard_against_none_bear_dissent():
    """
    Verification that investment_judge.evaluate_debate does not crash with AttributeError
    when bear_dissent is None or empty, and enforces fail-closed capital protection.
    """
    mock_client = MagicMock()
    original_context = {"decision": "buy", "entry_price": 1.0850}
    bull_claim = {"strength_score": 8, "thesis": "valid bull setup"}

    # Passing bear_dissent=None should not crash with AttributeError: 'NoneType' object has no attribute 'get'
    res = await evaluate_debate(
        client=mock_client,
        symbol="EURUSD",
        original_context=original_context,
        bull_claim=bull_claim,
        bear_dissent=None,  # type: ignore
    )
    assert res.get("final_decision") == "avoid"
    assert res.get("risk_multiplier") == 0.0
