import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.memory.skill_crystallizer import SkillCrystallizer


@pytest.mark.asyncio
async def test_skill_crystallizer_cluster():
    crystallizer = SkillCrystallizer()
    
    mock_session = AsyncMock()
    mock_r1 = MagicMock()
    mock_r1.symbol = "EURUSD"
    mock_r1.confidence = 0.85
    mock_r1.outcome_pnl_usd = 120.0
    mock_r1.reflection_text = "TREND | London open sweep confirmed"
    mock_r1.alpha_lesson = "Wait for Asian low sweep before buy entry"
    mock_r1.specific_lesson = "H4 BOS required"
    mock_r1.rationale_summary = "Long setup on SMC displacement"

    mock_r2 = MagicMock()
    mock_r2.symbol = "EURUSD"
    mock_r2.confidence = 0.90
    mock_r2.outcome_pnl_usd = 240.0
    mock_r2.reflection_text = "TREND | London open sweep confirmed"
    mock_r2.alpha_lesson = "Wait for Asian low sweep before buy entry"
    mock_r2.specific_lesson = "FVG rebalance confirmed"
    mock_r2.rationale_summary = "Long setup on Asian sweep"

    mock_execute_res = MagicMock()
    mock_execute_res.scalars.return_value.all.return_value = [mock_r1, mock_r2]
    mock_session.execute.return_value = mock_execute_res

    res = await crystallizer.evaluate_and_crystallize(mock_session, symbol="EURUSD")
    assert len(res) == 1
    assert res[0]["symbol"] == "EURUSD"
    assert res[0]["instances"] == 2
    assert "eurusd" in res[0]["name"]
