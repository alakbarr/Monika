"""Unit tests for SessionSurface, cache invariants, and projections."""

from __future__ import annotations

from datetime import UTC, datetime
import pytest

from monika.application.agent.harness.session_surface import (
    RuntimeContextProjection,
    SessionSurface,
    SystemPromptProjection,
    ThrottledTimeContext,
    deep_freeze_message,
)


def test_deep_freeze_message_isolation() -> None:
    original = {"role": "user", "content": "hello", "meta": {"k": "v"}}
    frozen = deep_freeze_message(original)

    # Mutating original does not affect frozen
    original["content"] = "mutated"
    original["meta"]["k"] = "changed"
    assert frozen["content"] == "hello"
    assert frozen["meta"]["k"] == "v"


def test_append_surface_vs_non_surface_events() -> None:
    surface = SessionSurface()

    # Append surface events
    ev1 = surface.append_event("system/message", message={"role": "system", "content": "sys prompt"})
    ev2 = surface.append_event("user/message", message={"role": "user", "content": "user query"})

    assert surface.nodes == [ev1.seq, ev2.seq]
    assert len(surface.log) == 2

    # Append non-surface events
    ev3 = surface.append_event("assistant/attempt", message={"role": "assistant", "content": "draft"})
    ev4 = surface.append_event("step/start", metadata={"step": 1})

    assert ev3.surface_op is None
    assert ev4.surface_op is None
    # Nodes remain strictly unchanged by non-surface events
    assert surface.nodes == [ev1.seq, ev2.seq]
    assert len(surface.log) == 4


def test_derive_messages_and_cache_invariants() -> None:
    surface = SessionSurface()
    surface.append_event("system/message", message={"role": "system", "content": "system 1"})
    surface.append_event("user/message", message={"role": "user", "content": "user 1"})

    # derive without system
    msgs = surface.derive_messages(include_system=False)
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "user 1"

    # derive with system
    msgs_sys = surface.derive_messages(include_system=True)
    assert len(msgs_sys) == 2
    assert msgs_sys[0]["role"] == "system"

    # Caller mutation does not pollute cache
    msgs_sys[0]["content"] = "HACKED"
    fresh_msgs = surface.derive_messages(include_system=True)
    assert fresh_msgs[0]["content"] == "system 1"

    # Incremental derivation: append new node
    surface.append_event("assistant/message", message={"role": "assistant", "content": "assistant 1"})
    # content_generation hasn't changed
    assert surface.content_generation == 0
    msgs_after = surface.derive_messages(include_system=False)
    assert len(msgs_after) == 2
    assert msgs_after[1]["content"] == "assistant 1"


def test_assert_system_head_rewrite_enforcement() -> None:
    surface = SessionSurface()
    ev_sys = surface.append_event("system/message", message={"role": "system", "content": "sys 1"})
    ev_user = surface.append_event("user/message", message={"role": "user", "content": "user 1"})

    # Compaction (user/message) cannot replace node 0
    with pytest.raises(ValueError, match="cannot be replaced by 'user/message'"):
        surface.append_event(
            "user/message",
            message={"role": "user", "content": "summary"},
            surface_op={"op": "replace", "start_seq": ev_sys.seq, "end_seq": ev_user.seq},
        )

    # Multi-node replace covering node 0 with system/message is rejected (must be singleton)
    with pytest.raises(ValueError, match="must replace node 0 alone"):
        surface.append_event(
            "system/message",
            message={"role": "system", "content": "new sys"},
            surface_op={"op": "replace", "start_seq": ev_sys.seq, "end_seq": ev_user.seq},
        )

    # Valid replacement of node 0 alone
    ev_new_sys = surface.append_event(
        "system/message",
        message={"role": "system", "content": "new sys"},
        surface_op={"op": "replace", "start_seq": ev_sys.seq, "end_seq": ev_sys.seq},
    )
    assert surface.nodes == [ev_new_sys.seq, ev_user.seq]
    assert surface.replace_generation == 1
    assert surface.content_generation == 1


