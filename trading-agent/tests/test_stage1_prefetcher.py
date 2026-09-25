import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.prefetch.stage1_prefetcher import Stage1DataBundler

@pytest.mark.asyncio
async def test_stage1_data_bundler():
    session = AsyncMock()
    settings = {}
    
    with patch("analysis.prefetch.stage1_prefetcher.ToolExecutor") as MockExecutor, \
         patch("analysis.prefetch.stage1_prefetcher.compress_tool_payload") as mock_compress:
        
        # Setup mocks
        mock_executor_instance = MockExecutor.return_value
        
        # Mock execute to return different data based on the tool
        async def mock_execute(tool_name, tool_input):
            if tool_name == "get_economic_calendar":
                return {"events": []}
            elif tool_name == "get_news_digest":
                return {"news": "good"}
            return {"status": "ok", "tool": tool_name}
            
        mock_executor_instance.execute.side_effect = mock_execute
        
        mock_compress.return_value = {"compressed": True}

        bundler = Stage1DataBundler(session, settings)
        
        compressed_json, satisfied_tools, raw_data = await bundler.prefetch_all_data()
        
        assert json.loads(compressed_json) == {"compressed": True}
        assert isinstance(satisfied_tools, set)
        assert "get_dxy" in satisfied_tools
        assert "get_vix" in satisfied_tools
        assert "get_funding_rate" in satisfied_tools
        assert "get_bond_yield_spreads" in satisfied_tools
        assert "get_central_bank_expectations" in satisfied_tools
        assert len(satisfied_tools) == 15
        
        # Verify executor was called for multiple tools
        assert mock_executor_instance.execute.call_count == 15
        mock_executor_instance.execute.assert_any_call("get_dxy", {})
        mock_executor_instance.execute.assert_any_call("get_vix", {})
        mock_executor_instance.execute.assert_any_call("get_funding_rate", {})
        mock_executor_instance.execute.assert_any_call("get_bond_yield_spreads", {})
        mock_executor_instance.execute.assert_any_call("get_central_bank_expectations", {})
        
        # Verify compressor was called
        mock_compress.assert_called_once()
