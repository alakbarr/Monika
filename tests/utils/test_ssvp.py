from tests.conftest import create_mock_async_session
import pytest
import datetime
from unittest.mock import AsyncMock, MagicMock
from monika.application.protocol.context_snapshot import compute_context_snapshot_id, detect_context_version_split


@pytest.mark.asyncio
async def test_compute_context_snapshot_id():
    session = create_mock_async_session()
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
    session = create_mock_async_session()

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


def test_cross_agent_sync_no_cascade_suppression():
    from monika.application.protocol.cross_agent_sync import CrossAgentSynchronizer

    sync = CrossAgentSynchronizer(contradiction_threshold=0.60)
    pa_results = {
        "EURUSD": {"decision": "buy", "confidence": 0.90, "confluence_score": 8},
        "GBPUSD": {"decision": "sell", "confidence": 0.55, "confluence_score": 4},
        "AUDUSD": {"decision": "buy", "confidence": 0.85, "confluence_score": 7},
    }

    contradictions = sync.detect_contradictions(pa_results)
    assert len(contradictions) >= 1

    updated, suppressed = sync.apply_selective_suppression(pa_results, contradictions)

    # GBPUSD should be suppressed, but AUDUSD and EURUSD must remain untouched!
    assert "GBPUSD" in suppressed
    assert "AUDUSD" not in suppressed
    assert "EURUSD" not in suppressed
    assert updated["EURUSD"]["decision"] == "buy"
    assert updated["AUDUSD"]["decision"] == "buy"
    assert updated["GBPUSD"]["decision"] == "wait"


def test_jev_primitives_empty_answers_zero_confidence():
    from typesafe_sdk import Usage
    from monika.core.primitives.jev_primitives import SystemOneResponse, parse_jev_response_to_dict

    empty_resp = SystemOneResponse(answers={}, model="jev-mock", usage=Usage(input_tokens=0, output_tokens=0))
    parsed = parse_jev_response_to_dict(empty_resp)

    assert parsed["_confidence"] == 0.0
    assert parsed["_is_high_confidence"] is False


@pytest.mark.asyncio
async def test_enhanced_cds_thresholds_monotonicity():
    from monika.application.protocol.enhanced_cds import get_cds_thresholds_async

    session = create_mock_async_session()
    mock_res = MagicMock()
    mock_cfg = MagicMock()
    # Out of order / overlapping values in DB
    mock_cfg.value = '{"warning": 0.8, "sync_trigger": 0.4, "block_buysell": 0.2, "abort_all": 0.3}'
    mock_res.scalar_one_or_none.return_value = mock_cfg
    session.execute.return_value = mock_res

    thresholds = await get_cds_thresholds_async(session)
    assert thresholds["warning"] < thresholds["sync_trigger"]
    assert thresholds["sync_trigger"] < thresholds["block_buysell"]
    assert thresholds["block_buysell"] < thresholds["abort_all"]
