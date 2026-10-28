# ==============================================================================
# File: tests/llm/test_risk_cache_invariance.py
# Description: Unit tests verifying prompt cache invariance for risk personas,
#              portfolio synthesis, adversarial check, and trade reflection.
# ==============================================================================

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from tests.conftest import create_mock_async_session


@pytest.mark.asyncio
async def test_portfolio_synthesis_prompt_free_of_volatile_ids_and_padded():
    """Verify portfolio synthesis removes volatile analysis_id and uses padded system prompt."""
    from monika.application.graph.nodes.risk.portfolio_synthesis import (
        PORTFOLIO_SYNTHESIS_SYSTEM_PROMPT,
        ai_portfolio_synthesis,
    )

    assert PORTFOLIO_SYNTHESIS_SYSTEM_PROMPT is not None
    assert len(PORTFOLIO_SYNTHESIS_SYSTEM_PROMPT) >= 4000

    mock_session = create_mock_async_session()
    mock_session.execute = AsyncMock()
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_scalar

    actionable = [
        ("EURUSD", {"decision": "buy", "confidence": 0.85, "analysis_id": 99991}),
        ("GBPUSD", {"decision": "buy", "confidence": 0.75, "analysis_id": 88882}),
    ]

    mock_client = MagicMock()
    mock_client.model = "minimax-m3.1-flash"
    mock_client.provider_name = "openrouter"
    mock_client.classify_json = AsyncMock(
        return_value={
            "recommendation": "execute_all",
            "keep": ["EURUSD", "GBPUSD"],
            "reasoning": "diversified",
        }
    )

    with patch(
        "monika.infrastructure.providers.llm_factory.get_client_for_task",
        return_value=mock_client,
    ):
        result = await ai_portfolio_synthesis(
            actionable=actionable,
            session=mock_session,
            settings={},
            market_regime="trending",
        )

    assert result["recommendation"] == "execute_all"
    assert mock_client.classify_json.called
    call_kwargs = mock_client.classify_json.call_args.kwargs

    prompt = call_kwargs["prompt"]
    # Volatile database analysis_id must NOT appear in the user prompt
    assert "analysis_id" not in prompt
    assert "99991" not in prompt
    assert "88882" not in prompt

    # System prompt must be passed, padded, and task_role set
    sys_prompt = call_kwargs.get("system_prompt", "")
    assert len(sys_prompt) >= 4000
    assert call_kwargs.get("task_role") == "portfolio_synthesis"


@pytest.mark.asyncio
async def test_adversarial_check_padded_system_prompt_and_task_role():
    """Verify adversarial check uses padded system prompt, static-first user prompt, and task_role."""
    from monika.application.analysis.validators.adversarial_check import (
        ADVERSARIAL_SYSTEM_PROMPT,
        run_adversarial_check,
    )

    assert ADVERSARIAL_SYSTEM_PROMPT is not None
    assert len(ADVERSARIAL_SYSTEM_PROMPT) >= 4000

    mock_session = create_mock_async_session()
    analysis = MagicMock()
    analysis.id = 101
    analysis.symbol = "XAUUSD"
    analysis.decision = "buy"
    analysis.stop_loss = 2300.0
    analysis.take_profit = 2400.0
    analysis.price_at_analysis = 2320.0
    analysis.entry_price = 2320.0
    analysis.confluence_score = 8
    analysis.priced_in_score = 3
    analysis.invalidation_price = 2290.0
    analysis.invalidation_direction = "below"
    analysis.rationale = "Gold breakout setup"
    analysis.entry_zone = "market"
    analysis.invalidation = "below 2290"

    mock_client = MagicMock()
    mock_client.model = "gemini-3.5-flash-lite"
    mock_client.provider_name = "gemini"
    mock_client.generate_content = AsyncMock(
        return_value=json.dumps(
            {
                "strongest_counter_argument": "DXY resistance overhead",
                "hard_block": False,
                "hard_block_reason": "",
                "recommend_block": False,
                "block_reason": "",
                "overall_quality": "high",
                "approve": True,
            }
        )
    )

    with (
        patch(
            "monika.application.analysis.validators.adversarial_check.get_client_for_task",
            return_value=mock_client,
        ),
        patch(
            "monika.application.analysis.validators.adversarial_check.SystemConfig.upsert",
            new_callable=AsyncMock,
        ),
    ):
        result = await run_adversarial_check(mock_session, analysis, {})

    assert result["approve"] is True
    assert mock_client.generate_content.called
    call_kwargs = mock_client.generate_content.call_args.kwargs

    # Padded system prompt and task role
    sys_prompt = call_kwargs.get("system_prompt", "")
    assert len(sys_prompt) >= 4000
    assert call_kwargs.get("task_role") == "adversarial_check"

    # User message layout: static rules / checklist must appear BEFORE dynamic SL/TP
    user_msg = call_kwargs["user_message"]
    pos_static = user_msg.find("QUALITY SEVERITY ANCHORS")
    pos_dynamic = user_msg.find("SL: 2300.0")
    assert pos_static != -1 and pos_dynamic != -1
    assert pos_static < pos_dynamic, "Static instructions must precede dynamic trade levels"


