"""
Unit tests for Phase 4 & Phase 5:
- Enhanced Spill Subsystem (grep_pattern, line pagination, storage_key alias, path normalization)
- Tool Concurrency, Parallel CodeExecutionRpcServer, and render_tools_sdk_py
- FilePatchEngine fuzzy matching, diff preview, and CAS observation tracking
- CodeSearchTool round-robin top-level sampling
- TerminalProcessEngine foreground-to-background auto-promotion on timeout
"""

import ast
import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from monika.application.analysis.tools.domain.code_search_tool import sample_across_top_level
from monika.application.analysis.tools.domain.spill_reader_tool import (
    RetrieveSpilledContextInput,
    handle_retrieve_spilled_context,
)
from monika.application.analysis.tools.file_patch_engine import (
    FilePatchEngine,
    apply_search_replace,
    check_file_observation,
    record_file_observation,
)
from monika.application.analysis.tools.kernel.code_execution_rpc import (
    CodeExecutionRpcServer,
    render_tools_sdk_py,
)
from monika.application.analysis.tools.registry import ToolRegistry
from monika.application.analysis.tools.terminal_process_engine import TerminalProcessEngine
from tests.conftest import create_mock_async_session


# ---------------------------------------------------------------------------
# 1. Spill Reader Subsystem Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spill_reader_storage_key_alias_and_line_pagination(tmp_path):
    """Verify storage_key alias and line_offset/line_limit pagination."""
    spill_dir = tmp_path / "spill"
    spill_dir.mkdir(parents=True, exist_ok=True)
    test_file = spill_dir / "test_doc_alpha.txt"

    lines = [f"Line {i}: data entry {i}" for i in range(1, 21)]
    test_file.write_text("\n".join(lines), encoding="utf-8")

    # Verify input model accepts storage_key without blob_id
    model_input = RetrieveSpilledContextInput(storage_key="test_doc_alpha", line_offset=5, line_limit=5)
    assert model_input.storage_key == "test_doc_alpha"
    assert model_input.blob_id is None

    mock_session = create_mock_async_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch("monika.application.analysis.tools.domain.spill_reader_tool.Path") as mock_path:

        def side_effect(p):
            if "spill" in str(p):
                return spill_dir
            return Path(p)

        mock_path.side_effect = side_effect

        res = await handle_retrieve_spilled_context(
            {"storage_key": "test_doc_alpha", "line_offset": 5, "line_limit": 5},
            session=mock_session,
        )

        assert res["success"] is True
        assert res["line_offset"] == 5
        assert res["returned_lines"] == 5
        assert res["total_lines"] == 20
        assert res["has_more"] is True
        assert res["next_line_offset"] == 10
        assert "Line 6" in res["content"]


@pytest.mark.asyncio
async def test_spill_reader_grep_pattern(tmp_path):
    """Verify regex and substring grep filtering with surrounding context."""
    spill_dir = tmp_path / "tool_spill"
    spill_dir.mkdir(parents=True, exist_ok=True)
    test_file = spill_dir / "market_intel_99.txt"

    content = (
        "header information\n"
        "intro line 1\n"
        "intro line 2\n"
        "CRITICAL ALERT: EURUSD liquidity shock detected\n"
        "post-alert line 1\n"
        "post-alert line 2\n"
        "footer line\n"
    )
    test_file.write_text(content, encoding="utf-8")

    mock_session = create_mock_async_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch("monika.application.analysis.tools.domain.spill_reader_tool.Path") as mock_path:

        def side_effect(p):
            if "tool_spill" in str(p):
                return spill_dir
            return Path(p)

        mock_path.side_effect = side_effect

        res = await handle_retrieve_spilled_context(
            {"blob_id": "market_intel_99", "grep_pattern": r"liquidity shock"},
            session=mock_session,
        )

        assert res["success"] is True
        assert res["match_count"] == 1
        assert res["grep_pattern"] == r"liquidity shock"
        assert ">" in res["content"]
        assert "CRITICAL ALERT" in res["content"]
        assert "intro line 2" in res["content"]  # Surrounding context


