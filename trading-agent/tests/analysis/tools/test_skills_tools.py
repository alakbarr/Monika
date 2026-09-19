import pytest
from analysis.tools.handlers.skills_tools import handle_skills_list, handle_skill_view
from analysis.tools.registry import default_tool_registry
import analysis.tools.handlers  # Trigger auto-registration


@pytest.mark.asyncio
async def test_handle_skills_list():
    res = await handle_skills_list()
    assert res["status"] == "success"
    assert res["total_skills"] > 0
    names = [s["name"] for s in res["skills"]]
    assert "central_banks_framework" in names or "smc_ict_playbook" in names
    assert all("summary" in s and "category" in s for s in res["skills"])


@pytest.mark.asyncio
async def test_handle_skill_view():
    # Success case
    res = await handle_skill_view({"skill_name": "central_banks_framework"})
    assert res["status"] == "success"
    assert "Federal Reserve" in res["content"] or "Fed" in res["content"] or "Central Bank" in res["content"]
    assert res["length_chars"] > 100

    # Error cases
    res_empty = await handle_skill_view({})
    assert res_empty["status"] == "error"

    res_missing = await handle_skill_view({"skill_name": "non_existent_fake_skill_12345"})
    assert res_missing["status"] == "error"
    assert "not found" in res_missing["message"].lower()


def test_skills_tools_registered_in_registry():
    handler_list = default_tool_registry.get("skills_list")
    assert handler_list is not None
    assert handler_list.name == "skills_list"

    handler_view = default_tool_registry.get("skill_view")
    assert handler_view is not None
    assert handler_view.name == "skill_view"
