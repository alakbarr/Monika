import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.memory.counterfactual_simulator import CounterfactualSimulator
from analysis.memory.playbook_lifecycle import PlaybookLifecycleManager, PlaybookStatus


@pytest.mark.asyncio
async def test_counterfactual_simulator_promotion(tmp_path):
    lifecycle = PlaybookLifecycleManager(playbooks_dir=str(tmp_path))
    simulator = CounterfactualSimulator(lifecycle_manager=lifecycle)

    # Mock session returning 20 winning paper trades
    mock_trades = []
    for i in range(20):
        trade = MagicMock()
        trade.symbol = "EURUSD"
        trade.pnl_pct = 1.5 if i < 14 else -1.0  # 14 wins out of 20 = 70% win rate
        mock_trades.append(trade)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_trades
    mock_session.execute.return_value = mock_result

    res = await simulator.simulate_candidate(
        session=mock_session,
        playbook_name="eurusd_trending_playbook",
        symbol="EURUSD",
        min_sample=20,
        min_win_rate=0.55,
    )

    assert res["promoted"] is True
    assert res["win_rate"] == 0.70
    assert res["status"] == PlaybookStatus.ACTIVE.value
    assert lifecycle.get_status("eurusd_trending_playbook") == PlaybookStatus.ACTIVE


@pytest.mark.asyncio
async def test_counterfactual_simulator_rejection(tmp_path):
    lifecycle = PlaybookLifecycleManager(playbooks_dir=str(tmp_path))
    simulator = CounterfactualSimulator(lifecycle_manager=lifecycle)

    # Mock session returning losing paper trades
    mock_trades = []
    for i in range(20):
        trade = MagicMock()
        trade.symbol = "EURUSD"
        trade.pnl_pct = 1.0 if i < 8 else -1.0  # 8 wins = 40% win rate
        mock_trades.append(trade)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_trades
    mock_session.execute.return_value = mock_result

    res = await simulator.simulate_candidate(
        session=mock_session,
        playbook_name="eurusd_weak_playbook",
        symbol="EURUSD",
        min_sample=20,
        min_win_rate=0.55,
    )

    assert res["promoted"] is False
    assert res["win_rate"] == 0.40
    assert res["status"] == PlaybookStatus.CANDIDATE.value
