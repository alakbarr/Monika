import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.calculators.economic_surprise import _parse_numeric, compute_surprise_scores
from database.models import EconomicCalendar

class TestEconomicSurprise:
    def test_parse_numeric(self):
        assert _parse_numeric("1.5") == 1.5
        assert _parse_numeric("1.5%") == 1.5
        assert _parse_numeric("2,000") == 2000.0
        assert _parse_numeric("1.5K") == 1500.0
        assert _parse_numeric("-2.5M") == -2500000.0
        assert _parse_numeric("1B") == 1000000000.0
        
        # Invalid / Empty
        assert _parse_numeric("-") is None
        assert _parse_numeric("--") is None
        assert _parse_numeric("N/A") is None
        assert _parse_numeric("") is None
        assert _parse_numeric(None) is None
        assert _parse_numeric("invalid") is None

    @pytest.mark.asyncio
    async def test_compute_surprise_scores(self):
        # Setup mock session
        session = AsyncMock()
        session.add = MagicMock()
        
        # Create mock events
        event1 = EconomicCalendar(id=1, actual="200K", forecast="150K", surprise_score=None)
        event2 = EconomicCalendar(id=2, actual="1.5%", forecast="1.5%", surprise_score=None)
        event3 = EconomicCalendar(id=3, actual="-1.0M", forecast="2.0M", surprise_score=None)
        event4 = EconomicCalendar(id=4, actual="1.0", forecast="0.0", surprise_score=None) # Zero forecast
        event5 = EconomicCalendar(id=5, actual="N/A", forecast="10K", surprise_score=None) # Invalid actual
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [event1, event2, event3, event4, event5]
        session.execute.return_value = mock_result
        
        updated = await compute_surprise_scores(session)
        
        # Verify
        assert updated == 4
        session.commit.assert_called_once()
        
        # event1: actual=200000, forecast=150000 -> surprise = 50000 / 150000 * 100 = 33.3333
        assert event1.surprise_score == 33.3333
        
        # event2: actual=1.5, forecast=1.5 -> surprise = 0
        assert event2.surprise_score == 0.0
        
        # event3: actual=-1000000, forecast=2000000 -> surprise = -3000000 / 2000000 * 100 = -150.0
        assert event3.surprise_score == -150.0
        
        # event4: forecast = 0 -> diff = 1.0 - 0.0 = 1.0 (since abs(forecast) <= 0.001)
        assert event4.surprise_score == 1.0
        
        # event5: un-updated
        assert event5.surprise_score is None

    @pytest.mark.asyncio
    async def test_compute_surprise_scores_no_events(self):
        session = AsyncMock()
        session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result
        
        updated = await compute_surprise_scores(session)
        
        assert updated == 0
        session.commit.assert_not_called()
