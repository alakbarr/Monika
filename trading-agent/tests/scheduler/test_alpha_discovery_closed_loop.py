import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.strategies.registry import StrategyRegistry
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from scheduler.alpha_discovery_scheduler import (
    AlphaDiscoveryScheduler,
    AlphaHypothesis,
    CandidateAlphaProposal,
)
from scheduler.edge_strategy_runner import EdgeStrategyRunner
from backtest.walk_forward_engine import WalkForwardResult


class MockDynamicStrategy(EdgeStrategy):
    strategy_id = "test_mock_alpha"
    applicable_symbols = {"EURUSD"}

    async def evaluate(self, session, symbol, settings):
        # Read parameter to verify dynamic loading
        period = self.cfg.get("donchian_period", 10)
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="buy",
            valid=True,
            confidence=0.85,
            meta={"donchian_period": period}
        )


@pytest.fixture(autouse=True)
def cleanup_registry():
    orig_registry = dict(StrategyRegistry._registry)
    orig_dynamic = dict(StrategyRegistry._dynamic_params)
    StrategyRegistry._registry = {"test_mock_alpha": MockDynamicStrategy}
    yield
    StrategyRegistry._registry = orig_registry
    StrategyRegistry._dynamic_params = orig_dynamic


@pytest.mark.asyncio
async def test_strategy_registry_dynamic_parameter_loading():
    """Verifies StrategyRegistry loads parameters from DB SystemConfig and hot-reloads."""
    # 1. Hot-reload in memory
    StrategyRegistry.hot_reload("test_mock_alpha", {"donchian_period": 35})
    assert StrategyRegistry._dynamic_params.get("test_mock_alpha", {}).get("donchian_period") == 35

    # Evaluate all and verify dynamic parameter was reflected
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_empty = MagicMock()
    mock_empty.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_empty

    signals = await StrategyRegistry.evaluate_all(mock_session, "EURUSD", {"trading": {"edge_strategy": {}}})
    assert len(signals) == 1
    assert signals[0].meta["donchian_period"] == 35

    # 2. Test loading from DB SystemConfig rows
    mock_row_param = MagicMock()
    mock_row_param.key = "strategy_params_test_mock_alpha"
    mock_row_param.value = json.dumps({"donchian_period": 50})

    mock_row_alpha = MagicMock()
    mock_row_alpha.key = "candidate_alpha_123"
    mock_row_alpha.value = json.dumps({
        "status": "PAPER_ACTIVE",
        "hypothesis": {
            "strategy_type": "test_mock_alpha",
            "parameters": {"donchian_period": 60}
        }
    })

    mock_exec_res = MagicMock()
    mock_exec_res.scalars.return_value.all.side_effect = [
        [mock_row_param],   # for strategy_params_%
        [mock_row_alpha],   # for candidate_alpha_%
        [],                 # for synthesized_strategy_%
    ]
    mock_session.execute.return_value = mock_exec_res

    loaded = await StrategyRegistry.load_dynamic_parameters(mock_session)
    assert loaded["test_mock_alpha"]["donchian_period"] == 60


@pytest.mark.asyncio
async def test_alpha_auto_deploy_promotes_to_paper_active_and_hot_reloads():
    """
    Verifies AlphaDiscoveryScheduler with auto_deploy_paper=True:
    1. Promotes qualified hypothesis (WFE > 0.60) directly to PAPER_ACTIVE.
    2. Hot-reloads parameters into EdgeStrategyRunner and StrategyRegistry.
    """
    mock_runner = MagicMock(spec=EdgeStrategyRunner)
    mock_runner.hot_reload_strategy = MagicMock()

    settings = {
        "trading": {"asset_universe": ["EURUSD"]},
        "alpha_discovery": {"auto_deploy_paper": True, "min_wfe": 0.60}
    }
    scheduler = AlphaDiscoveryScheduler(
        settings=settings,
        edge_strategy_runner=mock_runner,
        auto_deploy_paper=True
    )

    hypothesis = AlphaHypothesis(
        hypothesis_id="hyp_alpha_auto_1",
        name="Auto Alpha Donchian",
        strategy_type="test_mock_alpha",
        symbol="EURUSD",
        parameters={"donchian_period": 42},
        description="Auto discovery test",
    )

    mock_wfo_result = WalkForwardResult(
        folds=[],
        aggregate_is_sharpe=2.0,
        aggregate_oos_sharpe=1.6,
        overall_wfe=0.75,  # > 0.60
        is_overfit=False,
        total_oos_trades=20,
        oos_win_rate_pct=65.0,
    )

    with patch("scheduler.alpha_discovery_scheduler.WalkForwardEngine") as mock_engine_cls, \
         patch("scheduler.alpha_discovery_scheduler.get_session") as mock_get_session:

        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_wfo_result)
        mock_instance.generate_markdown_report = MagicMock(return_value="# Report")
        mock_engine_cls.return_value = mock_instance

        mock_db_session = AsyncMock()
        mock_db_session.add = MagicMock()
        mock_exec = MagicMock()
        mock_exec.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_exec
        mock_get_session.return_value.__aenter__.return_value = mock_db_session

        proposal = await scheduler.evaluate_hypothesis(hypothesis)

        assert proposal is not None
        assert proposal.status == "PAPER_ACTIVE"
        assert proposal.overall_wfe == 0.75

        # Verify runner was hot-reloaded
        mock_runner.hot_reload_strategy.assert_called_once_with(
            "test_mock_alpha", {"donchian_period": 42}
        )

        # Verify StrategyRegistry dynamic params were updated
        assert StrategyRegistry._dynamic_params.get("test_mock_alpha", {}).get("donchian_period") == 42


@pytest.mark.asyncio
async def test_manual_promote_to_paper_active():
    """Verifies promote_to_paper_active promotes proposal and hot-reloads runner."""
    mock_runner = MagicMock(spec=EdgeStrategyRunner)
    mock_runner.hot_reload_strategy = MagicMock()

    scheduler = AlphaDiscoveryScheduler(settings={}, edge_strategy_runner=mock_runner)

    prop = CandidateAlphaProposal(
        proposal_id="alpha_test_manual",
        hypothesis=AlphaHypothesis(
            hypothesis_id="hyp_man",
            name="Manual Strategy",
            strategy_type="test_mock_alpha",
            symbol="EURUSD",
            parameters={"donchian_period": 99},
            description="Manual test"
        ),
        overall_wfe=0.68,
        aggregate_is_sharpe=1.7,
        aggregate_oos_sharpe=1.3,
        total_oos_trades=12,
        oos_win_rate_pct=58.0,
        is_overfit=False,
        status="PROPOSED",
    )
    scheduler.candidate_proposals.append(prop)

    with patch("scheduler.alpha_discovery_scheduler.get_session") as mock_get_session:
        mock_db_session = AsyncMock()
        mock_db_session.add = MagicMock()
        mock_exec = MagicMock()
        mock_exec.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_exec
        mock_get_session.return_value.__aenter__.return_value = mock_db_session

        ok = await scheduler.promote_to_paper_active("alpha_test_manual")
        assert ok is True
        assert prop.status == "PAPER_ACTIVE"
        mock_runner.hot_reload_strategy.assert_called_once_with(
            "test_mock_alpha", {"donchian_period": 99}
        )
