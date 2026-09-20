import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.harness.agent_harness import AgentHarness
from analysis.harness.harness_state import HarnessState, SteeringMessage


@pytest.mark.asyncio
async def test_harness_state_dual_queues():
    state = HarnessState()
    assert len(state.steering_queue) == 0
    assert len(state.follow_up_queue) == 0
    assert state.length_truncated is False

    # Enqueue immediate steering
    state.enqueue_steering(SteeringMessage(content="Adjust risk to defensive", sender="operator", mode="immediate"))
    # Enqueue follow-up task
    state.enqueue_steering(SteeringMessage(content="Scan correlation after close", sender="scheduler", mode="follow_up"))

    assert len(state.steering_queue) == 1
    assert len(state.follow_up_queue) == 1

    drained_steering = state.drain_steering()
    assert len(drained_steering) == 1
    assert drained_steering[0].content == "Adjust risk to defensive"
    assert len(state.steering_queue) == 0

    drained_follow_up = state.drain_follow_up()
    assert len(drained_follow_up) == 1
    assert drained_follow_up[0].content == "Scan correlation after close"
    assert len(state.follow_up_queue) == 0


@pytest.mark.asyncio
async def test_agent_harness_immediate_steering_injection():
    mock_client = MagicMock()
    mock_client.provider_name = "test_provider"
    mock_client.model = "test-model"
    mock_client.role = "test_role"

    # Turn 1: LLM returns text response
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            finish_reason="stop",
            message=MagicMock(
                content="Initial market view",
                tool_calls=[],
                reasoning_content=None,
            ),
        )
    ]
    mock_client.run_tool_agent = AsyncMock(return_value=mock_response)

    harness = AgentHarness(llm_client=mock_client, settings={})
    harness.enqueue_steering("Emergency volatility spike on EURUSD", sender="news_watcher", mode="immediate")

    result = await harness.run_agent_from_messages(
        session=None,
        system_prompt="You are a trading agent.",
        messages=[{"role": "user", "content": "Analyze EURUSD"}],
        tools=[],
        stage_name="test_stage",
        max_tool_turns=3,
    )

    assert result["success"] is True
    # Verify steering directive was injected into context
    context = result["context_messages"]
    steering_found = any(
        "NEWS_WATCHER STEERING DIRECTIVE" in str(msg.get("content", ""))
        for msg in context
    )
    assert steering_found, "Immediate steering directive should be injected into messages"


@pytest.mark.asyncio
async def test_agent_harness_follow_up_queue():
    mock_client = MagicMock()
    mock_client.provider_name = "test_provider"
    mock_client.model = "test-model"
    mock_client.role = "test_role"

    # Turn 1: Complete primary task; Turn 2: Complete follow-up task
    resp1 = MagicMock(
        choices=[
            MagicMock(
                finish_reason="stop",
                message=MagicMock(
                    content="Primary task finished.",
                    tool_calls=[],
                    reasoning_content=None,
                ),
            )
        ]
    )
    resp2 = MagicMock(
        choices=[
            MagicMock(
                finish_reason="stop",
                message=MagicMock(
                    content="Follow-up task completed.",
                    tool_calls=[],
                    reasoning_content=None,
                ),
            )
        ]
    )
    mock_client.run_tool_agent = AsyncMock(side_effect=[resp1, resp2])

    harness = AgentHarness(llm_client=mock_client, settings={})
    harness.enqueue_steering("Verify position exposure", sender="risk_guardian", mode="follow_up")

    result = await harness.run_agent_from_messages(
        session=None,
        system_prompt="You are a trading agent.",
        messages=[{"role": "user", "content": "Analyze portfolio"}],
        tools=[],
        stage_name="test_stage",
        max_tool_turns=5,
    )

    assert result["success"] is True
    assert result["turns"] == 2
    context = result["context_messages"]
    follow_up_found = any(
        "RISK_GUARDIAN FOLLOW-UP TASK" in str(msg.get("content", ""))
        for msg in context
    )
    assert follow_up_found, "Follow-up directive should be executed before loop goes idle"


@pytest.mark.asyncio
async def test_agent_harness_truncation_safety_guard():
    mock_client = MagicMock()
    mock_client.provider_name = "test_provider"
    mock_client.model = "test-model"
    mock_client.role = "test_role"

    # Turn 1: Truncated response with a tool call
    truncated_tool_call = MagicMock(
        id="call_order_123",
        function=MagicMock(name="submit_order", arguments='{"symbol": "EURUSD", "lot": 1.0, "sl":'),
    )
    resp_truncated = MagicMock(
        choices=[
            MagicMock(
                finish_reason="length",
                message=MagicMock(
                    content="Opening order with parameters...",
                    tool_calls=[truncated_tool_call],
                    reasoning_content=None,
                ),
            )
        ]
    )

    # Turn 2: Recovered clean response
    resp_recovered = MagicMock(
        choices=[
            MagicMock(
                finish_reason="stop",
                message=MagicMock(
                    content="Re-evaluating without corrupted parameters. Standing by.",
                    tool_calls=[],
                    reasoning_content=None,
                ),
            )
        ]
    )
    mock_client.run_tool_agent = AsyncMock(side_effect=[resp_truncated, resp_recovered])

    harness = AgentHarness(llm_client=mock_client, settings={})
    result = await harness.run_agent_from_messages(
        session=None,
        system_prompt="You are a trading agent.",
        messages=[{"role": "user", "content": "Trade EURUSD"}],
        tools=[],
        stage_name="test_stage",
        max_tool_turns=4,
    )

    assert result["success"] is True
    assert result["length_truncated"] is True
    # Verify tool call was refused with safe truncation notice
    context = result["context_messages"]
    refusal_found = any(
        "refused_truncated_response" in str(msg.get("content", ""))
        for msg in context
    )
    assert refusal_found, "Truncated tool calls must be refused safely"
