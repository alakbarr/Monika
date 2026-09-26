# ==============================================================================
# File: tests/tools/test_domain_universal_tools.py
# ==============================================================================

import json
import os
import tempfile
import pytest

from analysis.tools.unified_registry import unified_tool_registry
from analysis.tools.domain.file_tools import (
    ReadFileInput,
    WriteFileInput,
    PatchFileInput,
    handle_read_file,
    handle_write_file,
    handle_patch,
)
from analysis.tools.domain.terminal_tools import (
    TerminalInput,
    ProcessManageInput,
    handle_terminal,
    handle_process_manage,
)
from analysis.tools.domain.skill_tools import (
    SkillsListInput,
    SkillViewInput,
    handle_skills_list,
    handle_skill_view,
)
from analysis.tools.domain.tool_search_tools import (
    ToolSearchInput,
    DescribeToolInput,
    LoadToolCategoryInput,
    handle_tool_search,
    handle_describe_tool,
    handle_load_tool_category,
)


@pytest.mark.asyncio
async def test_unified_tool_registry_has_universal_tools():
    """Verify all universal domain tools are properly registered."""
    tool_names = set(unified_tool_registry._tools.keys())
    expected = {
        "read_file",
        "write_file",
        "patch",
        "terminal",
        "process_manage",
        "skills_list",
        "skill_view",
        "tool_search",
        "describe_tool",
        "load_tool_category",
    }
    assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


@pytest.mark.asyncio
async def test_file_tools_lifecycle():
    """Verify read, write, and patch flow through domain handlers."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def foo():\n    return 42\n")
        temp_path = f.name

    try:
        # 1. Read
        read_res = await handle_read_file(ReadFileInput(path=temp_path))
        assert "def foo():" in read_res
        assert "return 42" in read_res

        # 2. Patch
        patch_res = await handle_patch(
            PatchFileInput(
                path=temp_path,
                old_string="return 42",
                new_string="return 100",
            )
        )
        assert "[SUCCESS]" in patch_res

        # 3. Read back verified
        read_res2 = await handle_read_file(ReadFileInput(path=temp_path))
        assert "return 100" in read_res2

        # 4. Write new content
        write_res = await handle_write_file(
            WriteFileInput(
                path=temp_path,
                content="def bar():\n    return 'hello'\n",
            )
        )
        assert "[SUCCESS]" in write_res

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_terminal_and_process_manage():
    """Verify terminal command execution and process supervision."""
    # 1. Foreground command
    res = await handle_terminal(
        TerminalInput(command="python -c \"print('Hello Monika')\"")
    )
    assert "[EXIT CODE 0]" in res
    assert "Hello Monika" in res

    # 2. Process list
    list_res = await handle_process_manage(ProcessManageInput(action="list"))
    assert isinstance(json.loads(list_res), list)


@pytest.mark.asyncio
async def test_skill_tools():
    """Verify skills listing and viewing."""
    # 1. List skills
    list_res = await handle_skills_list(SkillsListInput())
    skills = json.loads(list_res)
    assert isinstance(skills, list)
    assert len(skills) > 0

    skill_names = [s["name"] for s in skills]
    assert "software-development" in skill_names or "systematic-debugging" in skill_names

    # 2. View specific skill
    view_res = await handle_skill_view(
        SkillViewInput(skill_name="software-development")
    )
    assert "Software Development Skill" in view_res
    assert "Stale Overwrite Protection" in view_res


@pytest.mark.asyncio
async def test_tool_search_and_progressive_mounting():
    """Verify tool search, describe, and category loading."""
    # 1. Search tools
    search_res = await handle_tool_search(ToolSearchInput(query="patch"))
    results = json.loads(search_res)
    assert isinstance(results, list)
    tool_names = [r["name"] for r in results]
    assert "patch" in tool_names

    # 2. Describe tool
    desc_res = await handle_describe_tool(DescribeToolInput(tool_name="patch"))
    desc = json.loads(desc_res)
    assert desc["name"] == "patch"
    assert "parameters" in desc

    # 3. Load category
    cat_res = await handle_load_tool_category(
        LoadToolCategoryInput(category="FILESYSTEM")
    )
    assert "Successfully loaded" in cat_res
    assert "read_file" in cat_res or "patch" in cat_res
