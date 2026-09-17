import pytest
from unittest.mock import AsyncMock, MagicMock
from utils.analytics.edge_tracker import is_trade_win
from utils.analytics.specialist_tracker import compute_specialist_reliability
from utils.analytics.adversarial_outcome_tracker import compute_adversarial_check_correlation
from utils.analytics.trade_autopsy import run_trade_autopsy


def test_is_trade_win_variations():
    # Test positive pnl_pct
    trade_win_pnl = MagicMock(pnl_pct=1.5, realized_pnl=None, exit_reason='sl_hit')
    assert is_trade_win(trade_win_pnl) is True

    # Test positive realized_pnl
    trade_win_usd = MagicMock(pnl_pct=None, realized_pnl=25.0, exit_reason='manual')
    assert is_trade_win(trade_win_usd) is True

    # Test tp_hit exit reason
    trade_tp_hit = MagicMock(pnl_pct=None, realized_pnl=None, exit_reason='tp_hit')
    assert is_trade_win(trade_tp_hit) is True

    # Test partial_tp exit reason
    trade_partial_tp = MagicMock(pnl_pct=None, realized_pnl=None, exit_reason='partial_tp')
    assert is_trade_win(trade_partial_tp) is True

    # Test loss
    trade_loss = MagicMock(pnl_pct=-1.2, realized_pnl=-50.0, exit_reason='sl_hit')
    assert is_trade_win(trade_loss) is False

    # Test dict input support
    assert is_trade_win({'pnl_pct': 2.5, 'exit_reason': 'manual'}) is True
    assert is_trade_win({'realized_pnl': 100.0, 'exit_reason': 'manual'}) is True
    assert is_trade_win({'exit_reason': 'tp_hit'}) is True
    assert is_trade_win({'exit_reason': 'partial_tp'}) is True
    assert is_trade_win({'pnl_pct': -0.5, 'exit_reason': 'sl_hit'}) is False

    # Test zero pnl_pct fallback to positive realized_pnl
    trade_zero_pnl_fallback = MagicMock(pnl_pct=0.0, realized_pnl=15.0, exit_reason='manual')
    assert is_trade_win(trade_zero_pnl_fallback) is True
    assert is_trade_win({'pnl_pct': 0.0, 'realized_pnl': 15.0, 'exit_reason': 'manual'}) is True

    # Test zero pnl_pct and zero realized_pnl fallback to exit_reason
    assert is_trade_win({'pnl_pct': 0.0, 'realized_pnl': 0.0, 'exit_reason': 'breakeven'}) is False
    assert is_trade_win({'pnl_pct': 0.0, 'realized_pnl': 0.0, 'exit_reason': 'tp_hit'}) is True

    # Test edge cases: None, empty dict, NaN
    assert is_trade_win(None) is False
    assert is_trade_win({}) is False
    assert is_trade_win({'pnl_pct': float('nan'), 'realized_pnl': float('nan')}) is False


def test_package_level_analytics_exports():
    import utils.analytics as ua
    assert hasattr(ua, 'is_trade_win')
    assert hasattr(ua, 'compute_edge_status')
    assert hasattr(ua, 'binomial_confidence_interval')
    assert ua.is_trade_win({'pnl_pct': 1.0}) is True


@pytest.mark.asyncio
async def test_specialist_tracker_insufficient():
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.all.return_value = []
    mock_session.execute.return_value = mock_res

    stats = await compute_specialist_reliability(mock_session, days_back=30)
    assert stats.get('specialists', {}) == {}


@pytest.mark.asyncio
async def test_adversarial_tracker_insufficient():
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res

    res = await compute_adversarial_check_correlation(mock_session, days_back=30)
    assert res['status'] == 'insufficient_data'
