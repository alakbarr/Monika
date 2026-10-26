"""Unit tests for creation-time output spill store and spill policy."""

from __future__ import annotations

from pathlib import Path

from monika.application.agent.harness.spill_store import (
    SpillPolicy,
    SpillStore,
    encode_safe_segment,
)


def test_encode_safe_segment_traversal_immunity() -> None:
    # Single and double dot must be encoded
    assert encode_safe_segment(".") == "~002E"
    assert encode_safe_segment("..") == "~002E~002E"

    # Tilde must be encoded
    assert encode_safe_segment("~") == "~007E"
    assert encode_safe_segment("~admin") == "~007Eadmin"

    # Path delimiters, colons, NUL must be encoded
    assert encode_safe_segment("foo/bar") == "foo~002Fbar"
    assert encode_safe_segment("foo\\bar") == "foo~005Cbar"
    assert encode_safe_segment("C:data") == "C~003Adata"
    assert encode_safe_segment("nul\x00byte") == "nul~0000byte"

    # Standard alphanumeric, underscores, hyphens, and internal dots are preserved
    assert encode_safe_segment("valid_tool-name.v1") == "valid_tool-name.v1"


def test_spill_store_save_text(tmp_path: Path) -> None:
    store = SpillStore(root_dir=tmp_path)
    session_id = "test-session-123"
    content = "Hello, world! Full output line 1\nFull output line 2\n"

    spill_ref = store.save_text(session_id=session_id, tool_name="bash_exec", content=content)

    assert Path(spill_ref.locator).exists()
    assert spill_ref.bytes_total == len(content.encode("utf-8"))
    assert spill_ref.omitted_bytes == 0
    assert "bash_exec" in Path(spill_ref.locator).name
    assert "session-" in Path(spill_ref.locator).parent.name

    with open(spill_ref.locator, "r", encoding="utf-8") as f:
        stored_content = f.read()
    assert stored_content == content


def test_spill_policy_exempt_and_small_outputs(tmp_path: Path) -> None:
    store = SpillStore(root_dir=tmp_path)
    policy = SpillPolicy(store=store, max_inline_tokens=100)

    # Output within token budget is not spilled
    small_content = "Small tool output"
    res, ref = policy.apply("sess1", "grep_search", small_content)
    assert res == small_content
    assert ref is None

    # Exempt tools are never spilled regardless of size
    large_content = "X" * 10000
    res_exempt, ref_exempt = policy.apply("sess1", "read_file", large_content)
    assert res_exempt == large_content
    assert ref_exempt is None


def test_spill_policy_large_output_truncation_and_notice(tmp_path: Path) -> None:
    store = SpillStore(root_dir=tmp_path)
    # Threshold of 150 tokens ~ 600 chars (full content is 938 chars)
    policy = SpillPolicy(store=store, max_inline_tokens=150)

    # 1000 characters of identifiable content
    head_marker = "START_OF_HEAD_" + ("A" * 200)
    middle_marker = "MIDDLE_DATA_" + ("B" * 500)
    tail_marker = ("C" * 200) + "_END_OF_TAIL"
    full_content = head_marker + middle_marker + tail_marker

    res, ref = policy.apply("sess_spill", "run_terminal", full_content)

    assert ref is not None
    assert Path(ref.locator).exists()
    with open(ref.locator, "r", encoding="utf-8") as f:
        assert f.read() == full_content

    assert SpillPolicy.GAP in res
    assert "Omitted" in res
    assert ref.locator in res
    assert str(ref.omitted_bytes) in res
    assert ref.omitted_bytes > 0

    # Verify head and tail excerpts are present
    assert "START_OF_HEAD_" in res
    assert "_END_OF_TAIL" in res
    # Middle data should have been omitted
    assert middle_marker not in res
