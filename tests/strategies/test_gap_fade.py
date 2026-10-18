from tests.conftest import create_mock_async_session
import pytest
from unittest.mock import AsyncMock, MagicMock
from monika.application.analysis.strategies.gap_fade import DailyReopenGapFade
from monika.infrastructure.database.models import PriceOHLCV


@pytest.mark.asyncio
async def test_gap_fade_reject_outside_window():
    settings = {"trading": {"edge_strategy": {"gap_fade": {"enabled": True}}}}
    strategy = DailyReopenGapFade(settings)

    # Mock clock to be outside session window (e.g., 2 hours after EURUSD open)
    # EURUSD open is 8 UTC. So let's mock clock.now()
    import monika.core.primitives.clock as clock
    import datetime

    # Assume we are at 11:00 UTC
    clock.set_simulated_now(datetime.datetime(2026, 1, 1, 11, 0, 0, tzinfo=datetime.timezone.utc))

    session = create_mock_async_session()
    sig = await strategy.evaluate(session, "EURUSD", settings)

    assert not sig.valid
    assert "outside first-hour window" in sig.rationale


@pytest.mark.asyncio
async def test_gap_fade_unsupported_symbol():
    settings = {"trading": {"edge_strategy": {"gap_fade": {"enabled": True}}}}
    strategy = DailyReopenGapFade(settings)
    session = create_mock_async_session()
    sig = await strategy.evaluate(session, "UNSUPPORTED_SYM", settings)
    assert not sig.valid
    assert "not in SESSION_OPEN_HOUR_UTC" in sig.rationale


@pytest.mark.asyncio
async def test_gap_fade_sunday_reopen_window():
    settings = {"trading": {"edge_strategy": {"gap_fade": {"enabled": True}}}}
    strategy = DailyReopenGapFade(settings)
    import monika.core.primitives.clock as clock
    import datetime

    # Sunday 2026-01-04 21:15 UTC (reopen window 21:00-23:00)
    # EURUSD open is 8 UTC, but Sunday 21:15 UTC is valid reopen
    clock.set_simulated_now(datetime.datetime(2026, 1, 4, 21, 15, 0, tzinfo=datetime.timezone.utc))
    session = create_mock_async_session()
    # It will proceed past window check into session.execute
    sig = await strategy.evaluate(session, "EURUSD", settings)
    assert sig.rationale != "outside first-hour window"

    # Tuesday 2026-01-06 21:15 UTC -> outside first-hour window for EURUSD
    clock.set_simulated_now(datetime.datetime(2026, 1, 6, 21, 15, 0, tzinfo=datetime.timezone.utc))
    sig_weekday = await strategy.evaluate(session, "EURUSD", settings)
    assert not sig_weekday.valid
    assert "outside first-hour window" in sig_weekday.rationale
