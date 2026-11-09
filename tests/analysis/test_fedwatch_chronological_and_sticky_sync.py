# ==============================================================================
# File: tests/analysis/test_fedwatch_chronological_and_sticky_sync.py
# ==============================================================================

"""
Verification of:
1. Chronological sorting in handle_get_fedwatch_probabilities (preventing upcoming meeting truncation).
2. Symmetrical sticky currency detection via BriefContaminationGuard across prompt and validator.
3. Cross-check resiliency for fedwatch_dominant_pct against both CME FedWatch and get_central_bank_expectations.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.executor import ToolExecutor
from monika.application.analysis.tools.handlers.macro.central_banks import handle_get_fedwatch_probabilities
from monika.application.protocol.brief_contamination_guard import BriefContaminationGuard


@pytest.mark.asyncio
async def test_fedwatch_chronological_sorting():
    """Verify handle_get_fedwatch_probabilities sorts upcoming meetings chronologically,

    ensuring '9 Dec26' is first rather than alphabetically truncated behind '17 Mar27'/'27 Jan27'.
    """
    mock_session = AsyncMock()

    # Freeze time to November 9, 2026 (matching production issue timestamp)
    fixed_now = datetime(2026, 11, 9, 5, 58, 0, tzinfo=timezone.utc)

    # 5 meetings in database, including past (28 Oct26) and upcoming (9 Dec26, 27 Jan27, 17 Mar27, 28 Apr27)
    meeting_dates = ["28 Apr27", "17 Mar27", "27 Jan27", "9 Dec26", "28 Oct26"]
    mock_rows = []
    for i, m_date in enumerate(meeting_dates):
        row = MagicMock()
        row.id = 1000 + i
        row.meeting_date = m_date
        row.fetched_at = fixed_now - timedelta(hours=2)
        row.probabilities_json = (
            '{"current_rate_ref": 0.04, "probabilities": {"400-425": {"probability": 76.2, "action": "HIKE 25 bps"}}}'
        )
        mock_rows.append(row)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_rows
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch.object(clock, "now", return_value=fixed_now):
        res = await handle_get_fedwatch_probabilities({"limit": 4}, session=mock_session)

    assert res["count"] == 4
    result_dates = [m["meeting_date"] for m in res["meetings"]]
    # Must be chronologically ascending for upcoming meetings
    assert result_dates == ["9 Dec26", "27 Jan27", "17 Mar27", "28 Apr27"]
    assert res["next_meeting_date"] == "9 Dec26"


@pytest.mark.asyncio
async def test_validate_key_data_points_with_central_bank_expectations_fallback():
    """Verify _validate_key_data_points accepts claimed FedWatch dominant probability

    when it matches either CME FedWatch (76.2%) or central bank expectations (73.8%).
    """
    mock_session = AsyncMock()
    executor = ToolExecutor(session=mock_session, settings={})

    fedwatch_payload = {
        "count": 4,
        "meetings": [
            {
                "meeting_date": "9 Dec26",
                "probabilities": {
                    "probabilities": {
                        "400-425": {"probability": 76.2, "action": "cut_25"},
                        "375-400": {"probability": 23.8, "action": "maintain"},
                    }
                },
            }
        ],
    }
    cb_exp_payload = {
        "expectations": {
            "FED": {
                "bank": "FED",
                "dominant_probability_pct": 73.8,
            }
        }
    }

    async def mock_execute(tool_name, args=None):
        if tool_name == "get_fedwatch_probabilities":
            return fedwatch_payload
        elif tool_name == "get_central_bank_expectations":
            return cb_exp_payload
        return {}

    inp = {"key_data_points_used": {"fedwatch_dominant_pct": 73.8}}

    with patch.object(executor, "execute", side_effect=mock_execute):
        errors = await executor._validate_key_data_points(inp)
        mismatch_errors = [e for e in errors if "DATA_MISMATCH: Kamu menyatakan FedWatch dominant" in e]
        # 73.8% matches central bank expectations exactly and is within 2.4% of FedWatch 76.2%
        assert len(mismatch_errors) == 0


@pytest.mark.asyncio
async def test_sticky_currencies_shared_detection_across_weekend():
    """Verify BriefContaminationGuard.get_sticky_currencies bridges weekend gaps (7-day lookback)

    and detects identical sticky currencies symmetrically for prompt and validator.
    """
    mock_session = AsyncMock()
    now_dt = datetime(2026, 11, 9, 5, 58, 0, tzinfo=timezone.utc)  # Monday morning

    # 4 distinct cycles spanning Friday (Nov 6), Thursday (Nov 5), Wednesday (Nov 4), Tuesday (Nov 3)
    # This represents a weekend closure where no briefs were generated in the last 24h
    mock_briefs = []
    days_ago = [1, 3, 4, 5]  # Sunday night, Friday, Thursday, Wednesday
    for d in days_ago:
        mb = MagicMock()
        mb.generated_at = now_dt - timedelta(days=d)
        mb.currency_bias = {"AUD": "bearish", "XAU": "bearish", "BTC": "bearish", "USD": "bullish"}
        mb.structured_json = None
        mock_briefs.append(mb)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_briefs
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch.object(clock, "now", return_value=now_dt):
        sticky = await BriefContaminationGuard.get_sticky_currencies(mock_session, lookback_days=7)

    assert set(sticky.keys()) == {"AUD", "XAU", "BTC", "USD"}
    assert sticky["AUD"] == "bearish"
    assert sticky["XAU"] == "bearish"
    assert sticky["BTC"] == "bearish"
    assert sticky["USD"] == "bullish"


@pytest.mark.asyncio
async def test_tool_executor_anchoring_validation_with_guard():
    """Verify ToolExecutor._check_anchoring_and_require_justification enforces justification

    when sticky currencies are detected and accepts valid >=15 char numeric justifications.
    """
    mock_session = AsyncMock()
    executor = ToolExecutor(session=mock_session, settings={})

    with patch.object(
        BriefContaminationGuard,
        "get_sticky_currencies",
        AsyncMock(return_value={"AUD": "bearish", "XAU": "bearish", "BTC": "bearish"}),
    ):
        # 1. Missing justification -> rejected
        errors = await executor._check_anchoring_and_require_justification(
            current_bias={"AUD": "bearish", "XAU": "bearish", "BTC": "bearish", "USD": "bullish"},
            justification_map={},
        )
        assert len(errors) == 3
        assert any("AUD" in e for e in errors)
        assert any("XAU" in e for e in errors)
        assert any("BTC" in e for e in errors)

        # 2. Provided valid justification (>=15 chars with numbers) -> accepted
        valid_just = {
            "AUD": "AUD bearish maintained as RBA held at 4.85% and copper fell 1.2% to 4.15",
            "XAU": "XAU bearish maintained as 10Y real yield rose 6 bps to 1.85% on 2026-11-06",
            "BTC": "BTC bearish maintained due to ETF outflow of -$150M and funding rate at 0.005%",
        }
        errors_valid = await executor._check_anchoring_and_require_justification(
            current_bias={"AUD": "bearish", "XAU": "bearish", "BTC": "bearish", "USD": "bullish"},
            justification_map=valid_just,
        )
        assert len(errors_valid) == 0
