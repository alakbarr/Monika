import pytest
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.calculators.macro_priced_in_calculator import calculate_macro_priced_in_baseline

@pytest.mark.asyncio
async def test_calculate_macro_priced_in_baseline_defaults():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch("analysis.calculators.macro_priced_in_calculator.compute_usd_strength_proxy", new_callable=AsyncMock) as mock_proxy:
        mock_proxy.return_value = {"error": "no data"}
        result = await calculate_macro_priced_in_baseline(mock_session, as_of=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc))

        assert isinstance(result, dict)
        assert result["fedwatch"] == 0
        assert result["cot"] == 0
        assert result["usd_momentum"] == 0
        assert result["news_saturation"] == 0
        assert result["total_auto"] == 0
        assert result["interpretation"] == "NOT_PRICED_IN"
        assert isinstance(result["notes"], list)
        assert "computed_at" in result

@pytest.mark.asyncio
async def test_calculate_macro_priced_in_baseline_high_fedwatch_and_momentum():
    mock_session = AsyncMock()

    # Mock FedWatch row
    mock_fw_row = MagicMock()
    mock_fw_row.probabilities_json = json.dumps({
        "probabilities": {
            "cut_25": {"probability": 96}
        }
    })

    mock_fw_res = MagicMock()
    mock_fw_res.scalar_one_or_none.return_value = mock_fw_row

    # Mock COT row (None) and Digest (None)
    mock_empty_res = MagicMock()
    mock_empty_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [mock_fw_res, mock_empty_res, mock_empty_res]

    with patch("analysis.calculators.macro_priced_in_calculator.compute_usd_strength_proxy", new_callable=AsyncMock) as mock_proxy:
        mock_proxy.return_value = {
            "weighted_usd_change_pct": 3.5,
            "direction": "bullish"
        }
        result = await calculate_macro_priced_in_baseline(mock_session, as_of=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc))

        assert result["fedwatch"] == 3
        assert result["usd_momentum"] == 3
        assert result["total_auto"] == 6
        assert result["interpretation"] == "LARGELY_PRICED_IN"
