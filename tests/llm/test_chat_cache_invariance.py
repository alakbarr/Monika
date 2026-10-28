import pytest
from unittest.mock import AsyncMock, MagicMock
from monika.infrastructure.providers.openai_provider import OpenAIProvider
from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager
from monika.application.agent.chat_compaction import ChatMicroCompactor


@pytest.mark.asyncio
async def test_context_snapshot_placed_only_in_last_user_message():
    """Verify OpenAIProvider attaches <context_snapshot> ONLY to the last user message, leaving historical user turns unmodified."""
    provider = OpenAIProvider(model="gpt-4o", api_key="sk-test-fake")
    provider.client = MagicMock()
    captured_kwargs = {}

    async def mock_create(kwargs):
        captured_kwargs.update(kwargs)
        mock_choice = MagicMock()
        mock_choice.message = MagicMock()
        mock_choice.message.role = "assistant"
        mock_choice.message.content = "OK"
        mock_choice.message.tool_calls = None
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        return mock_resp

    provider._create_chat_completion = mock_create

    system_prompt = ("Static System Prefix", "Current Time: 10:15 UTC | Equity: 10000")
    messages = [
        {"role": "user", "content": "Turn 0 User: Halo"},
        {"role": "assistant", "content": "Turn 0 Assistant: Halo, ada yang bisa dibantu?"},
        {"role": "user", "content": "Turn 1 User: Cek posisi"},
        {"role": "assistant", "content": "Turn 1 Assistant: Tidak ada posisi terbuka."},
        {"role": "user", "content": "Turn 2 User: Analisis XAUUSD"},
    ]

    await provider.run_tool_agent(messages=messages, tools=[], system_prompt=system_prompt)

    sent_messages = captured_kwargs.get("messages", [])
    # System message is at index 0
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[0]["content"] == "Static System Prefix"

    # Message 1 is Turn 0 user message — MUST NOT contain <context_snapshot>
    user_0 = sent_messages[1]
    assert user_0["role"] == "user"
    assert user_0["content"] == "Turn 0 User: Halo"
    assert "<context_snapshot>" not in user_0["content"]

    # Message 3 is Turn 1 user message — MUST NOT contain <context_snapshot>
    user_1 = sent_messages[3]
    assert user_1["role"] == "user"
    assert user_1["content"] == "Turn 1 User: Cek posisi"
    assert "<context_snapshot>" not in user_1["content"]

    # Message 5 is Turn 2 user message (last user message) — MUST contain <context_snapshot>
    user_2 = sent_messages[5]
    assert user_2["role"] == "user"
    assert "Turn 2 User: Analisis XAUUSD" in user_2["content"]
    assert "<context_snapshot>" in user_2["content"]
    assert "Current Time: 10:15 UTC" in user_2["content"]


@pytest.mark.asyncio
async def test_multi_turn_history_never_mutated_across_turns():
    """Simulate a 3-turn conversation and assert historical messages (Turn 0, Turn 1) are byte-identical across turns."""
    provider = OpenAIProvider(model="gpt-4o", api_key="sk-test-fake")
    provider.client = MagicMock()
    all_sent_messages = []

    async def mock_create(kwargs):
        all_sent_messages.append([dict(m) for m in kwargs["messages"]])
        mock_choice = MagicMock()
        mock_choice.message = MagicMock()
        mock_choice.message.role = "assistant"
        mock_choice.message.content = "OK"
        mock_choice.message.tool_calls = None
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        return mock_resp

    provider._create_chat_completion = mock_create

    # Turn 0
    t0_sys = ("Static System", "Dynamic Snapshot Turn 0")
    t0_messages = [{"role": "user", "content": "Halo Turn 0"}]
    await provider.run_tool_agent(messages=t0_messages, tools=[], system_prompt=t0_sys)

    # Turn 1
    t1_sys = ("Static System", "Dynamic Snapshot Turn 1")
    t1_messages = [
        {"role": "user", "content": "Halo Turn 0"},
        {"role": "assistant", "content": "Reply Turn 0"},
        {"role": "user", "content": "Status Turn 1"},
    ]
    await provider.run_tool_agent(messages=t1_messages, tools=[], system_prompt=t1_sys)

    # Turn 2
    t2_sys = ("Static System", "Dynamic Snapshot Turn 2")
    t2_messages = [
        {"role": "user", "content": "Halo Turn 0"},
        {"role": "assistant", "content": "Reply Turn 0"},
        {"role": "user", "content": "Status Turn 1"},
        {"role": "assistant", "content": "Reply Turn 1"},
        {"role": "user", "content": "Query Turn 2"},
    ]
    await provider.run_tool_agent(messages=t2_messages, tools=[], system_prompt=t2_sys)

    assert len(all_sent_messages) == 3

    # In Turn 1 and Turn 2, Turn 0's user message must remain clean and byte-identical!
    turn1_msgs = all_sent_messages[1]
    turn2_msgs = all_sent_messages[2]

    # Both Turn 1 and Turn 2 should have identical Turn 0 user message (index 1 after system)
    assert turn1_msgs[1]["content"] == "Halo Turn 0"
    assert turn2_msgs[1]["content"] == "Halo Turn 0"
    assert "<context_snapshot>" not in turn1_msgs[1]["content"]
    assert "<context_snapshot>" not in turn2_msgs[1]["content"]

    # Turn 1 user message in Turn 2 (index 3) must also be clean and byte-identical!
    assert turn2_msgs[3]["content"] == "Status Turn 1"
    assert "<context_snapshot>" not in turn2_msgs[3]["content"]


