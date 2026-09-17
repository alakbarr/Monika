"""
Integration and Concurrency Tests for Transactional Advisory Lock in ExecutionService.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from execution.execution_service import ExecutionService, ExecutionResult


@pytest.mark.asyncio
async def test_execution_service_lock_contention_handling():
    """Verify that when transactional_advisory_lock fails to acquire, ExecutionResult is rejected safely."""
    service = ExecutionService(
        settings={
            "trading": {
                "risk": {
                    "max_concurrent_positions": 5,
                    "news_window_minutes": 0,
                }
            }
        },
        mt5_client=MagicMock(),
        dry_run=True,
    )
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    mock_analysis = MagicMock()
    mock_analysis.id = 999
    mock_analysis.symbol = "EURUSD"
    mock_analysis.decision = "buy"
    mock_analysis.take_profit = 1.1000
    mock_analysis.stop_loss = 1.0800
    mock_analysis.risk_multiplier = 1.0
    mock_analysis.entry_zone = None
    mock_analysis.generated_at = datetime.now(timezone.utc)
    mock_analysis.brief_id = None
    mock_analysis.priced_in_score = None

    # Mock advisory lock returning False (locked by another worker)
    class MockLockedContext:
        async def __aenter__(self):
            return False
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("execution.execution_service.transactional_advisory_lock", return_value=MockLockedContext()), \
         patch.object(service, "_get_current_price", AsyncMock(return_value=(1.0850, False, 1.0))):
        
        result = await service._execute_analysis_internal(
            session=mock_session,
            analysis=mock_analysis,
            account_equity=10000.0,
        )
        
        assert result.risk_approved is False
        assert result.executed is False
        assert "advisory_lock_contention" in result.risk_checks_failed
        assert "Concurrent execution locked" in result.risk_rejection_reasons[0]
