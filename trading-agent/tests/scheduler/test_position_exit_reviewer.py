import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from scheduler.position_exit_reviewer import PositionExitReviewer

@pytest.mark.asyncio
async def test_position_exit_reviewer_init():
    settings = {"trading": {"position_review_interval_hours": 4.0}}
    mock_stage = AsyncMock()
    mock_exec = AsyncMock()
    
    reviewer = PositionExitReviewer(settings, mock_stage, mock_exec)
    assert reviewer.settings == settings
    assert reviewer._per_asset == mock_stage
    assert reviewer._execution_service == mock_exec

@pytest.mark.asyncio
async def test_position_exit_reviewer_no_positions():
    settings = {"trading": {"position_review_interval_hours": 4.0}}
    mock_stage = AsyncMock()
    mock_exec = AsyncMock()
    
    reviewer = PositionExitReviewer(settings, mock_stage, mock_exec)
    
    with patch("scheduler.position_exit_reviewer.get_session") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session
        
        # Returns empty list for positions
        mock_session.execute.return_value = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        
        results = await reviewer.review_open_positions()
        
        assert len(results) == 0