@pytest.mark.asyncio
async def test_spill_reader_full_path_normalization(tmp_path):
    """Verify passing full path like 'data/tool_spill/item_123.json' resolves correctly."""
    spill_dir = tmp_path / "data" / "tool_spill"
    spill_dir.mkdir(parents=True, exist_ok=True)
    target_file = spill_dir / "item_123.json"
    target_file.write_text('{"status": "ok", "spilled": true}', encoding="utf-8")

    mock_session = create_mock_async_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch("monika.application.analysis.tools.domain.spill_reader_tool.Path") as mock_path:

        def side_effect(p):
            p_str = str(p).replace("\\", "/")
            if p_str in ("data/tool_spill", "data/tool_spill/"):
                return spill_dir
            if p_str == "data/tool_spill/item_123.json":
                return target_file
            return Path(p)

        mock_path.side_effect = side_effect

        res = await handle_retrieve_spilled_context(
            {"blob_id": "data/tool_spill/item_123.json", "offset": 0, "max_chars": 100},
            session=mock_session,
        )

        assert res["success"] is True
        assert '{"status": "ok"' in res["content"]


# ---------------------------------------------------------------------------
# 2. ToolRegistry Concurrency & CodeExecutionRpcServer Tests
# ---------------------------------------------------------------------------


def test_tool_registry_concurrency_safe():
    """Verify ToolRegistry.is_tool_concurrency_safe defaults and fail-closed safety."""
    assert ToolRegistry.is_tool_concurrency_safe("get_market_quote") is True
    assert ToolRegistry.is_tool_concurrency_safe("read_file") is True
    assert ToolRegistry.is_tool_concurrency_safe("search_files") is True
    assert ToolRegistry.is_tool_concurrency_safe("calculate_position_size") is True
    assert ToolRegistry.is_tool_concurrency_safe("retrieve_spilled_context") is True

    # Mutating tools must fail closed to False
    assert ToolRegistry.is_tool_concurrency_safe("execute_order") is False
    assert ToolRegistry.is_tool_concurrency_safe("modify_position") is False
    assert ToolRegistry.is_tool_concurrency_safe("close_position") is False
    assert ToolRegistry.is_tool_concurrency_safe("patch") is False
    assert ToolRegistry.is_tool_concurrency_safe("write_file") is False
    assert ToolRegistry.is_tool_concurrency_safe("run_terminal") is False
    assert ToolRegistry.is_tool_concurrency_safe("submit_asset_analysis") is False


def test_code_execution_rpc_parallel_connections():
    """Verify CodeExecutionRpcServer handles concurrent requests across threads."""
    called_tools = []

    def mock_dispatch(tool_name: str, args: dict) -> str:
        called_tools.append((tool_name, args))
        time.sleep(0.02)  # Tiny simulated latency
        return json.dumps({"status": "success", "tool": tool_name})

    server = CodeExecutionRpcServer(
        allowed_tools={"get_market_quote", "get_timesfm_forecast"},
        dispatch_fn=mock_dispatch,
        max_tool_calls=50,
    )
    port = server.start()
    token = server.rpc_token

    def send_rpc(tool: str, symbol: str) -> dict:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", port))
        payload = {"token": token, "tool": tool, "args": {"symbol": symbol}}
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        data = sock.recv(4096).decode("utf-8")
        sock.close()
        return json.loads(data.strip())

    try:
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(send_rpc, "get_market_quote", f"SYM_{i}") for i in range(5)]
            results = [f.result(timeout=5.0) for f in futures]

        assert len(results) == 5
        for r in results:
            assert r.get("status") == "success"
        assert len(called_tools) == 5
    finally:
        server.stop()


def test_render_tools_sdk_py():
    """Verify render_tools_sdk_py produces valid, parseable Python TypedDict and Protocol stubs."""
    schemas = [
        {
            "name": "get_market_quote",
            "description": "Fetch live market quote for a financial symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol (e.g. EURUSD)."},
                    "include_depth": {"type": "boolean", "description": "Whether to include order book depth."},
                },
                "required": ["symbol"],
            },
        },
        {
            "name": "calculate_position_size",
            "description": "Compute verified position size from risk percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "risk_pct": {"type": "number"},
                },
                "required": ["symbol"],
            },
        },
    ]

    sdk_code = render_tools_sdk_py(schemas)
    assert "class GetMarketQuoteArgs(TypedDict" in sdk_code
    assert "class CalculatePositionSizeArgs(TypedDict" in sdk_code
    assert "class Tools(Protocol):" in sdk_code
    assert "def get_market_quote(" in sdk_code

    # Verify generated Python code compiles cleanly with ast.parse
    parsed_ast = ast.parse(sdk_code)
    assert parsed_ast is not None


