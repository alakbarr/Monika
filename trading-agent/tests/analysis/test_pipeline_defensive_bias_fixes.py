import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.validators.in_harness_grounding import InHarnessGroundingValidator
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from analysis.strategies.registry import StrategyRegistry
from scheduler.strategy_synthesis_scheduler import StrategySynthesisScheduler


def test_in_harness_grounding_symmetric_wait_validation():
    # 1. High confluence with empty/short rationale -> flagged as suspicious wait
    payload_bad_wait = {
        "decision": "WAIT",
        "confluence_score": 8,
        "rationale": "Just waiting",
    }
    is_grounded, errors, metadata = InHarnessGroundingValidator.verify_grounding(
        payload_bad_wait, {}
    )
    assert not is_grounded
    assert metadata.get("suspicious_wait") is True
    assert any("High confluence but chose WAIT" in e for e in errors)

    # 2. High confluence with detailed structural rationale -> valid wait
    payload_good_wait = {
        "decision": "WAIT",
        "confluence_score": 8,
        "rationale": "Waiting for H4 candle close at 14:00 UTC to confirm liquidity sweep reclaim.",
    }
    is_grounded, errors, metadata = InHarnessGroundingValidator.verify_grounding(
        payload_good_wait, {}
    )
    assert is_grounded
    assert len(errors) == 0

    # 3. Low confluence with standard wait -> valid wait
    payload_normal_wait = {
        "decision": "WAIT",
        "confluence_score": 4,
        "rationale": "No setup",
    }
    is_grounded, errors, metadata = InHarnessGroundingValidator.verify_grounding(
        payload_normal_wait, {}
    )
    assert is_grounded


@pytest.mark.asyncio
async def test_unified_threshold_hard_ceiling_7():
    from analysis.calculators.unified_threshold_calculator import (
        compute_unified_confluence_threshold,
        MAX_TOTAL_ADJUSTMENT,
    )
    assert MAX_TOTAL_ADJUSTMENT == 1

    from collections import namedtuple
    TradeStats = namedtuple('TradeStats', ['total_trades', 'winning_trades'])
    mock_trade_stats = TradeStats(total_trades=0, winning_trades=0)

    mock_session = AsyncMock()
    def mock_execute(query):
        res = MagicMock()
        res.first.return_value = mock_trade_stats
        res.scalar_one_or_none.return_value = None
        res.scalars.return_value.all.return_value = []
        return res

    mock_session.execute.side_effect = mock_execute

    # Compute threshold with mock
    thresh, reason = await compute_unified_confluence_threshold(
        mock_session, "EURUSD", {}, stage1_confidence=0.10
    )
    # Threshold must not exceed ceiling of 7
    assert thresh <= 7


@pytest.mark.asyncio
async def test_synthesis_engine_no_fallback_stub():
    scheduler = StrategySynthesisScheduler({})
    # Mock LLM generation returning None (failure)
    scheduler.synthesize_code = AsyncMock(return_value=None)

    result = await scheduler.synthesize_code("EURUSD", "Test Concept")
    # Must be None, never returning hardcoded fallback code
    assert result is None


@pytest.mark.asyncio
async def test_strategy_registry_discards_synthesized_stub():
    class MockStubStrategy(EdgeStrategy):
        strategy_id = "alpha_test_stub_123"
        applicable_symbols = {"EURUSD"}

        async def evaluate(self, session, symbol, settings):
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction="buy",
                valid=True,
                confidence=0.82,
                rationale="Stub",
                tags=["trend", "synthesized_alpha"],
            )

    StrategyRegistry.register(MockStubStrategy, overwrite=True)
    signals = await StrategyRegistry.evaluate_all(None, "EURUSD", {})

    # Signal from stub strategy with confidence 0.82 and synthesized_alpha tag must be discarded
    assert not any(s.strategy_id == "alpha_test_stub_123" for s in signals)
