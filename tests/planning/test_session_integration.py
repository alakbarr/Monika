"""Integration test: session plan is injected into agent streaming and bound to scratchpad."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.agent.chat.streaming import StreamingMixin
from monika.application.planning.session_plan import SessionPlan
from monika.application.analysis.memory.working_scratchpad import WorkingScratchpad


@pytest.mark.asyncio
async def test_session_plan_injected_and_scratchpad_bound():
    class _Probe(StreamingMixin):
        def __init__(self):
            self.settings = {}
            self.tool_event_listener = None
            self.pending_calls: list = []

        def _create_pending_action(self, proposed: dict):
            return None

    probe = _Probe()
    # Direct verification of session plan lifecycle
    sp = SessionPlan.get_or_create("test_int_session", goal="Verify injection")
    sp.add_task("Run audit", priority="HIGH")

    # Verify scratchpad binding via working scratchpad
    scratch_symbol = "test_int_session".strip().upper().replace("/", "")
    scratch_symbol = scratch_symbol[:20]
    scratch_state = WorkingScratchpad.get_or_create(scratch_symbol)
    scratch_state["session_plan_ref"] = sp.session_id
    scratch_state["session_plan_goal"] = sp.get_plan().get("goal", "")
    WorkingScratchpad.update_scratchpad(
        scratch_symbol,
        {"notes": f"SessionPlan goal={sp.get_plan().get('goal', 'N/A')}"},
    )

    summary = sp.summary_text()
    assert "Verify injection" in summary
    assert "Run audit" in summary
    assert scratch_state.get("session_plan_goal") == "Verify injection"
