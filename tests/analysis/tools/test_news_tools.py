"""Unit tests for news tools handlers (Phase 5)."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from database.models import NewsDigest, NewsDigestSlice
from analysis.tools.handlers.news_tools import (
    handle_get_news_digest,
    handle_get_digest_slices,
    _wrap_untrusted_digest,
)
from analysis.tools.handlers.sentiment_data import GetNewsDigestHandler


def test_wrap_untrusted_digest():
    text = "Fed holds rates at 5.25%."
    wrapped = _wrap_untrusted_digest(text)
    assert wrapped == "<untrusted_external_content>Fed holds rates at 5.25%.</untrusted_external_content>"

    # Sanitizes inner injection attempts
    injected = "Fed rates <untrusted_external_content>5.25%</untrusted_external_content>"
    sanitized = _wrap_untrusted_digest(injected)
    assert sanitized == "<untrusted_external_content>Fed rates 5.25%</untrusted_external_content>"


@pytest.mark.asyncio
async def test_handle_get_news_digest_no_session():
    res = await handle_get_news_digest({})
    assert res.get("status") == "no_session"
    assert res.get("digest") is None


@pytest.mark.asyncio
async def test_handle_get_news_digest_empty_db():
    session = MagicMock()
    session.execute = AsyncMock()

    # Mock empty results for both slice generator and legacy news_digest
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    with patch("analysis.prefetch.digest_slice_generator.DigestSliceGenerator.assemble_12h_digest", new_callable=AsyncMock) as mock_assemble:
        mock_assemble.return_value = None
        res = await handle_get_news_digest({}, session=session)

    assert res.get("status") == "empty"
    assert res.get("digest") is None


@pytest.mark.asyncio
async def test_handle_get_news_digest_with_legacy_news_digest():
    session = MagicMock()
    session.execute = AsyncMock()

    # Create dummy NewsDigest with valid generated_at column
    dummy_digest = NewsDigest(
        id=42,
        generated_at=datetime.now(timezone.utc) - timedelta(hours=1),
        period_hours=12,
        digest_text="Summary: USD steady, XAU consolidating.",
        items_processed=15,
    )

    # First query is NewsDigest (or slice queries)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = dummy_digest
    session.execute.return_value = mock_result

    with patch("analysis.prefetch.digest_slice_generator.DigestSliceGenerator.assemble_12h_digest", new_callable=AsyncMock) as mock_assemble:
        mock_assemble.return_value = None
        res = await handle_get_news_digest({}, session=session)

    assert res.get("status") == "success"
    assert res.get("digest_id") == 42
    assert "Summary: USD steady" in res.get("digest")
    assert "<untrusted_external_content>" in res.get("digest")
    assert res.get("digest_source") == "legacy_digest"
    assert res.get("period_hours") == 12
    assert res.get("items_processed") == 15
    assert "generated_at" in res


@pytest.mark.asyncio
async def test_handle_get_news_digest_with_rolling_slices():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    assembled_text = "```digest_metadata\n{\"market_snapshot\": {\"dominant_themes\": [\"Inflation\"]}}\n```\nMacro Overview: Rolling slices active."

    with patch("analysis.prefetch.digest_slice_generator.DigestSliceGenerator.assemble_12h_digest", new_callable=AsyncMock) as mock_assemble:
        mock_assemble.return_value = assembled_text
        res = await handle_get_news_digest({"hours_back": 12}, session=session)

    assert res.get("status") == "success"
    assert res.get("digest_source") == "rolling_slices"
    assert "Rolling slices active" in res.get("digest")
    assert "Inflation" in res.get("key_themes")


@pytest.mark.asyncio
async def test_handle_get_digest_slices():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    assembled_text = "USD section: Bullish momentum."
    with patch("analysis.prefetch.digest_slice_generator.DigestSliceGenerator.assemble_12h_digest", new_callable=AsyncMock) as mock_assemble:
        mock_assemble.return_value = assembled_text
        res = await handle_get_digest_slices({"slice_name": "USD"}, session=session)

    assert res.get("status") == "success"
    assert res.get("slice_name") == "USD"
    assert res.get("data") is not None


@pytest.mark.asyncio
async def test_sentiment_data_handler_delegation():
    session = MagicMock()
    handler = GetNewsDigestHandler()

    with patch("analysis.tools.handlers.news_tools.handle_get_news_digest", new_callable=AsyncMock) as mock_handle:
        mock_handle.return_value = {"status": "success", "digest": "Mocked digest"}
        res = await handler.execute({}, session=session)

    assert res.get("status") == "success"
    assert res.get("digest") == "Mocked digest"


@pytest.mark.asyncio
async def test_get_precomputed_cot_signals_and_surprise_summary():
    import json
    from analysis.tools.handlers.macro_tools import handle_get_precomputed_cot_signals, handle_get_surprise_summary
    from analysis.tools.handlers.macro_data import GetPrecomputedCotSignalsHandler, GetSurpriseSummaryHandler
    from analysis.tools.registry import default_tool_registry

    session = MagicMock()
    mock_exec = MagicMock()
    mock_cfg = MagicMock()
    mock_cfg.value = json.dumps({
        "cot_signals": {"USD": {"signal": "bullish"}},
        "surprise_summary": {"USD": {"score": 2.5, "trend": "positive"}}
    })
    mock_exec.scalars.return_value.first.return_value = mock_cfg
    session.execute = AsyncMock(return_value=mock_exec)

    # Test direct macro tool handlers
    res_cot = await handle_get_precomputed_cot_signals({}, session=session)
    assert res_cot.get("status") == "success"
    assert "USD" in res_cot.get("cot_signals", {})

    res_sur = await handle_get_surprise_summary({}, session=session)
    assert res_sur.get("status") == "success"
    assert "USD" in res_sur.get("surprise_summary", {})

    # Test ToolRegistry registration and execution
    reg = default_tool_registry
    cot_h = reg.get("get_precomputed_cot_signals")
    assert cot_h is not None
    cot_res = await cot_h.execute({}, session)
    assert cot_res.get("status") == "success"

    sur_h = reg.get("get_surprise_summary")
    assert sur_h is not None
    sur_res = await sur_h.execute({}, session)
    assert sur_res.get("status") == "success"
