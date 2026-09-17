import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.stages.fundamental_stage import FundamentalStage


@pytest.mark.asyncio
async def test_macro_debate_concurrent_execution():
    settings = {
        "agent_architecture": {"enable_debate": True},
        "llm": {
            "task_roles": {
                "stage1_fundamental": {"primary": "mock-model"}
            }
        }
    }
    stage = FundamentalStage(settings)
    mock_session = AsyncMock()
    mock_brief = MagicMock()
    mock_brief.structured_json = json.dumps({"currency_bias": {"USD": "bullish"}})
    mock_brief.content_markdown = "Test brief"
    mock_brief.confidence = 0.8

    call_order = []

    async def mock_bull(context, cfg):
        call_order.append("bull_start")
        await asyncio.sleep(0.02)
        call_order.append("bull_end")
        return {"thesis": "Bullish DXY"}

    async def mock_bear(context, cfg):
        call_order.append("bear_start")
        await asyncio.sleep(0.02)
        call_order.append("bear_end")
        return {"thesis": "Bearish DXY"}

    async def mock_judge(bull, bear, context, cfg):
        call_order.append("judge")
        return {
            "winner": "BULL",
            "dxy_bias": "BULLISH",
            "bull_arguments_score": 8,
            "bear_arguments_score": 5,
        }

    with patch("analysis.debate.macro_bull_analyst.run_bull_analyst", side_effect=mock_bull), \
         patch("analysis.debate.macro_bear_analyst.run_bear_analyst", side_effect=mock_bear), \
         patch("analysis.debate.macro_judge.run_macro_judge", side_effect=mock_judge), \
         patch("analysis.debate.macro_debate_validator.validate_macro_judge_output", side_effect=lambda j, b, be: j):

        outcome = await stage._run_macro_debate(mock_session, mock_brief)

        assert outcome["ran"] is True
        assert outcome["winner"] == "BULL"
        # Since bull and bear ran concurrently, both started before either finished
        assert "bull_start" in call_order
        assert "bear_start" in call_order
        assert call_order.index("judge") > call_order.index("bull_end")
        assert call_order.index("judge") > call_order.index("bear_end")
        # Starts should precede ends
        assert call_order.index("bull_start") < call_order.index("bear_end")
        assert call_order.index("bear_start") < call_order.index("bull_end")


@pytest.mark.asyncio
async def test_macro_debate_exception_resilience():
    settings = {
        "agent_architecture": {"enable_debate": True},
        "llm": {
            "task_roles": {
                "stage1_fundamental": {"primary": "mock-model"}
            }
        }
    }
    stage = FundamentalStage(settings)
    mock_session = AsyncMock()
    mock_brief = MagicMock()
    mock_brief.structured_json = json.dumps({"currency_bias": {"USD": "neutral"}})
    mock_brief.content_markdown = "Test brief"
    mock_brief.confidence = 0.7

    async def mock_bull_error(context, cfg):
        raise RuntimeError("Bull analyst upstream timeout")

    async def mock_bear_success(context, cfg):
        return {"thesis": "Bearish DXY"}

    async def mock_judge(bull, bear, context, cfg):
        assert "error" in bull
        assert bear.get("thesis") == "Bearish DXY"
        return {
            "winner": "BEAR",
            "dxy_bias": "BEARISH",
            "bull_arguments_score": 1,
            "bear_arguments_score": 7,
        }

    with patch("analysis.debate.macro_bull_analyst.run_bull_analyst", side_effect=mock_bull_error), \
         patch("analysis.debate.macro_bear_analyst.run_bear_analyst", side_effect=mock_bear_success), \
         patch("analysis.debate.macro_judge.run_macro_judge", side_effect=mock_judge), \
         patch("analysis.debate.macro_debate_validator.validate_macro_judge_output", side_effect=lambda j, b, be: j):

        outcome = await stage._run_macro_debate(mock_session, mock_brief)

        assert outcome["ran"] is True
        assert outcome["winner"] == "BEAR"
