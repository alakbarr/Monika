from tests.conftest import create_mock_async_session
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from monika.application.analysis.prefetch.stage1_prefetcher import Stage1DataBundler


@pytest.mark.asyncio
async def test_stage1_data_bundler():
    session = create_mock_async_session()
    settings = {}

    with (
        patch("monika.application.analysis.prefetch.stage1_prefetcher.ToolExecutor") as MockExecutor,
        patch("monika.application.analysis.prefetch.stage1_prefetcher.compress_tool_payload") as mock_compress,
    ):
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
        assert "diff_central_bank_documents" in satisfied_tools
        # Verify executor was called for multiple tools (21 stage1 tools + 6 cross-asset momentum + 1 FedWatch repricing shift)
        assert mock_executor_instance.execute.call_count == 28
        mock_executor_instance.execute.assert_any_call("get_dxy", {})
        mock_executor_instance.execute.assert_any_call("get_vix", {})
        mock_executor_instance.execute.assert_any_call("get_funding_rate", {})
        mock_executor_instance.execute.assert_any_call("get_bond_yield_spreads", {})
        mock_executor_instance.execute.assert_any_call("get_central_bank_expectations", {})
        mock_executor_instance.execute.assert_any_call(
            "diff_central_bank_documents", {"bank": "FED", "doc_type": "STATEMENT"}
        )

        # Verify compressor was called
        mock_compress.assert_called_once()

        # Verify extra parallel feeds, cross-asset momentum, and aggregated sentiment
        assert "brent_crude" in raw_data
        assert "eurusd_momentum" in raw_data
        assert "cross_asset_momentum" in raw_data
        assert set(raw_data["cross_asset_momentum"].keys()) == {
            "EURUSD",
            "GBPUSD",
            "USDJPY",
            "AUDUSD",
            "XAUUSD",
            "BTCUSD",
            "XTIUSD",
        }
        assert "aggregated_sentiment" in raw_data
        assert "XAUUSD" in raw_data["aggregated_sentiment"]
        assert "EURUSD" in raw_data["aggregated_sentiment"]
        assert "BTCUSD" in raw_data["aggregated_sentiment"]


def test_stage1_cross_asset_momentum_terminal_rendering():
    session = create_mock_async_session()
    bundler = Stage1DataBundler(session, {})
    terminal = bundler._synthesize_tier1_terminal(
        {
            "cross_asset_momentum": {
                "EURUSD": {"change_1d_pct": 0.42, "change_5d_pct": 1.15, "trend": "bullish"},
                "USDJPY": {"change_1d_pct": -0.35, "change_5d_pct": 0.80, "trend": "pullback"},
            }
        }
    )
    assert "cross_asset_momentum_matrix" in terminal
    matrix_str = terminal["cross_asset_momentum_matrix"]
    assert "[CROSS-ASSET 24H/5D PRICE MOMENTUM & RECONCILIATION MATRIX]" in matrix_str
    assert "EURUSD: change_1d_pct=0.42% | change_5d_pct=1.15% | trend=bullish" in matrix_str
    assert "ANTI-STICKY RECONCILIATION:" in matrix_str


def test_brief_submission_sanitizes_punctuation_macro_regime():
    from monika.application.analysis.tools.mixins.brief_submission import (
        VALID_MACRO_REGIMES,
        sanitize_macro_regime,
    )

    for bad_input in (",", ".", ";", "-", ", - ,", "  ,  ", None, ""):
        res = sanitize_macro_regime(bad_input)
        assert res != ","
        assert len(res) >= 3
        assert res in VALID_MACRO_REGIMES

    assert sanitize_macro_regime(",", "Persistent inflation and slowing growth point to stagflation.") == "stagflation"
    assert sanitize_macro_regime(";", "Acute equity selloff and risk-off flight to safety.") == "risk-off"
    assert sanitize_macro_regime(" 'goldilocks', ") == "goldilocks"
    assert sanitize_macro_regime(",", "Mixed signals without clear keyword.") == "transitional"
