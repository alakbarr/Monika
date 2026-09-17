import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.calibration.cds_threshold_calibrator import run_calibration_if_due

@pytest.mark.asyncio
async def test_calibration_skipped_if_not_due():
    # Mock session
    session = AsyncMock()
    
    # Mock cfg
    cfg = MagicMock()
    import json
    # Last run was just now
    cfg.value = json.dumps({'last_run': datetime.now(timezone.utc).isoformat()})
    
    class MockResult:
        def scalar_one_or_none(self):
            return cfg
            
    session.execute.return_value = MockResult()
    
    settings = {}
    result = await run_calibration_if_due(session, settings)
    
    assert result['status'] == 'skipped'
    assert 'reason' in result

@pytest.mark.asyncio
async def test_calibration_runs_if_due():
    # Mock session
    session = AsyncMock()
    
    # Mock cfg
    cfg = MagicMock()
    import json
    # Last run was 25 hours ago (due)
    last_run = datetime.now(timezone.utc) - timedelta(hours=25)
    cfg.value = json.dumps({'last_run': last_run.isoformat()})
    
    # Mock the two queries in run_calibration_if_due and _compute_cds_calibration
    class MockResult:
        def scalar_one_or_none(self):
            return cfg
        def all(self):
            return []
            
    session.execute.return_value = MockResult()
    session.commit = AsyncMock()
    
    settings = {}
    result = await run_calibration_if_due(session, settings)
    
    assert result['status'] == 'insufficient_data'
    session.commit.assert_called_once()