@pytest.mark.asyncio
async def test_trade_reflection_padded_system_prompt_and_task_role():
    """Verify trade reflection uses padded system prompt and passes explicit task_role."""
    from monika.application.analysis.memory.reflector import (
        TRADE_REFLECTION_SYSTEM_PROMPT,
        TradeReflector,
    )
    from monika.infrastructure.database.models import DecisionReflection

    assert TRADE_REFLECTION_SYSTEM_PROMPT is not None
    assert len(TRADE_REFLECTION_SYSTEM_PROMPT) >= 4000

    mock_client = MagicMock()
    mock_client.model = "minimax-m3.1-flash"
    mock_client.provider_name = "openrouter"
    mock_client.generate_content = AsyncMock(
        return_value=json.dumps(
            {
                "reflection_text": "Clean trend execution.",
                "lesson_tags": ["trend"],
                "alpha_lesson": "Captured strong alpha.",
            }
        )
    )

    reflector = TradeReflector(settings={})
    reflector.llm_client = mock_client

    mock_session = create_mock_async_session()
    mock_reflection = DecisionReflection(
        id=42,
        status="pending",
        is_paper_whatif=False,
        rationale_summary="Breakout confirmation",
        decision="BUY",
        confidence=0.8,
        outcome_pnl_usd=120.0,
        was_profitable=True,
        holding_hours=4.0,
        exit_reason="tp_hit",
        benchmark_name="DXY",
        alpha_return=2.4,
    )
    mock_session.get.return_value = mock_reflection

    await reflector.reflect_on_trade(mock_session, 42)

    assert mock_client.generate_content.called
    call_kwargs = mock_client.generate_content.call_args.kwargs
    sys_prompt = call_kwargs.get("system_prompt", "")
    assert len(sys_prompt) >= 4000
    assert call_kwargs.get("task_role") == "trade_reflection"


