import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
from scheduler.strategy_synthesis_scheduler import (
    StrategySynthesisScheduler,
    SynthesizedStrategyCandidate,
)
from analysis.strategies.hypothesis_registry import HypothesisRegistry, HypothesisStatus


@pytest.fixture
def tmp_hypothesis_file(tmp_path):
    return tmp_path / "test_strategy_hypotheses.json"


@pytest.mark.asyncio
async def test_synthesis_tracks_hypothesis_and_lineage(tmp_hypothesis_file):
    reg = HypothesisRegistry(storage_path=tmp_hypothesis_file)

    scheduler = StrategySynthesisScheduler(
        settings={
            "strategy_synthesis": {
                "enabled": True,
                "min_sharpe": 1.5,
                "max_drawdown_pct": 10.0,
                "min_trades": 5,
                "walk_forward_enabled": False,
            }
        }
    )
    scheduler.hypothesis_registry = reg

    valid_code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class MockPassStrategy(EdgeStrategy):
    strategy_id: str = "mock_pass"
    applicable_symbols: set = {"EURUSD"}
    compatible_regimes: set = {"TREND"}
    factor_family: str = "trend"

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="buy",
            valid=True,
            confidence=0.8,
            stop_loss=1.09,
            take_profit=1.12
        )
"""
    # 20 profitable trades -> Sharpe > 1.5, MaxDD < 10%
    simulated_returns = [0.015, 0.02, 0.01, 0.012, 0.018, 0.022, 0.015, 0.017] * 4

    with patch.object(scheduler, "_persist_candidate", new=AsyncMock()):
        candidate = await scheduler.evaluate_and_register_candidate(
            strategy_id="mock_pass",
            class_name="MockPassStrategy",
            code_str=valid_code,
            symbol="EURUSD",
            simulated_returns=simulated_returns,
            concept="Momentum pullback with volatility band compression",
            derived_from="parent_alpha_001",
            generation=1,
        )

    assert candidate is not None
    assert candidate.derived_from == "parent_alpha_001"
    assert candidate.generation == 1

    # Check hypothesis registry status is INCUBATING
    hypotheses = reg.get_by_status(HypothesisStatus.INCUBATING)
    assert len(hypotheses) == 1
    hyp = hypotheses[0]
    assert hyp.derived_from == "parent_alpha_001"
    assert hyp.generation == 1
    assert "EURUSD" in hyp.target_universe


@pytest.mark.asyncio
async def test_synthesis_rejects_and_deduplicates(tmp_hypothesis_file):
    reg = HypothesisRegistry(storage_path=tmp_hypothesis_file)

    scheduler = StrategySynthesisScheduler(
        settings={
            "strategy_synthesis": {
                "enabled": True,
                "min_sharpe": 1.5,
                "max_drawdown_pct": 10.0,
                "min_trades": 5,
                "walk_forward_enabled": False,
            }
        }
    )
    scheduler.hypothesis_registry = reg

    valid_code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class MockFailStrategy(EdgeStrategy):
    strategy_id: str = "mock_fail"
    applicable_symbols: set = {"EURUSD"}
    compatible_regimes: set = {"TREND"}
    factor_family: str = "trend"

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="buy",
            valid=True,
            confidence=0.8,
            stop_loss=1.09,
            take_profit=1.12
        )
"""
    # Bad returns -> negative Sharpe
    simulated_returns = [-0.02, -0.015, -0.03, -0.01, -0.02] * 4

    candidate = await scheduler.evaluate_and_register_candidate(
        strategy_id="mock_fail",
        class_name="MockFailStrategy",
        code_str=valid_code,
        symbol="EURUSD",
        simulated_returns=simulated_returns,
        concept="Naive breakout without volume filter",
    )

    assert candidate is None

    # Check hypothesis was registered and marked as REJECTED
    rejected = reg.get_by_status(HypothesisStatus.REJECTED)
    assert len(rejected) == 1
    assert "Threshold failure" in rejected[0].invalidation_notes

    # Now verify deduplication blocks the same or similar concept
    is_dup, reason = reg.is_duplicate_or_rejected("Naive breakout without volume filter")
    assert is_dup is True
    assert "Matches rejected hypothesis" in reason
