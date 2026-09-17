"""
Unit Tests for Extended Macro Data Freshness in data_validator.py.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from utils.validation.data_validator import validate_data_freshness


@pytest.mark.asyncio
async def test_validate_data_freshness_macro_tables():
    """Verify validate_data_freshness checks TreasuryYield, DXY, COT, and FedWatch."""
    mock_session = AsyncMock()
    now = datetime.now(timezone.utc)

    execute_side_effects = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=1))),  # EURUSD H1 OHLCV
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=1))),  # EURUSD H1 Ind
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=1))),  # News
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=2))),  # Calendar
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=12))), # VIX
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(days=10))),  # Stale Yield
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(days=1))),   # Fresh DXY
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(days=20))),  # Stale COT
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(days=1))),   # Fresh FedWatch
    ]
    mock_session.execute.side_effect = execute_side_effects

    res = await validate_data_freshness(
        session=mock_session,
        symbols=["EURUSD"],
        timeframes=["H1"]
    )

    warnings_str = " ".join(res.get("warnings", []))
    assert "Treasury yield data is" in warnings_str and "(stale)" in warnings_str
    assert "COT report data is" in warnings_str and "(stale)" in warnings_str


@pytest.mark.asyncio
async def test_validate_data_freshness_dxy_fedwatch_and_vix_stale():
    """Verify stale DXY, FedWatch, and VIX are detected and flagged."""
    mock_session = AsyncMock()
    now = datetime.now(timezone.utc)

    execute_side_effects = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=1))),  # OHLCV
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=1))),  # Ind
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=1))),  # News
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=2))),  # Calendar
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(days=5))),   # Stale VIX (>72h)
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(days=2))),   # Yield
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(days=8))),   # Stale DXY (>120h)
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(days=3))),   # COT
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(days=10))),  # Stale FedWatch (>168h)
    ]
    mock_session.execute.side_effect = execute_side_effects

    res = await validate_data_freshness(
        session=mock_session,
        symbols=["EURUSD"],
        timeframes=["H1"]
    )

    warnings_str = " ".join(res.get("warnings", []))
    assert "VIX data is" in warnings_str
    assert "DXY data is" in warnings_str
    assert "FedWatch probability data is" in warnings_str


@pytest.mark.asyncio
async def test_validate_data_freshness_strict_mode_empty_macro_tables():
    """Verify require_macro_data=True turns missing macro tables into hard errors."""
    mock_session = AsyncMock()
    now = datetime.now(timezone.utc)

    execute_side_effects = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=1))),  # OHLCV
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=1))),  # Ind
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=1))),  # News
        MagicMock(scalar_one_or_none=MagicMock(return_value=now - timedelta(hours=2))),  # Calendar
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),                       # Missing VIX
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),                       # Missing Yield
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),                       # Missing DXY
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),                       # Missing COT
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),                       # Missing FedWatch
    ]
    mock_session.execute.side_effect = execute_side_effects

    res = await validate_data_freshness(
        session=mock_session,
        symbols=["EURUSD"],
        timeframes=["H1"],
        require_macro_data=True
    )

    assert res["ready"] is False
    errors_str = " ".join(res.get("errors", []))
    assert "VIX" in errors_str
    assert "Treasury" in errors_str
    assert "DXY" in errors_str
