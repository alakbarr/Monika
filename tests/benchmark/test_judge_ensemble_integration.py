"""
Unit Tests for Benchmark Multi-Judge Ensemble.
"""
import pytest
from unittest.mock import AsyncMock, patch
from benchmark.judge import judge_output_ensemble


@pytest.mark.asyncio
async def test_judge_output_ensemble_consensus_calculation():
    """Verify judge_output_ensemble averages multiple judge scores and selects the consensus verdict."""
    judge_models = ["claude-sonnet-5", "gpt-4o", "deepseek-chat"]
    settings = {}
    
    # Mock responses from 3 judges: scores 8.0, 8.5, 7.5 -> consensus = 8.0
    mock_res_1 = ({"accuracy_score": 8, "grounding_score": 8, "actionability_score": 8, "consistency_score": 8, "hallucination_risk": "none"}, 8.0, 100, 50)
    mock_res_2 = ({"accuracy_score": 9, "grounding_score": 8, "actionability_score": 9, "consistency_score": 8, "hallucination_risk": "none"}, 8.5, 120, 60)
    mock_res_3 = ({"accuracy_score": 7, "grounding_score": 8, "actionability_score": 7, "consistency_score": 8, "hallucination_risk": "none"}, 7.5, 90, 45)

    with patch("benchmark.judge.judge_output", AsyncMock(side_effect=[mock_res_1, mock_res_2, mock_res_3])):
        verdict, score, total_in, total_out = await judge_output_ensemble(
            judge_models=judge_models,
            settings=settings,
            category="trade_decision",
            context_summary="Test context summary",
            candidate_output={"decision": "buy", "confidence": 0.8}
        )

    assert score == 8.0
    assert total_in == 310
    assert total_out == 155
    assert "ensemble_scores" in verdict
    assert len(verdict["ensemble_scores"]) == 3
    assert verdict["ensemble_consensus_score"] == 8.0
