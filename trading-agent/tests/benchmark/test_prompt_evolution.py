import pytest
from unittest.mock import AsyncMock, MagicMock
from benchmark.prompt_evolution import GEPALiteEvolver
from benchmark.judge import JUDGE_PERSONAS, judge_output_ensemble

@pytest.mark.asyncio
async def test_gepa_lite_evolver():
    evolver = GEPALiteEvolver()
    res = await evolver.evolve_round(session=None, population_size=2, generations=1)
    assert "prompt" in res
    assert "score" in res
    assert "tokens" in res

def test_judge_personas_portfolio_assessor():
    assert "portfolio_risk_assessor" in JUDGE_PERSONAS
    assert "Portfolio Risk Assessor" in JUDGE_PERSONAS["portfolio_risk_assessor"]

@pytest.mark.asyncio
async def test_judge_ensemble_supports_4_personas():
    settings = {"benchmark": {"default_judges": ["claude_sonnet", "gemini_flash", "deepseek_v3", "gpt_4o"]}}
    # Check that ensemble assigns 4 distinct personas
    # (Mocking judge_output)
    from benchmark import judge
    orig_judge_output = judge.judge_output
    judge.judge_output = AsyncMock(return_value=({"grounding_score": 8, "accuracy_score": 8, "actionability_score": 8, "consistency_score": 8, "hallucination_risk": "none"}, 8.0, 100, 50))
    try:
        verdict, score, tin, tout = await judge.judge_output_ensemble(
            judge_models=["m1", "m2", "m3", "m4"],
            settings=settings,
            category="trade_decision",
            context_summary="ctx",
            candidate_output="out"
        )
        assert score == 8.0
        assert len(verdict["ensemble_verdicts"]) == 4
        personas = [v["judge_persona"] for v in verdict["ensemble_verdicts"]]
        assert "portfolio_risk_assessor" in personas
    finally:
        judge.judge_output = orig_judge_output
