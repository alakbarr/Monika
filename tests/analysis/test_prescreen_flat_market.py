"""Tests for Phase 3B: Smart Re-analysis Gate (Flat-Market Check) in prescreen."""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.analysis.stages.per_asset.runner_mixins.prescreen import PrescreenMixin
from monika.infrastructure.database.models import (
    AssetAnalysis,
    Position,
    PriceOHLCV,
    TechnicalIndicator,
)
from tests.conftest import create_mock_async_session


class PrescreenTestRunner(PrescreenMixin):
    """Test harness implementing minimal PerAssetRunner attributes for PrescreenMixin."""

    def __init__(self):
        self._last_analysis_time = {}
        self._haiku_client = None
        self.always_open_assets = set()
        self.settings = {"trading": {"asset_universe": ["EURUSD", "GBPUSD", "XAUUSD"]}}


@pytest.fixture
def runner():
    return PrescreenTestRunner()


def _build_mock_execute(
    open_position=None,
    last_analysis=None,
    price_now=1.1002,
    atr_h4=0.0020,
    atr_h1=None,
):
    """Helper to mock session.execute returning the specified domain entities."""

    async def mock_execute(query, *args, **kwargs):
        qs = str(query).lower()
        res = MagicMock()

        # Check compiled parameters if available
        is_h4 = False
        is_h1 = False
        try:
            compiled = query.compile()
            if hasattr(compiled, "params"):
                for v in compiled.params.values():
                    if v == "H4":
                        is_h4 = True
                    elif v == "H1":
                        is_h1 = True
        except Exception:
            pass

        if "h4" in qs:
            is_h4 = True
        if "h1" in qs:
            is_h1 = True

        if "from positions" in qs:
            res.scalar_one_or_none.return_value = open_position
        elif "from asset_analysis" in qs:
            res.scalar_one_or_none.return_value = last_analysis
        elif "from price_ohlcv" in qs:
            res.scalar_one_or_none.return_value = price_now
        elif "from technical_indicators" in qs:
            if is_h4:
                if atr_h4 is not None:
                    ti = TechnicalIndicator(
                        symbol="EURUSD",
                        timeframe="H4",
                        indicator_name="ATR_14",
                        value_json=json.dumps({"atr": atr_h4}) if isinstance(atr_h4, (int, float)) else atr_h4,
                        timestamp=datetime.now(timezone.utc),
                    )
                    res.scalar_one_or_none.return_value = ti
                else:
                    res.scalar_one_or_none.return_value = None
            elif is_h1:
                if atr_h1 is not None:
                    ti = TechnicalIndicator(
                        symbol="EURUSD",
                        timeframe="H1",
                        indicator_name="ATR_14",
                        value_json=json.dumps({"atr": atr_h1}) if isinstance(atr_h1, (int, float)) else atr_h1,
                        timestamp=datetime.now(timezone.utc),
                    )
                    res.scalar_one_or_none.return_value = ti
                else:
                    res.scalar_one_or_none.return_value = None
            else:
                res.scalar_one_or_none.return_value = None
        else:
            res.scalar_one_or_none.return_value = None

        return res

    return mock_execute


@pytest.mark.asyncio
async def test_flat_market_skips_when_criteria_met(runner):
    """Verify that when price moved < 0.25x ATR, last decision was 'wait' < 60m ago,

    and there is no open position, prescreen returns False with the flat-market message.
    """
    mock_session = create_mock_async_session()
    now_utc = datetime.now(timezone.utc)

    last_analysis = AssetAnalysis(
        symbol="EURUSD",
        decision="wait",
        generated_at=now_utc - timedelta(minutes=25),
        price_at_analysis=1.1000,
    )

    # price_now = 1.1002 (delta 0.0002), ATR 0.0020 -> 0.10x ATR (<0.25x)
    mock_session.execute.side_effect = _build_mock_execute(
        open_position=None,
        last_analysis=last_analysis,
        price_now=1.1002,
        atr_h4=0.0020,
    )

    should_run, reason = await runner._run_prescreen(mock_session, "EURUSD")

    assert should_run is False
    assert "Quick flat-market check" in reason
    assert "<0.25x" in reason
    assert "reusing WAIT posture" in reason
    assert "25m ago" in reason


@pytest.mark.asyncio
async def test_flat_market_skips_with_uppercase_wait(runner):
    """Verify that last decision 'WAIT' (uppercase) is recognized and skipped."""
    mock_session = create_mock_async_session()
    now_utc = datetime.now(timezone.utc)

    last_analysis = AssetAnalysis(
        symbol="EURUSD",
        decision="WAIT",
        generated_at=now_utc - timedelta(minutes=15),
        price_at_analysis=1.1000,
    )

    mock_session.execute.side_effect = _build_mock_execute(
        open_position=None,
        last_analysis=last_analysis,
        price_now=1.1001,
        atr_h4=0.0020,
    )

    should_run, reason = await runner._run_prescreen(mock_session, "EURUSD")

    assert should_run is False
    assert "Quick flat-market check" in reason


@pytest.mark.asyncio
async def test_flat_market_not_skipped_when_price_moved_ge_025x_atr(runner):
    """Verify that when price moved >= 0.25x ATR, it does not skip via flat market check."""
    mock_session = create_mock_async_session()
    now_utc = datetime.now(timezone.utc)

    last_analysis = AssetAnalysis(
        symbol="EURUSD",
        decision="wait",
        generated_at=now_utc - timedelta(minutes=20),
        price_at_analysis=1.1000,
    )

    # price_now = 1.1010 (delta 0.0010), ATR 0.0020 -> 0.50x ATR (>= 0.25x)
    mock_session.execute.side_effect = _build_mock_execute(
        open_position=None,
        last_analysis=last_analysis,
        price_now=1.1010,
        atr_h4=0.0020,
    )

    should_run, reason = await runner._run_prescreen(mock_session, "EURUSD")

    # Should not be skipped by flat-market check
    assert "Quick flat-market check" not in reason