@pytest.mark.asyncio
async def test_risk_debate_models_json_dumps_sort_keys():
    """Verify conservative, aggressive, neutral, and portfolio manager serialize state with sorted keys."""
    from monika.application.analysis.debate.aggressive_risk_llm import analyze_risk_aggressive_llm
    from monika.application.analysis.debate.conservative_risk_llm import analyze_risk_conservative_llm
    from monika.application.analysis.debate.neutral_risk_llm import analyze_risk_neutral_llm
    from monika.application.analysis.debate.portfolio_manager import make_portfolio_decision

    test_context = {
        "z_tail_risk": "low",
        "a_confluence": 10,
        "m_drawdown": -0.5,
        "direction": "buy",
        "min_rr_ratio": 2.0,
    }

    mock_client = MagicMock()
    mock_client.generate_content = AsyncMock(
        return_value=json.dumps(
            {
                "risk_profile_assessment": "Acceptable edge",
                "recommended_multiplier": 1.0,
                "veto_trade": False,
                "approval": True,
                "recommended_risk_multiplier": 1.0,
                "reason": "Disciplined setup",
            }
        )
    )

    # 1. Conservative
    await analyze_risk_conservative_llm(mock_client, "EURUSD", test_context)
    call_kwargs = mock_client.generate_content.call_args.kwargs
    msg = call_kwargs["user_message"]
    pos_a = msg.find('"a_confluence"')
    pos_m = msg.find('"m_drawdown"')
    pos_z = msg.find('"z_tail_risk"')
    assert pos_a < pos_m < pos_z, "Conservative LLM context must serialize with sort_keys=True"
    assert call_kwargs.get("task_role") == "risk_gate_conservative"

    # 2. Aggressive
    await analyze_risk_aggressive_llm(mock_client, "EURUSD", test_context)
    call_kwargs = mock_client.generate_content.call_args.kwargs
    msg = call_kwargs["user_message"]
    pos_a = msg.find('"a_confluence"')
    pos_m = msg.find('"m_drawdown"')
    pos_z = msg.find('"z_tail_risk"')
    assert pos_a < pos_m < pos_z, "Aggressive LLM context must serialize with sort_keys=True"
    assert call_kwargs.get("task_role") == "risk_gate_aggressive"

    # 3. Neutral
    await analyze_risk_neutral_llm(mock_client, "EURUSD", test_context)
    call_kwargs = mock_client.generate_content.call_args.kwargs
    msg = call_kwargs["user_message"]
    pos_a = msg.find('"a_confluence"')
    pos_m = msg.find('"m_drawdown"')
    pos_z = msg.find('"z_tail_risk"')
    assert pos_a < pos_m < pos_z, "Neutral LLM context must serialize with sort_keys=True"
    assert call_kwargs.get("task_role") == "risk_gate_neutral"

    # 4. Portfolio Manager
    debate_states = {"z_debate": 1, "a_debate": 2}
    risk_state = {"z_heat": 2.0, "a_heat": 1.0}
    await make_portfolio_decision(mock_client, "EURUSD", debate_states, risk_state)
    call_kwargs = mock_client.generate_content.call_args.kwargs
    msg = call_kwargs["user_message"]
    pos_da = msg.find('"a_debate"')
    pos_dz = msg.find('"z_debate"')
    assert pos_da < pos_dz, "Portfolio Manager debate states must serialize with sort_keys=True"
    pos_sa = msg.find('"a_heat"')
    pos_sz = msg.find('"z_heat"')
    assert pos_sa < pos_sz, "Portfolio Manager risk state must serialize with sort_keys=True"
    assert call_kwargs.get("task_role") == "portfolio_manager_per_trade"


@pytest.mark.asyncio
async def test_system_tools_risk_gate_padded_system_prompt():
    """Verify system_tools provides padded RISK_GATE_SYSTEM_PROMPT and task_role="risk_gate"."""
    from monika.application.analysis.tools.mixins.system_tools import (
        RISK_GATE_SYSTEM_PROMPT,
        SystemToolsMixin,
    )

    assert RISK_GATE_SYSTEM_PROMPT is not None
    assert len(RISK_GATE_SYSTEM_PROMPT) >= 4000

    class DummyExecutor(SystemToolsMixin):
        def __init__(self):
            self.settings = {}
            self.session = None

    executor = DummyExecutor()
    inp = {
        "specialist_role": "risk_specialist",
        "task_prompt": "Evaluate structural risk for EURUSD",
        "symbol": "EURUSD",
    }

    mock_runner = MagicMock()
    mock_runner.run_isolated = AsyncMock(return_value={"success": True, "final_text": "Risk approved"})

    with (
        patch(
            "monika.application.analysis.subagent.isolated_harness.IsolatedSubagentRunner",
            return_value=mock_runner,
        ),
        patch(
            "monika.infrastructure.providers.llm_factory.get_client_for_task",
            return_value=MagicMock(),
        ),
    ):
        res = await executor._tool_delegate_specialist_analysis(inp)

    assert res["status"] == "success"
    assert mock_runner.run_isolated.called
    call_kwargs = mock_runner.run_isolated.call_args.kwargs
    assert call_kwargs.get("system_prompt") == RISK_GATE_SYSTEM_PROMPT
    assert call_kwargs.get("task_role") == "risk_gate"