def test_tier_tools_stable_and_sorted_across_turns():
    """Assert canonical static tool lists for Lite, Medium, Deep tiers are sorted by name and preserve permission boundaries."""
    from monika.application.agent.chat.tiers import (
        TIER_LITE_TOOLS,
        TIER_MEDIUM_TOOLS,
        TIER_DEEP_TOOLS,
    )

    # All tiers must have tools sorted by name
    lite_names = [t["name"] for t in TIER_LITE_TOOLS]
    medium_names = [t["name"] for t in TIER_MEDIUM_TOOLS]
    deep_names = [t["name"] for t in TIER_DEEP_TOOLS]

    assert lite_names == sorted(lite_names), "Lite tier tools must be sorted alphabetically by name"
    assert medium_names == sorted(medium_names), "Medium tier tools must be sorted alphabetically by name"
    assert deep_names == sorted(deep_names), "Deep tier tools must be sorted alphabetically by name"

    # Size constraints
    assert 5 <= len(TIER_LITE_TOOLS) <= 8, f"Lite tier should have ~6 tools, got {len(TIER_LITE_TOOLS)}"
    assert 15 <= len(TIER_MEDIUM_TOOLS) <= 22, f"Medium tier should have ~18 tools, got {len(TIER_MEDIUM_TOOLS)}"
    assert 30 <= len(TIER_DEEP_TOOLS) <= 45, f"Deep tier should have ~35 tools, got {len(TIER_DEEP_TOOLS)}"

    # Permission containment: Lite and Medium MUST NOT have mutation or execution tools
    assert "propose_action" not in lite_names
    assert "propose_action" not in medium_names
    assert "propose_action" in deep_names

    assert "execute_analysis_code" not in lite_names
    assert "execute_analysis_code" not in medium_names

    # Informational tools are in Lite
    assert "get_account_info" in lite_names
    assert "get_system_health" in lite_names


def test_tier_lite_system_prompt_exceeds_cache_threshold():
    """Assert Lite tier system prompt exceeds the minimum cache threshold when padded."""
    from monika.application.agent.chat.prompt_builder import PromptBuilderMixin

    class DummyChat(PromptBuilderMixin):
        def __init__(self):
            self.settings = {}

    chat = DummyChat()
    lean_sys = chat._build_lean_system_prompt()
    padded_sys = CacheBreakpointManager.pad_system_prompt_to_threshold(lean_sys, task_role="chat_telegram", force=True)

    # Must exceed 4,096 chars (Gemini threshold) and 1,024 tokens
    assert len(padded_sys) >= 4096, f"Padded system prompt is {len(padded_sys)} chars, expected >= 4096"
    assert "You are Monika" in padded_sys


@pytest.mark.asyncio
async def test_run_tier_lite_invokes_padded_system_prompt():
    """Verify ExecutionTiersMixin._run_tier_lite passes padded system prompt to client."""
    from monika.application.agent.chat.tiers import ExecutionTiersMixin
    from monika.application.agent.chat.prompt_builder import PromptBuilderMixin

    class DummyAgent(ExecutionTiersMixin, PromptBuilderMixin):
        def __init__(self):
            self.settings = {}
            self._client_lite = MagicMock()
            self._client_lite.run_chat_loop = AsyncMock(return_value={"reply": "OK"})

    agent = DummyAgent()
    await agent._run_tier_lite(system_prompt="sys", history=[], message="Halo")

    assert agent._client_lite.run_chat_loop.called
    call_kwargs = agent._client_lite.run_chat_loop.call_args.kwargs
    sys_prompt = call_kwargs["system_prompt"]
    assert len(sys_prompt) >= 4096
    assert "=== ROLE DIRECTIVE ===" in sys_prompt


def test_chat_micro_compactor_append_only():
    """Verify ChatMicroCompactor does NOT mutate earlier assistant turns in-place (Option A)."""
    compactor = ChatMicroCompactor(max_history_tokens=100)

    messages = [
        {"role": "user", "content": "What is the price of EURUSD?"},
        {"role": "assistant", "content": "EURUSD is at 1.0850. " + "Detailed technical analysis... " * 50},
        {"role": "user", "content": "Please explain the RSI setup."},
        {"role": "assistant", "content": "RSI is currently oversold at 28.5. " + "Further breakdown... " * 50},
        {"role": "user", "content": "Should I enter now?"},
        {"role": "assistant", "content": "Yes, enter with tight SL at 1.0820."},
    ]

    compacted = compactor.compact_history(messages)

    # In Option A: Historical messages messages[0..5] must remain 100% byte-identical
    for i in range(len(messages)):
        assert compacted[i]["content"] == messages[i]["content"], (
            f"Message {i} ({compacted[i]['role']}) was mutated in-place by compactor! "
            f"Expected: '{messages[i]['content'][:50]}...', Got: '{compacted[i]['content'][:50]}...'"
        )

    # All user messages must be preserved verbatim
    user_msgs = [m for m in compacted if m["role"] == "user"]
    assert len(user_msgs) == 3
    assert user_msgs[0]["content"] == "What is the price of EURUSD?"
    assert user_msgs[1]["content"] == "Please explain the RSI setup."
    assert user_msgs[2]["content"] == "Should I enter now?"
