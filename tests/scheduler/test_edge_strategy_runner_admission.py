"""Unit tests for EdgeStrategyRunner tier admission and live execution gating."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from monika.application.analysis.strategies.base_strategy import EdgeSignal, StrategyTier
from monika.application.scheduler.edge_strategy_runner import EdgeStrategyRunner


@pytest.mark.asyncio
async def test_edge_strategy_runner_suppresses_quarantined_strategy():
    settings = {
        "trading": {
            "asset_universe": ["EURUSD"],
            "paper_trading": {"enabled": True},
        }
    }
    runner = EdgeStrategyRunner(settings=settings)

    sig_quarantined = EdgeSignal(
        strategy_id="smc_fvg",  # In QUARANTINED_STRATEGY_IDS
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1150,
    )

    mock_session = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_res)

    with (
        patch(
            "monika.application.scheduler.edge_strategy_runner.validate_data_freshness",
            AsyncMock(return_value={"ready": True}),
        ),
        patch(
            "monika.application.analysis.calculators.regime_classifier.classify_market_regime",
            AsyncMock(return_value={"regime": "trend"}),
        ),
        patch(
            "monika.application.scheduler.edge_strategy_runner.StrategyRegistry.evaluate_all",
            AsyncMock(return_value=[sig_quarantined]),
        ),
        patch("monika.application.scheduler.edge_strategy_runner.get_session") as mock_get_session,
        patch.object(runner, "_materialize_and_route", AsyncMock()) as mock_route,
    ):
        mock_get_session.return_value.__aenter__.return_value = mock_session
        await runner.run_once()

        # Quarantined signal must never be routed
        mock_route.assert_not_called()


@pytest.mark.asyncio
async def test_edge_strategy_runner_blocks_experimental_alpha_in_live_mode():
    settings = {
        "trading": {
            "asset_universe": ["EURUSD"],
            "paper_trading": {"enabled": False},  # LIVE trading mode!
        }
    }
    runner = EdgeStrategyRunner(settings=settings)

    sig = EdgeSignal(
        strategy_id="experimental_unvalidated_alpha",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1150,
    )

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    with (
        patch(
            "monika.application.analysis.calculators.macro_bias_filter.evaluate_macro_alignment",
            AsyncMock(return_value={"strong_conflict": False}),
        ),
        patch(
            "monika.application.analysis.arbitration.signal_arbitrator.SignalArbitrator.arbitrate",
            AsyncMock(
                return_value=MagicMock(
                    decision="buy",
                    confidence=0.85,
                    risk_multiplier=1.0,
                    selected_source="quant",
                    arbitration_reason="ok",
                )
            ),
        ),
        patch(
            "monika.application.scheduler.edge_strategy_runner.StrategyRegistry.get_tier",
            return_value=StrategyTier.EXPERIMENTAL,
        ),
        patch("monika.application.graph.reactive_graph.get_reactive_graph") as mock_graph,
    ):
        await runner._materialize_and_route(mock_session, sig)

        # Reactive graph must NOT be called in live mode for experimental alpha
        mock_graph.assert_not_called()