def test_assert_tool_result_rewrite_enforcement() -> None:
    surface = SessionSurface()
    ev_user = surface.append_event("user/message", message={"role": "user", "content": "do tool"})
    ev_tool1 = surface.append_event("tool/result", message={"role": "tool", "content": "res1"})
    ev_tool2 = surface.append_event("tool/result", message={"role": "tool", "content": "res2"})

    # Tool result replace spanning multiple nodes raises
    with pytest.raises(ValueError, match="target a single node"):
        surface.append_event(
            "tool/result",
            message={"role": "tool", "content": "compacted"},
            surface_op={"op": "replace", "start_seq": ev_tool1.seq, "end_seq": ev_tool2.seq},
        )

    # Tool result replace targeting non-tool/result node raises
    with pytest.raises(ValueError, match="cannot replace a node of type 'user/message'"):
        surface.append_event(
            "tool/result",
            message={"role": "tool", "content": "compacted"},
            surface_op={"op": "replace", "start_seq": ev_user.seq, "end_seq": ev_user.seq},
        )

    # Valid tool result rewrite
    ev_tool1_rewrite = surface.append_event(
        "tool/result",
        message={"role": "tool", "content": "spilled_ref"},
        surface_op={"op": "replace", "start_seq": ev_tool1.seq, "end_seq": ev_tool1.seq},
    )
    assert surface.nodes == [ev_user.seq, ev_tool1_rewrite.seq, ev_tool2.seq]
    assert surface.replace_generation == 1


def test_system_prompt_projection_policy() -> None:
    surface = SessionSurface()
    proj = SystemPromptProjection(surface, starts_series=False, in_history=True)

    # Initial prompt creates node 0
    proj.update_system_prompt("Initial System Prompt")
    assert len(surface.nodes) == 1
    assert surface.get_event(surface.nodes[0]) is not None

    # Mid-session prompt update with in_history=True and not starts_series appends at tail
    surface.append_event("user/message", message={"role": "user", "content": "hello"})
    proj.update_system_prompt("Updated System Prompt")
    assert len(surface.nodes) == 3
    ev_tail = surface.get_event(surface.nodes[2])
    assert ev_tail is not None
    assert ev_tail.event_type == "system/message"
    assert ev_tail.message == {"role": "system", "content": "Updated System Prompt"}

    # With starts_series=True, it replaces node 0
    proj_series = SystemPromptProjection(surface, starts_series=True, in_history=True)
    proj_series.update_system_prompt("Series Start Prompt")
    ev_head = surface.get_event(surface.nodes[0])
    assert ev_head is not None
    assert ev_head.message == {"role": "system", "content": "Series Start Prompt"}


def test_runtime_context_projection() -> None:
    proj = RuntimeContextProjection()

    # Empty sections return None
    assert proj.project({}) is None
    assert proj.project({"empty": "   "}) is None

    # Initial projection emits user message
    res1 = proj.project({"cwd": "/app", "goal": "win"})
    assert res1 is not None
    assert res1["role"] == "user"
    assert '<system-reminder type="runtime-context">' in res1["content"]
    assert "<cwd>\n/app\n</cwd>" in res1["content"]
    assert "<goal>\nwin\n</goal>" in res1["content"]

    # Identical content returns None (0 tokens emitted)
    assert proj.project({"cwd": "/app", "goal": "win"}) is None

    # Modified content emits new message
    res2 = proj.project({"cwd": "/app", "goal": "win more"})
    assert res2 is not None
    assert "<goal>\nwin more\n</goal>" in res2["content"]

    # Reset on compaction clears digest
    proj.reset_on_compaction(replace_generation=1)
    res3 = proj.project({"cwd": "/app", "goal": "win more"})
    assert res3 is not None


def test_throttled_time_context() -> None:
    time_ctx = ThrottledTimeContext(refresh_interval_seconds=600.0)

    # Initial projection
    t0 = 1000.0
    msg1 = time_ctx.project(now_ts=t0)
    assert msg1 is not None
    assert "Current time:" in msg1["content"]

    # Projection within 10 minutes returns None
    t1 = t0 + 300.0
    assert time_ctx.project(now_ts=t1) is None

    # Projection after 10 minutes returns new snapshot
    t2 = t0 + 601.0
    msg2 = time_ctx.project(now_ts=t2, as_of_iso="2026-10-26T00:10:01Z")
    assert msg2 is not None
    assert "2026-10-26T00:10:01Z" in msg2["content"]