# ---------------------------------------------------------------------------
# 3. FilePatchEngine Fuzzy Matching & CAS Observation Tests
# ---------------------------------------------------------------------------


def test_apply_search_replace_exact_and_fuzzy():
    """Verify apply_search_replace handles CRLF/LF normalization, smart quotes, and returns diff."""
    # Test 1: Exact match
    text1 = "line 1\nline 2 target\nline 3"
    res1 = apply_search_replace(text1, "line 2 target", "line 2 replaced", file_path="test.py")
    assert res1["success"] is True
    assert res1["match_type"] == "exact"
    assert "line 2 replaced" in res1["patched_text"]
    assert "-line 2 target" in res1["diff_preview"]
    assert "+line 2 replaced" in res1["diff_preview"]

    # Test 2: Smart quotes normalization
    text2 = 'msg = "hello world"\nval = 42'
    # search block with smart quotes: “hello world”
    search_smart = "msg = “hello world”"
    res2 = apply_search_replace(text2, search_smart, 'msg = "bye world"', file_path="test.py")
    assert res2["success"] is True
    assert res2["match_type"] == "fuzzy"
    assert 'msg = "bye world"' in res2["patched_text"]

    # Test 3: Trailing whitespace tolerance
    text3 = "def calculate():   \n    return 100   \n"
    search3 = "def calculate():\n    return 100"
    res3 = apply_search_replace(text3, search3, "def calculate():\n    return 200", file_path="test.py")
    assert res3["success"] is True
    assert "return 200" in res3["patched_text"]


def test_file_observation_cas_detection(tmp_path):
    """Verify ObservedStateGate detects external modifications on disk."""
    fpath = tmp_path / "cas_test.txt"
    fpath.write_text("initial content", encoding="utf-8")

    # Record observation
    record_file_observation(str(fpath))

    # Clean check
    ok, err = check_file_observation(str(fpath), require_prior_read=True)
    assert ok is True
    assert err is None

    # Modify file externally with different size/content
    time.sleep(0.01)
    fpath.write_text("initial content updated externally!", encoding="utf-8")

    # CAS check should detect stale observation
    stale_ok, stale_err = check_file_observation(str(fpath), require_prior_read=True)
    assert stale_ok is False
    assert "modified externally" in stale_err


# ---------------------------------------------------------------------------
# 4. CodeSearchTool Round-Robin Directory Sampling Tests
# ---------------------------------------------------------------------------


def test_sample_across_top_level_round_robin():
    """Verify sample_across_top_level samples fairly across directories rather than one dense directory."""
    matches = [
        {"file": "src/analysis/a.py", "line_number": 10},
        {"file": "src/analysis/b.py", "line_number": 20},
        {"file": "src/analysis/c.py", "line_number": 30},
        {"file": "src/analysis/d.py", "line_number": 40},
        {"file": "tests/test_a.py", "line_number": 5},
        {"file": "tests/test_b.py", "line_number": 15},
        {"file": "docs/readme.md", "line_number": 1},
    ]

    sampled = sample_across_top_level(matches, limit=4)
    assert len(sampled) == 4

    top_levels = [m["file"].split("/")[0] for m in sampled]
    # Round-robin should draw: 1st from src, 1st from tests, 1st from docs, then 2nd from src
    assert top_levels == ["src", "tests", "docs", "src"]


# ---------------------------------------------------------------------------
# 5. TerminalProcessEngine Timeout Promotion Tests
# ---------------------------------------------------------------------------


def test_terminal_timeout_promotion(tmp_path):
    """Verify foreground command auto-promotes to background on timeout when promote_on_timeout=True."""
    engine = TerminalProcessEngine(checkpoint_path=str(tmp_path / "proc.json"))

    # Command that sleeps longer than timeout
    import sys

    cmd = "Start-Sleep -Seconds 10" if sys.platform == "win32" else "sleep 10"

    # With promote_on_timeout=True:
    res = engine.execute(cmd, timeout=1, promote_on_timeout=True)
    try:
        assert res["timed_out"] is True
        assert res["status"] == "promoted_to_background"
        assert "pid" in res
        assert "session_id" in res
    finally:
        if "session_id" in res:
            engine.kill_process(res["session_id"])
