# ==============================================================================
# File: tests/analysis/tools/test_phase5_tool_engine_and_patching.py
# ==============================================================================

import os
import sys
import tempfile
import pytest

from analysis.tools.terminal_process_engine import (
    TerminalProcessEngine,
    PtyQueryResponder,
    rewrite_sudo_command,
)
from analysis.tools.file_patch_engine import (
    FilePatchEngine,
    V4APatchParser,
    PatchOperation,
    SyntaxLinter,
)
from analysis.tools.tool_search_engine import ToolSearchEngine


def test_pty_query_responder():
    assert PtyQueryResponder.scan_and_reply("\x1b[6n") == "\x1b[1;1R"
    assert PtyQueryResponder.scan_and_reply("\x1b[c") == "\x1b[?1;0c"
    assert PtyQueryResponder.scan_and_reply("\x1b[0c") == "\x1b[?1;0c"
    assert PtyQueryResponder.scan_and_reply("\x1b[5n") == "\x1b[0n"
    assert PtyQueryResponder.scan_and_reply("plain text output") is None


def test_rewrite_sudo_command():
    cmd = "sudo ls -la"
    rewritten = rewrite_sudo_command(cmd)
    if sys.platform == "win32":
        assert rewritten == "ls -la"
    else:
        assert rewritten in ("ls -la", "sudo ls -la")

    pipe_cmd = "echo hi | sudo tee file.txt"
    rewritten_pipe = rewrite_sudo_command(pipe_cmd)
    if sys.platform == "win32":
        assert "sudo" not in rewritten_pipe


def test_terminal_process_engine_exec_and_kill():
    with tempfile.TemporaryDirectory() as tmpdir:
        chk_file = os.path.join(tmpdir, "proc.json")
        engine = TerminalProcessEngine(checkpoint_path=chk_file)

        # Run quick foreground command
        if sys.platform == "win32":
            res = engine.execute("Write-Output 'hello_monika'", background=False, timeout=10)
        else:
            res = engine.execute("echo 'hello_monika'", background=False, timeout=10)

        assert res["success"] is True
        assert "hello_monika" in res["output"]

        # Run background command and kill it
        if sys.platform == "win32":
            bg_res = engine.execute("Start-Sleep -Seconds 10", background=True)
        else:
            bg_res = engine.execute("sleep 10", background=True)

        assert bg_res["success"] is True
        sid = bg_res["session_id"]

        poll_res = engine.poll_process(sid)
        assert poll_res["success"] is True
        assert poll_res["is_running"] is True

        kill_res = engine.kill_process(sid)
        assert kill_res["success"] is True
        # Verify handle cleanup & subprocess popped
        assert sid not in engine._subprocesses


def test_v4a_patch_parser():
    patch_text = """*** Update File: src/main.py ***
<<<<<<< SEARCH
def hello():
    pass
=======
def hello():
    return "monika"
>>>>>>> REPLACE

*** Add File: src/new_module.py ***
print("new")

*** Delete File: src/obsolete.py ***

*** Move File: src/a.py -> src/b.py ***
"""
    ops = V4APatchParser.parse(patch_text)
    assert len(ops) == 4

    assert ops[0].action == "UPDATE"
    assert ops[0].path == "src/main.py"
    assert "def hello():" in ops[0].search_content
    assert "monika" in ops[0].replace_content

    assert ops[1].action == "ADD"
    assert ops[1].path == "src/new_module.py"
    assert "print(\"new\")" in ops[1].new_file_content

    assert ops[2].action == "DELETE"
    assert ops[2].path == "src/obsolete.py"

    assert ops[3].action == "MOVE"
    assert ops[3].path == "src/a.py"
    assert ops[3].new_path == "src/b.py"


def test_file_patch_engine_apply_multi_patch_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        f1 = os.path.join(tmpdir, "main.py")
        with open(f1, "w", encoding="utf-8") as f:
            f.write("def calculate():\n    return 1\n")

        engine = FilePatchEngine()
        # Record read first (stale overwrite guard)
        engine.read_file(f1)

        patch = f"""*** Update File: {f1} ***
<<<<<<< SEARCH
def calculate():
    return 1
=======
def calculate():
    return 100
>>>>>>> REPLACE
"""
        # Test dry-run first
        ok, msg, summaries = engine.apply_multi_patch(patch, dry_run=True)
        assert ok is True
        assert "Dry-run passed" in msg

        # Real apply
        ok_apply, msg_apply, summaries_apply = engine.apply_multi_patch(patch, dry_run=False)
        assert ok_apply is True
        assert "Successfully committed" in msg_apply

        with open(f1, "r", encoding="utf-8") as f:
            content = f.read()
        assert "return 100" in content


def test_file_patch_engine_multi_patch_lint_failure_aborts_dry_run():
    with tempfile.TemporaryDirectory() as tmpdir:
        f1 = os.path.join(tmpdir, "syntax_target.py")
        original_code = "def valid_code():\n    return True\n"
        with open(f1, "w", encoding="utf-8") as f:
            f.write(original_code)

        engine = FilePatchEngine()
        engine.read_file(f1)

        # Introduce broken syntax
        broken_patch = f"""*** Update File: {f1} ***
<<<<<<< SEARCH
def valid_code():
    return True
=======
def broken_syntax(
    return "missing parenthesis"
>>>>>>> REPLACE
"""
        ok, msg, _ = engine.apply_multi_patch(broken_patch, dry_run=False)
        assert ok is False
        assert "syntax error" in msg.lower()

        # Verify disk was NOT modified (atomic failure)
        with open(f1, "r", encoding="utf-8") as f:
            current_code = f.read()
        assert current_code == original_code


def test_tool_search_engine_progressive_materialization():
    engine = ToolSearchEngine(token_budget=2000)
    engine.register_tool(
        name="crypto_arbitrage_scanner",
        description="Scans cross-exchange orderbook spreads for riskless arbitrage.",
        parameters={"type": "object", "properties": {"pair": {"type": "string"}}},
        category="TRADING",
        is_pinned=False,
    )
    engine.register_tool(
        name="web_search_duckduckgo",
        description="Searches live web for breaking financial headlines.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        category="SEARCH",
        is_pinned=False,
    )

    # Initially neither is active
    assert "crypto_arbitrage_scanner" not in engine._active_tools
    assert "web_search_duckduckgo" not in engine._active_tools

    # Materialize for query
    activated = engine.materialize_tools_for_query("need to scan arbitrage spreads across pairs")
    assert "crypto_arbitrage_scanner" in activated
    assert "crypto_arbitrage_scanner" in engine._active_tools

    # Test progressive execution
    executed_record = []
    def dummy_executor(tname, args):
        executed_record.append((tname, args))
        return {"status": "ok"}

    res = engine.execute_progressive_tool("web_search_duckduckgo", {"query": "fed interest rate"}, executor=dummy_executor)
    assert res == {"status": "ok"}
    assert "web_search_duckduckgo" in engine._active_tools
    assert len(executed_record) == 1
