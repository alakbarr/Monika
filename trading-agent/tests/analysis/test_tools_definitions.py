import pytest
from analysis.tools.tools_definitions import _tool, ALL_TOOLS, STAGE1_TOOLS, STAGE2_TOOLS, STAGE2_PRESCREEN_TOOLS, TELEGRAM_TOOLS

def test_tool_helper():
    result = _tool("test_name", "test_desc", {"prop1": {"type": "string"}}, ["prop1"])
    assert result["name"] == "test_name"
    assert result["description"] == "test_desc"
    assert result["input_schema"]["type"] == "object"
    assert result["input_schema"]["properties"] == {"prop1": {"type": "string"}}
    assert result["input_schema"]["required"] == ["prop1"]

def test_all_tools_valid_schema():
    for t in ALL_TOOLS:
        assert "name" in t
        assert "description" in t
        assert "input_schema" in t
        assert "properties" in t["input_schema"]
        assert "required" in t["input_schema"]
        # Required must be a list
        assert isinstance(t["input_schema"]["required"], list)

def test_stage_tools_lists():
    assert len(STAGE1_TOOLS) > 0
    assert len(STAGE2_TOOLS) > 0
    assert len(STAGE2_PRESCREEN_TOOLS) > 0
    assert len(TELEGRAM_TOOLS) > 0
    
    # check that submit_fundamental_brief is in stage 1
    names1 = [t["name"] for t in STAGE1_TOOLS]
    assert "submit_fundamental_brief" in names1
    
    # check that submit_asset_analysis is in stage 2
    names2 = [t["name"] for t in STAGE2_TOOLS]
    assert "submit_asset_analysis" in names2
    
    names_pre = [t["name"] for t in STAGE2_PRESCREEN_TOOLS]
    assert "submit_asset_analysis" in names_pre
