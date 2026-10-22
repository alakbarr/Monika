"""Integration tests for file tools exposed through the operator catalog."""

import pytest

from monika.application.analysis.tools.definitions.groups import ALL_TOOLS, OPERATOR_INTERACTIVE_TOOLS
from monika.application.analysis.tools.tool_executor import ToolExecutor


def test_file_tools_are_in_operator_catalog():
    all_names = {tool.get("name") for tool in ALL_TOOLS}
    operator_names = {tool.get("name") for tool in OPERATOR_INTERACTIVE_TOOLS}

    assert {"read_file", "write_file", "patch"} <= all_names
    assert {"read_file", "write_file", "patch"} <= operator_names


@pytest.mark.asyncio
async def test_file_tools_round_trip_through_tool_executor(tmp_path):
    target = tmp_path / "sample.py"
    executor = ToolExecutor(None, settings={})

    write_result = await executor.execute("write_file", {"path": str(target), "content": "value = 1\n"})
    assert "[SUCCESS]" in write_result
    assert target.read_text(encoding="utf-8") == "value = 1\n"

    read_result = await executor.execute("read_file", {"path": str(target)})
    assert "value = 1" in read_result

    patch_result = await executor.execute(
        "patch",
        {"path": str(target), "old_string": "value = 1", "new_string": "value = 2"},
    )
    assert "[SUCCESS]" in patch_result
    assert target.read_text(encoding="utf-8") == "value = 2\n"
