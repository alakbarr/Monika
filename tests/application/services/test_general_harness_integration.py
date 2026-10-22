"""Durability / general-purpose integration: GeneralHarnessService with file-tool runtime."""

import tempfile
from pathlib import Path

import pytest

from monika.application.services.general_harness_service import GeneralHarnessService
from monika.application.analysis.tools.unified_registry import unified_tool_registry


@pytest.mark.asyncio
async def test_developer_toolset_includes_file_tools():
    names = GeneralHarnessService.get_toolset_names("DEVELOPER")
    assert "read_file" in names
    assert "write_file" in names
    assert "patch" in names


@pytest.mark.asyncio
async def test_file_tool_roundtrip_via_harness_service():
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "sample.py"

        # Use unified registry dispatch directly (same path harness service uses)
        await unified_tool_registry.dispatch(
            name="write_file",
            arguments={"path": str(target), "content": "value = 1\n"},
        )
        assert target.read_text(encoding="utf-8") == "value = 1\n"

        await unified_tool_registry.dispatch(
            name="read_file",
            arguments={"path": str(target)},
        )

        await unified_tool_registry.dispatch(
            name="patch",
            arguments={
                "path": str(target),
                "old_string": "value = 1",
                "new_string": "value = 2",
            },
        )
        assert target.read_text(encoding="utf-8") == "value = 2\n"
