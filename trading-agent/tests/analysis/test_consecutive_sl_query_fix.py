"""
Unit Tests for Consecutive SL Query Fix in UnifiedThresholdCalculator.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from database.models import PaperTradeRecord
from analysis.calculators.unified_threshold_calculator import compute_unified_confluence_threshold


@pytest.mark.asyncio
async def test_consecutive_sl_penalty_triggered_only_when_all_three_are_sl():
    """Verify +2 penalty is triggered ONLY when the 3 latest closed trades are ALL sl_hit."""
    mock_session = AsyncMock()
    now = datetime.now(timezone.utc)

    # Scenario A: 3 latest trades are all sl_hit -> Penalty +2
    trades_all_sl = [
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", closed_at=now - timedelta(hours=1)),
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", closed_at=now - timedelta(hours=2)),
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", closed_at=now - timedelta(hours=3)),
    ]

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = trades_all_sl
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_res.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_res

    with patch("analysis.calculators.adaptive_policy.AdaptiveRiskPolicy.get_effective_threshold",
               AsyncMock(return_value=(6, "base"))):
        threshold, reason = await compute_unified_confluence_threshold(
            session=mock_session,
            symbol="EURUSD",
            settings={"trading": {"risk": {}}},
            stage1_confidence=0.8
        )

    assert "3_consecutive_sl_hits(EURUSD)" in reason
    assert threshold >= 7


@pytest.mark.asyncio
async def test_consecutive_sl_penalty_not_triggered_when_recent_win_exists():
    """Verify NO penalty when 3 latest trades contain a take profit (e.g. SL, TP, SL)."""
    mock_session = AsyncMock()
    now = datetime.now(timezone.utc)

    # Scenario B: 3 latest trades are SL, TP, SL -> NOT consecutive 3 SL
    trades_mixed = [
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", closed_at=now - timedelta(hours=1)),
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="tp_hit", closed_at=now - timedelta(hours=2)),
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", closed_at=now - timedelta(hours=3)),
    ]

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = trades_mixed
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_res.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_res

    with patch("analysis.calculators.adaptive_policy.AdaptiveRiskPolicy.get_effective_threshold",
               AsyncMock(return_value=(7, "base"))):
        threshold, reason = await compute_unified_confluence_threshold(
            session=mock_session,
            symbol="EURUSD",
            settings={"trading": {"risk": {}}},
            stage1_confidence=0.8
        )

    assert "3_consecutive_sl_hits(EURUSD)" not in reason
