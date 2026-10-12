"""
Unit tests for QuantPlateauOptimizer.
Verifies ParameterSpec sampling & perturbation, Plateau stability scoring, and DSR calculation.
"""
import pytest
import math
from analysis.calculators.quant_plateau_optimizer import (
    ParameterSpec,
    QuantPlateauOptimizer,
    PlateauOptimizationResult,
)


def test_parameter_spec_sampling_and_perturbation():
    """Verify ParameterSpec generates values within bounds and adjacent neighbors."""
    p_int = ParameterSpec(name="period", param_type="int", low=10, high=50, step=5)
    sample_int = p_int.sample()
    assert 10 <= sample_int <= 50
    neighbors_int = p_int.perturb(20)
    assert 20 in neighbors_int
    assert len(neighbors_int) >= 2

    p_float = ParameterSpec(name="zscore", param_type="float", low=1.0, high=3.0, step=0.2)
    sample_float = p_float.sample()
    assert 1.0 <= sample_float <= 3.0
    neighbors_float = p_float.perturb(2.0)
    assert 2.0 in neighbors_float
    assert any(n < 2.0 for n in neighbors_float)
    assert any(n > 2.0 for n in neighbors_float)

    p_choice = ParameterSpec(name="exit_style", param_type="choice", choices=["adr", "atr", "fixed"])
    assert p_choice.sample() in ["adr", "atr", "fixed"]
    neighbors_choice = p_choice.perturb("atr")
    assert "atr" in neighbors_choice
    assert len(neighbors_choice) >= 2


@pytest.mark.asyncio
async def test_quant_plateau_optimizer_finds_stable_plateau():
    """
    Simulate parameter evaluation with an isolated sharp peak vs a flat plateau.
    The optimizer should choose the flat plateau over the isolated fragile peak.
    """
    param_space = [
        ParameterSpec(name="period", param_type="int", low=10, high=30, step=2),
    ]

    async def mock_eval_fn(params: dict) -> dict:
        p = params["period"]
        # Sharp isolated peak at period=16 (high Sharpe, but neighbors fail)
        if p == 16:
            return {"sharpe": 3.0, "trades": 35, "trade_returns": [0.02] * 35, "pnl_pct": 50.0}
        elif 14 <= p <= 18:
            return {"sharpe": 0.1, "trades": 30, "trade_returns": [0.001] * 30, "pnl_pct": 1.0}

        # Flat robust plateau around period 24-28 (consistent Sharpe 1.8 across all neighbors)
        if 22 <= p <= 28:
            return {"sharpe": 1.8, "trades": 35, "trade_returns": [0.015] * 35, "pnl_pct": 30.0}

        return {"sharpe": 0.5, "trades": 25, "trade_returns": [0.005] * 25, "pnl_pct": 5.0}

    optimizer = QuantPlateauOptimizer(
        param_space=param_space,
        n_trials=15,
        lambda_stability=1.0,
        min_trade_count=20,
        seed=123,
    )

    result = await optimizer.optimize(mock_eval_fn)

    assert isinstance(result, PlateauOptimizationResult)
    assert result.total_evaluations > 0
    # Should select parameter in the plateau (22-28), not the fragile peak 16
    assert result.best_params["period"] in [22, 24, 26, 28]
    assert result.is_plateau_stable is True
    assert result.neighbor_mean_sharpe >= 1.5
