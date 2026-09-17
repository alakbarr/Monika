import pytest
import datetime
from unittest.mock import AsyncMock, MagicMock
from utils.protocol.context_snapshot import compute_context_snapshot_id, detect_context_version_split

@pytest.mark.asyncio
async def test_compute_context_snapshot_id():
    session = AsyncMock()
    # Mocking sqlalchemy scalar_one_or_none and scalars().all()
    mock_result_1 = MagicMock()
    mock_brief = MagicMock()
    mock_brief.id = 1
    mock_brief.generated_at = datetime.datetime.now()
    mock_brief.structured_json = '{"currency_bias": {"USD": "bullish"}, "risk_sentiment": "risk-on"}'
    mock_result_1.scalar_one_or_none.return_value = mock_brief
    
    mock_result_2 = MagicMock()
    mock_vix = MagicMock()
    mock_vix.close = 18.5
    mock_vix.date = datetime.date.today()
    mock_result_2.scalar_one_or_none.return_value = mock_vix
    
    mock_result_3 = MagicMock()
    mock_dxy1 = MagicMock()
    mock_dxy1.close = 104.5
    mock_dxy2 = MagicMock()
    mock_dxy2.close = 104.0
    mock_result_3.scalars.return_value.all.return_value = [mock_dxy1, mock_dxy2]
    
    session.execute.side_effect = [mock_result_1, mock_result_2, mock_result_3]
    
    snapshot_id, components = await compute_context_snapshot_id(session)
    
    assert snapshot_id is not None
    assert components["brief_id"] == 1
    assert components["vix_regime"] == "moderate"
    assert components["dxy_trend"] == "up"

@pytest.mark.asyncio
async def test_detect_context_version_split():
    session = AsyncMock()
    
    mock_result = MagicMock()
    mock_analysis1 = MagicMock()
    mock_analysis1.context_snapshot_id = "abc"
    mock_analysis2 = MagicMock()
    mock_analysis2.context_snapshot_id = "def"
    mock_result.scalars.return_value.all.return_value = [mock_analysis1, mock_analysis2]
    
    session.execute.return_value = mock_result
    
    warning = await detect_context_version_split(session, datetime.datetime.now())
    assert warning is not None
    assert "CONTEXT VERSION SPLIT DETECTED" in warning

