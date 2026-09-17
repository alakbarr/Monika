import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.strategies.gap_fade import DailyReopenGapFade
from database.models import PriceOHLCV

@pytest.mark.asyncio
async def test_gap_fade_reject_outside_window():
    settings = {'trading': {'edge_strategy': {'gap_fade': {'enabled': True}}}}
    strategy = DailyReopenGapFade(settings)
    
    # Mock clock to be outside session window (e.g., 2 hours after EURUSD open)
    # EURUSD open is 8 UTC. So let's mock clock.now()
    import utils.clock as clock
    import datetime
    
    # Assume we are at 11:00 UTC
    clock.set_simulated_now(datetime.datetime(2026, 1, 1, 11, 0, 0, tzinfo=datetime.timezone.utc))
    
    session = AsyncMock()
    sig = await strategy.evaluate(session, 'EURUSD', settings)
    
    assert not sig.valid
    assert "outside first-hour window" in sig.rationale


@pytest.mark.asyncio
async def test_gap_fade_unsupported_symbol():
    settings = {'trading': {'edge_strategy': {'gap_fade': {'enabled': True}}}}
    strategy = DailyReopenGapFade(settings)
    session = AsyncMock()
    sig = await strategy.evaluate(session, 'UNSUPPORTED_SYM', settings)
    assert not sig.valid
    assert "not in SESSION_OPEN_HOUR_UTC" in sig.rationale

