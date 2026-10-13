import pytest
from monika.application.analysis.tools.tools_definitions import (
    _tool,
    ALL_TOOLS,
    MACRO_ANALYSIS_TOOLS,
    PER_ASSET_ANALYSIS_TOOLS,
    ASSET_PRESCREEN_TOOLS,
    OPERATOR_INTERACTIVE_TOOLS,
)


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
    assert len(MACRO_ANALYSIS_TOOLS) > 0
    assert len(PER_ASSET_ANALYSIS_TOOLS) > 0
    assert len(ASSET_PRESCREEN_TOOLS) > 0
    assert len(OPERATOR_INTERACTIVE_TOOLS) > 0

    # check that submit_fundamental_brief is in stage 1
    names1 = [t["name"] for t in MACRO_ANALYSIS_TOOLS]
    assert "submit_fundamental_brief" in names1

    # check that submit_asset_analysis is in stage 2
    names2 = [t["name"] for t in PER_ASSET_ANALYSIS_TOOLS]
    assert "submit_asset_analysis" in names2

    names_pre = [t["name"] for t in ASSET_PRESCREEN_TOOLS]
    assert "submit_asset_analysis" in names_pre
