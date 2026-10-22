import copy
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.analysis.calculators.quantlib_core import (
    clayton_copula_cdf as ql_clayton,
    gumbel_copula_cdf as ql_gumbel,
)
from monika.application.analysis.calculators.copula_tail_risk import (
    clayton_copula_cdf as direct_clayton,
    gumbel_copula_cdf as direct_gumbel,
)
from monika.application.analysis.memory.decision_log import DecisionLogger
from monika.application.analysis.memory.reflector import TradeReflector
from monika.application.analysis.subagent.isolated_harness import IsolatedSubagentRunner


def test_copula_delegation_consistency():
    """Verify quantlib_core delegates to institutional copula_tail_risk with identical results."""
    # Clayton test
    theta_clayton = 2.0
    u, v = 0.3, 0.7
    ql_res = ql_clayton(u, v, theta_clayton)
    direct_res = float(direct_clayton(u, v, theta_clayton))
    assert abs(ql_res - direct_res) < 1e-7

    # Clayton zero / negative theta fallback
    assert ql_clayton(0.4, 0.5, 0.0) == 0.2
    assert ql_clayton(0.4, 0.5, -1.0) == 0.2

    # Gumbel test
    theta_gumbel = 1.8
    ql_g_res = ql_gumbel(u, v, theta_gumbel)
    direct_g_res = float(direct_gumbel(u, v, theta_gumbel))
    assert abs(ql_g_res - direct_g_res) < 1e-7

    # Gumbel independence boundary
    assert ql_gumbel(0.4, 0.5, 1.0) == 0.2

    with pytest.raises(ValueError):
        ql_gumbel(u, v, 0.5)


@pytest.mark.asyncio
async def test_isolated_subagent_deepcopy():
    """Verify IsolatedSubagentRunner performs deep copy to prevent parent message mutation."""
    runner = IsolatedSubagentRunner()
    nested_list = ["original_point_1", "original_point_2"]
    original_messages = [{"role": "user", "content": [{"type": "text", "text": "hello"}], "nested": nested_list}]

    mock_client = MagicMock()
    mock_client.generate = AsyncMock(return_value="response")

    with patch(
        "monika.application.agent.harness.agent_harness.AgentHarness.run_agent_from_messages", new_callable=AsyncMock
    ) as mock_run:
        # Simulate agent runner mutating its input messages in-place
        async def side_effect(messages, **kwargs):
            messages[0]["nested"].append("mutated_inside_subagent")
            return {"success": True, "final_text": "done"}

        mock_run.side_effect = side_effect

        await runner.run_isolated(
            role_name="researcher",
            llm_client=mock_client,
            system_prompt="sys",
            messages=original_messages,
            tools=[],
        )

        # Parent's nested structure must remain completely untouched
        assert "mutated_inside_subagent" not in nested_list
        assert len(nested_list) == 2


@pytest.mark.asyncio
async def test_decision_log_fts_indexing_triggered():
    """Verify DecisionLog triggers index_reflection on new entries."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    with (
        patch("monika.infrastructure.database.safe_ops.safe_commit", new_callable=AsyncMock) as mock_commit,
        patch(
            "monika.application.analysis.memory.session_search.SessionSearchEngine.index_reflection",
            new_callable=AsyncMock,
        ) as mock_idx,
    ):
        log_id = await DecisionLogger.log_decision(
            session=mock_session,
            analysis_id=101,
            symbol="EURUSD",
            decision="BUY",
            confidence=0.85,
            confluence_score=7,
            rationale="Breakout setup",
        )
        assert mock_commit.await_count >= 1
        assert mock_idx.await_count == 1
