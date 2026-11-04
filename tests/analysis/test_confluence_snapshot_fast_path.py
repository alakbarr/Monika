# ==============================================================================
# File: tests/analysis/test_confluence_snapshot_fast_path.py
# Description: High-fidelity test verifying in-memory snapshot fast-path in confluence.
# ==============================================================================

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.analysis.calculators.confluence_calculator import calculate_confluence
from monika.application.services.market_snapshot_service import MarketSnapshotService


@pytest.mark.asyncio
async def test_confluence_uses_market_snapshot_service_fast_path():
    """Verify that calculate_confluence extracts indicators from MarketSnapshotService without DB queries."""
    MarketSnapshotService.reset()
    svc = MarketSnapshotService.get_instance()

    now = datetime.now(timezone.utc)
    # Set in-memory snapshot with known indicators
    svc.set_snapshot(
        symbol="EURUSD",
        timeframe="H4",
        timestamp=now,
        open_=1.1000,
        high=1.1050,
        low=1.0950,
        close=1.1020,
        volume=1000.0,
        indicators={
            "atr_14": 0.0035,
            "rsi_14": 55.0,
            "ema_20": 1.1010,
            "ema_50": 1.0990,
        },
    )

    mock_session = AsyncMock()
    # If session.execute is called for ATR_14 or RSI_14, it would fail if not mocked
    # We mock execute only for other queries (VIX, Brief, DXY, etc.)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result

    with (
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            return_value={"structure_confirmed": False},
        ),
    ):
        res = await calculate_confluence(
            session=mock_session,
            symbol="EURUSD",
            direction="buy",
            entry_price=1.1020,
            sl=1.0980,
            tp=1.1080,
            settings={},
        )

        assert "computed_score" in res
        # Check that none of the executed queries were for ATR_14 or RSI_14
        for call_args in mock_session.execute.call_args_list:
            stmt_str = str(call_args[0][0])
            assert "ATR_14" not in stmt_str, "ATR_14 query should have been bypassed by MarketSnapshotService"
            assert "RSI_14" not in stmt_str, "RSI_14 query should have been bypassed by MarketSnapshotService"
            assert "EMA_20" not in stmt_str, "EMA_20 query should have been bypassed by MarketSnapshotService"
            assert "EMA_50" not in stmt_str, "EMA_50 query should have been bypassed by MarketSnapshotService"

    MarketSnapshotService.reset()
