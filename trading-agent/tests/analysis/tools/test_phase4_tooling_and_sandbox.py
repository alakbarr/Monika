# ==============================================================================
# File: tests/analysis/tools/test_phase4_tooling_and_sandbox.py
# ==============================================================================

"""
Comprehensive Unit Tests for Phase 4:
  1. Code Search Tool (search_files) with directory filtering and windowing
  2. Large-File Wipeout & Empty File Protection in FilePatchEngine
  3. PTY Terminal Escape Query Responder
  4. Worktree Manager Isolation
"""

import os
import tempfile
from pathlib import Path
import pytest

from analysis.tools.domain.code_search_tool import CodeSearchEngine, CodeSearchInput, handle_search_files
from analysis.tools.file_patch_engine import FilePatchEngine
from analysis.tools.environments.pty_query_responder import PtyQueryResponder
from utils.infra.worktree_manager import WorktreeManager


# ==============================================================================
# 1. Code Search Tool Tests
# ==============================================================================

def test_code_search_engine_basic_and_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        # Create test files
        f1 = tmp / "sample.py"
        f1.write_text(
            "import os\n"
            "def calculate_alpha():\n"
            "    value = 42\n"
            "    return value\n",
            encoding="utf-8",
        )
        f2 = tmp / "ignored.bin"
        f2.write_bytes(b"\x00\x01\x02binarydata")

        # Run search
        matches = CodeSearchEngine.search(
            pattern="calculate_alpha",
            base_path=str(tmp),
            max_results=10,
            context_lines=1,
            is_regex=False,
        )

        assert len(matches) == 1
        m = matches[0]
        assert "sample.py" in m["file"]
        assert m["line_number"] == 2
        assert "calculate_alpha" in m["line_content"]
        assert "import os" in m["snippet"]
        assert "value = 42" in m["snippet"]


@pytest.mark.asyncio
async def test_handle_search_files_tool_invocation():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "test.txt").write_text("Monika Institutional Agent\nVersion 1.0.0\n", encoding="utf-8")

        params = CodeSearchInput(
            pattern="Monika Institutional",
            path=str(tmp),
            max_results=5,
        )
        res = await handle_search_files(params)
        assert "[SEARCH RESULTS]" in res
        assert "Found 1 matches" in res
        assert "test.txt" in res


# ==============================================================================
# 2. File Patch Engine Wipeout Protection
# ==============================================================================

def test_file_patch_engine_empty_and_large_file_protection():
    engine = FilePatchEngine()

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tf:
        fpath = tf.name

    try:
        # Rule 10: Empty write must be rejected
        ok, msg = engine.write_file(fpath, "")
        assert ok is False
        assert "0 bytes" in msg

        # Write initial file with 150 lines
        lines_150 = "\n".join([f"# Line {i}: comment" for i in range(1, 151)]) + "\n"
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(lines_150)

        # Mark read in guard so stale guard allows inspection
        engine.guard.record_read(fpath)

        # Attempt to overwrite entire 150-line file without allow_overwrite
        ok_wipe, msg_wipe = engine.write_file(fpath, "print('short replacement')\n", allow_overwrite=False)
        assert ok_wipe is False
        assert "large" in msg_wipe.lower()
        assert "allow_overwrite" in msg_wipe

        # Successful overwrite when allow_overwrite=True
        ok_perm, msg_perm = engine.write_file(fpath, "print('permitted overwrite')\n", allow_overwrite=True)
        assert ok_perm is True
        assert "Successfully wrote" in msg_perm
    finally:
        if os.path.exists(fpath):
            os.remove(fpath)


# ==============================================================================
# 3. PTY Terminal Escape Query Responder
# ==============================================================================

def test_pty_query_responder():
    responder = PtyQueryResponder()

    # 1. Cursor Position Query (ESC [ 6 n)
    stream_chunk_cursor = b"Processing...\x1b[6n"
    responses = responder.process_output(stream_chunk_cursor)
    assert len(responses) == 1
    assert responses[0] == b"\x1b[1;1R"

    # 2. Primary Device Attributes (ESC [ c)
    stream_chunk_da = b"\x1b[c"
    responses_da = responder.process_output(stream_chunk_da)
    assert len(responses_da) == 1
    assert responses_da[0] == b"\x1b[?1;2c"

    # 3. Secondary Device Attributes (ESC [ > c)
    stream_chunk_sda = b"\x1b[>c"
    responses_sda = responder.process_output(stream_chunk_sda)
    assert len(responses_sda) == 1
    assert responses_sda[0] == b"\x1b[>0;10;0c"

    # 4. Standard clean output without queries produces no synthetic response
    responses_clean = responder.process_output(b"Normal terminal output\r\nDone.\r\n")
    assert len(responses_clean) == 0


# ==============================================================================
# 4. Worktree Manager
# ==============================================================================

def test_worktree_manager_query():
    wm = WorktreeManager()
    assert wm.is_git_repo() is True
    trees = wm.list_worktrees()
    assert len(trees) >= 1
    assert any("Monika" in t.get("path", "") for t in trees)
