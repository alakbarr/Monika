import pytest
import logging
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from analysis.strategies.registry import StrategyRegistry


class MockSingleSymbolStrategy(EdgeStrategy):
    strategy_id: str = "mock_xau_strategy"
    applicable_symbols: set = {"XAUUSD"}

    async def evaluate(self, session, symbol, settings):
        return None


class MockMultiSymbolStrategy(EdgeStrategy):
    strategy_id: str = "mock_multi_strategy"
    applicable_symbols: set = {"EURUSD", "GBPUSD", "XAUUSD"}

    async def evaluate(self, session, symbol, settings):
        return None


class MockAlphaNamingStrategy(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_123456"
    applicable_symbols: set = set()

    async def evaluate(self, session, symbol, settings):
        return None


def test_get_strategy_counts_and_log_summary(caplog):
    """Verifies get_strategy_counts and log_summary aggregate correctly without per-item INFO spam."""
    caplog.set_level(logging.DEBUG)

    # Clean registry state for isolation
    StrategyRegistry._registry.clear()

    StrategyRegistry.register(MockSingleSymbolStrategy, overwrite=True)
    StrategyRegistry.register(MockMultiSymbolStrategy, overwrite=True)
    StrategyRegistry.register(MockAlphaNamingStrategy, overwrite=True)

    # 1. Verify register() logs at DEBUG, NOT at INFO
    info_records = [r for r in caplog.records if r.levelno == logging.INFO and "Registered strategy" in r.message]
    assert len(info_records) == 0, f"Expected 0 INFO records for individual registrations, got {len(info_records)}"

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG and "Registered strategy" in r.message]
    assert len(debug_records) == 3

    # 2. Verify get_strategy_counts()
    total, counts = StrategyRegistry.get_strategy_counts()
    assert total == 3
    # XAUUSD is in single and multi (count 2)
    assert counts["XAUUSD"] == 2
    # EURUSD and GBPUSD are in multi (count 1 each)
    assert counts["EURUSD"] == 1
    assert counts["GBPUSD"] == 1
    # BTCUSD parsed from alpha_btcusd_123456 (count 1)
    assert counts["BTCUSD"] == 1

    # 3. Verify log_summary()
    caplog.clear()
    with caplog.at_level(logging.INFO):
        StrategyRegistry.log_summary()

    summary_records = [r for r in caplog.records if "[StrategyRegistry] Registered 3 strategies total" in r.message]
    assert len(summary_records) == 1
    msg = summary_records[0].message
    assert "XAUUSD: 2" in msg
    assert "BTCUSD: 1" in msg
    assert "EURUSD: 1" in msg
    assert "GBPUSD: 1" in msg


@pytest.mark.asyncio
async def test_load_dynamic_parameters_calls_log_summary():
    """Verify load_dynamic_parameters calls log_summary when synthesized strategies are loaded."""
    StrategyRegistry._registry.clear()
    StrategyRegistry._blacklisted_ids.clear()

    mock_row = MagicMock()
    mock_row.key = "synthesized_strategy_alpha_audusd_111111"
    mock_row.value = (
        '{"strategy_id": "alpha_audusd_111111", "python_code": "code", "class_name": "Synthesized_Test"}'
    )

    mock_session = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_row]
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_result

    with patch.object(StrategyRegistry, "log_summary") as mock_summary:
        with patch("scheduler.strategy_synthesis_scheduler.StrategySynthesisScheduler.compile_strategy_class") as mock_compile:
            class DummyCompiled(EdgeStrategy):
                strategy_id = "alpha_audusd_111111"
                applicable_symbols = {"AUDUSD"}

                async def evaluate(self, session, symbol, settings):
                    return None

            mock_compile.return_value = DummyCompiled
            await StrategyRegistry.load_dynamic_parameters(mock_session)

            assert mock_summary.call_count == 1
