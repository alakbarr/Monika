"""
Test Suite for Spill Reader Tool (retrieve_spilled_context).
Verifies DB retrieval, disk fallback, pagination slicing, error handling,
and registry integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from analysis.tools.domain.spill_reader_tool import (
    handle_retrieve_spilled_context,
    RetrieveSpilledContextInput,
    unified_retrieve_spilled_context,
)
from analysis.tools.unified_registry import unified_tool_registry
from analysis.tools.registry import default_tool_registry


@pytest.mark.asyncio
async def test_retrieve_spilled_context_from_db():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    # Mock payload text in DB
    full_payload = "A" * 5000 + "B" * 5000
    mock_result.scalar_one_or_none.return_value = full_payload
    mock_session.execute.return_value = mock_result

    res = await handle_retrieve_spilled_context(
        {"blob_id": "db://spill/spill_test123", "offset": 0, "max_chars": 1000},
        session=mock_session
    )

    assert res["success"] is True
    assert res["blob_id"] == "spill_test123"
    assert res["source"] == "postgres"
    assert res["offset"] == 0
    assert res["length"] == 1000
    assert res["total_chars"] == 10000
    assert res["has_more"] is True
    assert res["next_offset"] == 1000
    assert res["content"] == "A" * 1000


@pytest.mark.asyncio
async def test_retrieve_spilled_context_pagination():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    full_payload = "START_" + ("X" * 100) + "_END"
    mock_result.scalar_one_or_none.return_value = full_payload
    mock_session.execute.return_value = mock_result

    res = await handle_retrieve_spilled_context(
        {"blob_id": "spill_page_test", "offset": 6, "max_chars": 100},
        session=mock_session
    )

    assert res["success"] is True
    assert res["offset"] == 6
    assert res["length"] == 100
    assert res["content"] == "X" * 100
    assert res["has_more"] is True


@pytest.mark.asyncio
async def test_retrieve_spilled_context_disk_fallback(tmp_path):
    # Prepare a temp disk spill file
    cache_dir = tmp_path / "data" / "cache" / "spillover"
    cache_dir.mkdir(parents=True, exist_ok=True)
    spill_file = cache_dir / "spill_get_price_history_disk123.txt"
    spill_content = "DISK_SPILLED_PAYLOAD_TEST_CONTENT"
    spill_file.write_text(spill_content, encoding="utf-8")

    # DB returns None
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch("analysis.tools.domain.spill_reader_tool.Path") as mock_path:
        # Route to tmp_path
        def side_effect(p):
            if "data/cache/spillover" in str(p):
                return cache_dir
            return Path(p)
        mock_path.side_effect = side_effect

        res = await handle_retrieve_spilled_context(
            {"blob_id": "disk123", "offset": 0, "max_chars": 500},
            session=mock_session
        )

        assert res["success"] is True
        assert "disk" in res["source"]
        assert res["content"] == spill_content


@pytest.mark.asyncio
async def test_retrieve_spilled_context_not_found():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    res = await handle_retrieve_spilled_context(
        {"blob_id": "spill_nonexistent_999"},
        session=mock_session
    )

    assert res["success"] is False
    assert "not found" in res["error"]


@pytest.mark.asyncio
async def test_retrieve_spilled_context_unified_registry():
    # Verify tool is registered in unified_tool_registry
    tool_entry = unified_tool_registry.get_tool("retrieve_spilled_context")
    assert tool_entry is not None
    assert tool_entry.name == "retrieve_spilled_context"
    assert tool_entry.category == "SYSTEM"

    anthropic_schema = tool_entry.get_anthropic_schema()
    assert anthropic_schema["name"] == "retrieve_spilled_context"
    assert "blob_id" in anthropic_schema["input_schema"]["properties"]


@pytest.mark.asyncio
async def test_retrieve_spilled_context_default_tool_registry():
    handler = default_tool_registry.get("retrieve_spilled_context")
    assert handler is not None
    assert handler.name == "retrieve_spilled_context"
    # Test alias resolution
    canonical = default_tool_registry.resolve_name("read_spilled_blob")
    assert canonical == "retrieve_spilled_context"