@pytest.mark.asyncio
async def test_flat_market_not_skipped_when_open_position_exists(runner):
    """Verify that when symbol has an open position, it does not skip even if price moved < 0.25x ATR."""
    mock_session = create_mock_async_session()
    now_utc = datetime.now(timezone.utc)

    open_pos = Position(
        symbol="EURUSD",
        status="open",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
    )

    last_analysis = AssetAnalysis(
        symbol="EURUSD",
        decision="wait",
        generated_at=now_utc - timedelta(minutes=10),
        price_at_analysis=1.1000,
    )

    # price moved only 0.0001 (0.05x ATR), but open position exists
    mock_session.execute.side_effect = _build_mock_execute(
        open_position=open_pos,
        last_analysis=last_analysis,
        price_now=1.1001,
        atr_h4=0.0020,
    )

    should_run, reason = await runner._run_prescreen(mock_session, "EURUSD")

    assert "Quick flat-market check" not in reason


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["buy", "sell", "BUY", "SELL", "avoid"])
async def test_flat_market_not_skipped_when_last_decision_not_wait(runner, decision):
    """Verify that when last decision was buy, sell, or avoid, flat market check does not skip."""
    mock_session = create_mock_async_session()
    now_utc = datetime.now(timezone.utc)

    last_analysis = AssetAnalysis(
        symbol="EURUSD",
        decision=decision,
        generated_at=now_utc - timedelta(minutes=20),
        price_at_analysis=1.1000,
    )

    mock_session.execute.side_effect = _build_mock_execute(
        open_position=None,
        last_analysis=last_analysis,
        price_now=1.1001,
        atr_h4=0.0020,
    )

    should_run, reason = await runner._run_prescreen(mock_session, "EURUSD")

    assert "Quick flat-market check" not in reason


@pytest.mark.asyncio
async def test_flat_market_not_skipped_when_analysis_older_than_60m(runner):
    """Verify that when last analysis is >= 60 minutes old, flat market check does not skip."""
    mock_session = create_mock_async_session()
    now_utc = datetime.now(timezone.utc)

    last_analysis = AssetAnalysis(
        symbol="EURUSD",
        decision="wait",
        generated_at=now_utc - timedelta(minutes=61),
        price_at_analysis=1.1000,
    )

    mock_session.execute.side_effect = _build_mock_execute(
        open_position=None,
        last_analysis=last_analysis,
        price_now=1.1001,
        atr_h4=0.0020,
    )

    should_run, reason = await runner._run_prescreen(mock_session, "EURUSD")

    assert "Quick flat-market check" not in reason


@pytest.mark.asyncio
async def test_flat_market_uses_h1_atr_fallback(runner):
    """Verify that when H4 ATR is unavailable, H1 ATR is used as fallback."""
    mock_session = create_mock_async_session()
    now_utc = datetime.now(timezone.utc)

    last_analysis = AssetAnalysis(
        symbol="EURUSD",
        decision="wait",
        generated_at=now_utc - timedelta(minutes=15),
        price_at_analysis=1.1000,
    )

    # H4 ATR is None, H1 ATR is 0.0020, delta is 0.0002 -> 0.10x ATR
    mock_session.execute.side_effect = _build_mock_execute(
        open_position=None,
        last_analysis=last_analysis,
        price_now=1.1002,
        atr_h4=None,
        atr_h1=0.0020,
    )

    should_run, reason = await runner._run_prescreen(mock_session, "EURUSD")

    assert should_run is False
    assert "Quick flat-market check" in reason
    assert "0.10x ATR" in reason


@pytest.mark.asyncio
async def test_flat_market_fallback_when_price_at_analysis_is_none(runner):
    """Verify that when price_at_analysis is None, it defaults to price_now (delta = 0)."""
    mock_session = create_mock_async_session()
    now_utc = datetime.now(timezone.utc)

    last_analysis = AssetAnalysis(
        symbol="EURUSD",
        decision="wait",
        generated_at=now_utc - timedelta(minutes=30),
        price_at_analysis=None,
    )

    mock_session.execute.side_effect = _build_mock_execute(
        open_position=None,
        last_analysis=last_analysis,
        price_now=1.1000,
        atr_h4=0.0020,
    )

    should_run, reason = await runner._run_prescreen(mock_session, "EURUSD")

    assert should_run is False
    assert "Quick flat-market check" in reason
    assert "0.00x ATR" in reason


@pytest.mark.asyncio
async def test_flat_market_does_not_crash_on_invalid_atr(runner):
    """Verify that invalid or zero ATR does not cause division by zero or exception."""
    mock_session = create_mock_async_session()
    now_utc = datetime.now(timezone.utc)

    last_analysis = AssetAnalysis(
        symbol="EURUSD",
        decision="wait",
        generated_at=now_utc - timedelta(minutes=10),
        price_at_analysis=1.1000,
    )

    # ATR is 0.0
    mock_session.execute.side_effect = _build_mock_execute(
        open_position=None,
        last_analysis=last_analysis,
        price_now=1.1001,
        atr_h4=0.0,
    )

    should_run, reason = await runner._run_prescreen(mock_session, "EURUSD")

    assert "Quick flat-market check" not in reason
