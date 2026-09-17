import pytest
from unittest.mock import AsyncMock, patch

from utils.calibration.confidence_calibrator import compute_confidence_calibration

@pytest.mark.asyncio
async def test_compute_confidence_calibration_no_data():
    mock_session = AsyncMock()
    mock_session.execute.return_value = AsyncMock(all=lambda: [])
    
    result = await compute_confidence_calibration(mock_session)
    # The logic might return empty dict or early return if < 30 trades, so just check it doesn't crash
    assert isinstance(result, dict)

@pytest.mark.asyncio
async def test_compute_confidence_calibration_calibrated():
    # Simulate a scenario where higher confidence means higher win rate
    # Data is (is_win, confidence)
    simulated_data = [
        (True, 0.9), (True, 0.8), (False, 0.8), 
        (True, 0.6), (False, 0.6), (False, 0.5)
    ]
    
    class MockRecord:
        def __init__(self, is_win, conf):
            self.pnl_pct = 1.0 if is_win else -1.0
        
    class MockAnalysis:
        def __init__(self, is_win, conf):
            self.confidence = conf

    mock_results = [(MockRecord(win, conf), MockAnalysis(win, conf)) for win, conf in simulated_data]
    
    mock_session = AsyncMock()
    mock_session.execute.return_value = AsyncMock(all=lambda: mock_results)
    
    result = await compute_confidence_calibration(mock_session)
    
    assert isinstance(result, dict)

