# ==============================================================================
# File: tests/tools/test_universal_tools.py
# ==============================================================================

import os
import tempfile
import pytest
from analysis.tools.file_patch_engine import (
    FilePatchEngine,
    FuzzyMatcher,
    StaleOverwriteGuard,
    SyntaxLinter,
)
from analysis.tools.terminal_process_engine import TerminalProcessEngine
from analysis.tools.tool_search_engine import ToolSearchEngine


def test_fuzzy_matcher_stages():
    content = "def calculate_risk(lots, sl):\n    return lots * sl * 10\n"

    # Stage 1: Exact
    span, stage = FuzzyMatcher.find_match(content, "lots * sl * 10")
    assert span is not None
    assert stage.startswith("exact")

    # Stage 2: Whitespace tolerance
    span, stage = FuzzyMatcher.find_match(content, "lots   *   sl   *   10")
    assert span is not None

    # Stage 4: Indentation flexible
    span, stage = FuzzyMatcher.find_match(content, "        return lots * sl * 10\n")
    assert span is not None


def test_syntax_linter():
    valid_py = "def foo():\n    return 42\n"
    assert SyntaxLinter.lint_content("test.py", valid_py) is None

    invalid_py = "def foo():\nreturn 42"  # IndentationError/SyntaxError
    err = SyntaxLinter.lint_content("test.py", invalid_py)
    assert err is not None
    assert "SyntaxError" in err


def test_file_patch_engine_workflow():
    engine = FilePatchEngine()

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".py") as tf:
        tf.write("def sample():\n    pass\n")
        temp_path = tf.name

    try:
        # Verify read first
        ok, text = engine.read_file(temp_path)
        assert ok is True
        assert "def sample" in text

        # Test safe patch
        ok, msg = engine.patch_file(temp_path, "pass", "return True")
        assert ok is True

        # Read back to verify
        ok, new_text = engine.read_file(temp_path)
        assert "return True" in new_text

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_terminal_process_engine():
    with tempfile.TemporaryDirectory() as td:
        chk_file = os.path.join(td, "proc.json")
        engine = TerminalProcessEngine(checkpoint_path=chk_file)

        # Synchronous echo
        res = engine.execute("echo 'Monika Universal Engine'", timeout=5)
        assert res["success"] is True
        assert "Monika Universal Engine" in res["output"]

        # Background process
        bg_res = engine.execute("echo 'background task done'", background=True)
        assert bg_res["success"] is True
        sid = bg_res["session_id"]
        assert sid is not None

        # Poll status
        poll_res = engine.poll_process(sid)
        assert poll_res["success"] is True


def test_tool_search_engine():
    engine = ToolSearchEngine(token_budget=1000)

    # Register pinned and deferred tools
    engine.register_tool(
        name="calculate_position_size",
        description="Calculates deterministic lot sizes for FX and metals.",
        parameters={"type": "object"},
        category="EXECUTION",
        is_pinned=True,
    )
    engine.register_tool(
        name="web_search",
        description="Searches external web sources for current market news.",
        parameters={"type": "object"},
        category="WEB",
        is_pinned=False,
    )

    # Check active tools (only pinned should be initially active)
    schemas = engine.get_active_tool_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "calculate_position_size"

    # Search for deferred tool
    results = engine.search_tools("web market news")
    assert len(results) >= 1
    assert results[0]["name"] == "web_search"

    # Mount category on-demand
    loaded = engine.load_category("WEB")
    assert "web_search" in loaded
    new_schemas = engine.get_active_tool_schemas()
    assert len(new_schemas) == 2
