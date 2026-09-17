import pytest
import datetime
from unittest.mock import AsyncMock, MagicMock
from analysis.validators.core_data_validator import CoreDataValidator

@pytest.mark.asyncio
async def test_validate_core_data_freshness():
    session = AsyncMock()
    
    mock_result_1 = MagicMock()
    mock_brief = MagicMock()
    mock_brief.generated_at = datetime.datetime.now(datetime.timezone.utc)
    mock_brief.structured_json = '{"currency_bias": {"USD": "neutral", "EUR": "bullish", "GBP": "neutral", "JPY": "bearish", "AUD": "neutral", "XAU": "bullish"}}'
    mock_result_1.scalar_one_or_none.return_value = mock_brief
    
    mock_result_2 = MagicMock()
    mock_vix = MagicMock()
    mock_vix.date = datetime.datetime.now(datetime.timezone.utc).date()
    mock_vix.close = 15.0
    mock_result_2.scalar_one_or_none.return_value = mock_vix
    
    mock_result_3 = MagicMock()
    mock_dxy = MagicMock()
    mock_dxy.date = datetime.datetime.now(datetime.timezone.utc).date()
    mock_dxy.close = 104.5
    mock_result_3.scalars.return_value.all.return_value = [mock_dxy, mock_dxy, mock_dxy]
    
    session.execute.side_effect = [mock_result_1, mock_result_2, mock_result_3]
    
    validator = CoreDataValidator(session, {})
    is_valid, core_data, issues = await validator.validate_and_fetch_core_data()
    
    assert is_valid is True
    assert len(issues) == 0

@pytest.mark.asyncio
async def test_validate_core_data_stale():
    session = AsyncMock()
    
    mock_result_1 = MagicMock()
    mock_brief = MagicMock()
    # 3 days ago
    mock_brief.generated_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
    mock_result_1.scalar_one_or_none.return_value = mock_brief
    
    mock_result_2 = MagicMock()
    mock_result_2.scalar_one_or_none.return_value = None  # No VIX
    
    mock_result_3 = MagicMock()
    mock_result_3.scalars.return_value.all.return_value = [] # No DXY
    
    session.execute.side_effect = [mock_result_1, mock_result_2, mock_result_3]
    
    validator = CoreDataValidator(session, {})
    is_valid, core_data, issues = await validator.validate_and_fetch_core_data()
    
    assert is_valid is False
    assert len(issues) > 0
    assert any("Brief is" in i for i in issues)

@pytest.mark.asyncio
async def test_validate_core_data_brief_age_custom_limit():
    session = AsyncMock()
    now = datetime.datetime.now(datetime.timezone.utc)
    
    mock_result_1 = MagicMock()
    mock_brief = MagicMock()
    # 6.3 hours ago
    mock_brief.generated_at = now - datetime.timedelta(hours=6.3)
    mock_brief.structured_json = '{"currency_bias": {"USD": "neutral", "EUR": "bullish", "GBP": "neutral", "JPY": "bearish", "AUD": "neutral", "XAU": "bullish"}}'
    mock_result_1.scalar_one_or_none.return_value = mock_brief
    
    mock_result_2 = MagicMock()
    mock_vix = MagicMock()
    mock_vix.date = now.date()
    mock_vix.close = 15.0
    mock_result_2.scalar_one_or_none.return_value = mock_vix
    
    mock_result_3 = MagicMock()
    mock_dxy = MagicMock()
    mock_dxy.date = now.date()
    mock_dxy.close = 104.5
    mock_result_3.scalars.return_value.all.return_value = [mock_dxy, mock_dxy, mock_dxy]
    
    session.execute.side_effect = [mock_result_1, mock_result_2, mock_result_3]
    
    # Custom limit 6.5h -> 6.3h is valid
    validator = CoreDataValidator(session, {'data_quality': {'max_brief_age_analysis_hours': 6.5}})
    is_valid, core_data, issues = await validator.validate_and_fetch_core_data()
    
    assert is_valid is True
    assert len(issues) == 0

    # Reset side effect for failure case (> 6.5h)
    mock_brief.generated_at = now - datetime.timedelta(hours=6.8)
    session.execute.side_effect = [mock_result_1, mock_result_2, mock_result_3]
    validator_fail = CoreDataValidator(session, {'data_quality': {'max_brief_age_analysis_hours': 6.5}})
    is_valid_fail, _, issues_fail = await validator_fail.validate_and_fetch_core_data()
    assert is_valid_fail is False
    assert any("limit: 6.5h" in i for i in issues_fail)

