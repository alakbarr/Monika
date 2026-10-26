import copy
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.infrastructure.llm.context_compaction import (
    ContextCompactionEngine,
    find_tool_pairing_balanced_cut,
    prune_session_tool_results,
    prune_tool_result_text,
)
from monika.infrastructure.llm.rate_limiting.streaming import StreamResult
from monika.infrastructure.providers.anthropic_provider import AnthropicProvider
from monika.infrastructure.providers.base_provider import MockBlock
from monika.infrastructure.providers.deepseek_provider import DeepSeekProvider
from monika.infrastructure.providers.gemini_provider import GeminiProvider, _gemini_stream_parser
from monika.infrastructure.providers.openai_provider import OpenAIProvider


# ---------------------------------------------------------------------------
# 1. GeminiProvider Tests
# ---------------------------------------------------------------------------


def test_gemini_stream_parser_captures_thinking_and_signature():
    """Verify _gemini_stream_parser captures thought text and thoughtSignature."""
    res = StreamResult()
    chunk = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "Thinking about EURUSD...",
                            "thought": True,
                            "thoughtSignature": "gemini_sig_xyz_123",
                        },
                        {"text": "The market is bullish."},
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 20,
            "thoughtsTokenCount": 50,
        },
    }

    finished = _gemini_stream_parser(chunk, res)
    assert finished is True
    assert res.thinking_text == "Thinking about EURUSD..."
    assert res.text == "The market is bullish."
    assert getattr(res, "thought_signature", None) == "gemini_sig_xyz_123"


@pytest.mark.asyncio
async def test_gemini_streaming_thinking_block_preservation():
    """Verify run_tool_agent streaming branch adds MockBlock(type='thinking') before text/tools."""
    provider = GeminiProvider(
        "gemini-3.7-flash",
        api_key="dummy_key",
        settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": True}}}}},
    )

    fake_stream_res = StreamResult()
    fake_stream_res.thinking_text = "I need to call get_market_data first."
    setattr(fake_stream_res, "thought_signature", "gemini_native_thought_sig_999")
    fake_stream_res.text = "Here is the market analysis."
    fake_stream_res.tool_calls = [
        {"name": "get_market_data", "args": {"symbol": "EURUSD"}, "thoughtSignature": "ts_call_1"}
    ]
    fake_stream_res.usage = {
        "promptTokenCount": 120,
        "candidatesTokenCount": 45,
        "thoughtsTokenCount": 30,
        "cachedContentTokenCount": 50,
    }
    fake_stream_res.finish_reason = "STOP"

    with (
        patch.object(provider, "_is_paid_key", return_value=True),
        patch.object(provider, "_get_api_key", return_value="dummy_key"),
        patch("monika.infrastructure.providers.gemini_provider.get_session") as mock_get_sess,
        patch("monika.infrastructure.providers.gemini_provider.GeminiRateLimiter") as mock_rl,
        patch(
            "monika.infrastructure.providers.gemini_provider.streaming_request",
            new=AsyncMock(return_value=fake_stream_res),
        ),
    ):
        mock_session_ctx = AsyncMock()
        mock_get_sess.return_value.__aenter__.return_value = mock_session_ctx
        mock_rl.return_value.try_acquire = AsyncMock(return_value=True)

        resp = await provider.run_tool_agent(
            messages=[{"role": "user", "content": "Analyze EURUSD"}],
            tools=[],
            system_prompt="You are a helpful trading agent.",
        )

        assert resp is not None
        assert len(resp.content) == 3
        # First block must be thinking
        b0 = resp.content[0]
        assert b0.type == "thinking"
        assert b0.get("thinking") == "I need to call get_market_data first."
        assert b0.get("thought_signature") == "gemini_native_thought_sig_999"

        # Second block is text
        b1 = resp.content[1]
        assert b1.type == "text"
        assert b1.text == "Here is the market analysis."

        # Third block is tool_use
        b2 = resp.content[2]
        assert b2.type == "tool_use"
        assert b2.name == "get_market_data"


@pytest.mark.asyncio
async def test_gemini_multiturn_thinking_block_serialization_and_immutability():
    """Verify multi-turn thinking blocks serialize correctly in payload without mutating caller messages."""
    provider = GeminiProvider(
        "gemini-3.7-flash",
        api_key="dummy_key",
        settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": True}}}}},
    )

    original_messages = [
        {"role": "user", "content": "Check market condition"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "Analyzing volatility and structure...",
                    "signature": "c2lnX3Rob3VnaHRfdHVybl8x",
                },
                {"type": "text", "text": "Market is trending upward."},
            ],
        },
        {"role": "user", "content": "What about ATR?"},
    ]

    messages_snapshot = copy.deepcopy(original_messages)
    captured_payload = {}

    async def mock_streaming_request(url, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("payload", {})
        res = StreamResult()
        res.text = "ATR is 0.0045"
        res.finish_reason = "STOP"
        return res

    with (
        patch.object(provider, "_is_paid_key", return_value=True),
        patch.object(provider, "_get_api_key", return_value="dummy_key"),
        patch("monika.infrastructure.providers.gemini_provider.get_session") as mock_get_sess,
        patch("monika.infrastructure.providers.gemini_provider.GeminiRateLimiter") as mock_rl,
        patch(
            "monika.infrastructure.providers.gemini_provider.streaming_request",
            side_effect=mock_streaming_request,
        ),
    ):
        mock_session_ctx = AsyncMock()
        mock_get_sess.return_value.__aenter__.return_value = mock_session_ctx
        mock_rl.return_value.try_acquire = AsyncMock(return_value=True)

        resp = await provider.run_tool_agent(
            messages=original_messages,
            tools=[],
            system_prompt=("Static System Prompt", "Dynamic Note: High volatility detected!"),
        )
        assert resp is not None

    # Check caller messages were NEVER mutated in-place
    assert original_messages == messages_snapshot
    assert "Dynamic Note" not in str(original_messages)

    # Check that thinking block was serialized into gemini_contents
    contents = captured_payload.get("contents", [])
    assert len(contents) == 3
    # Model turn contains thought part
    model_turn = contents[1]
    assert model_turn["role"] == "model"
    thought_part = next((p for p in model_turn["parts"] if p.get("thought") is True), None)
    assert thought_part is not None
    assert thought_part["text"] == "Analyzing volatility and structure..."
    assert thought_part["thoughtSignature"] == "c2lnX3Rob3VnaHRfdHVybl8x"

    # Check that dynamic note was injected into user message in payload without affecting caller
    last_user_turn = contents[2]
    assert last_user_turn["role"] == "user"
    assert "Dynamic Note: High volatility detected!" in last_user_turn["parts"][-1]["text"]


# ---------------------------------------------------------------------------
# 2. OpenAIProvider Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openai_first_user_immutability_and_reasoning_replay():
    """Verify OpenAIProvider does not mutate caller's messages[0] and replays reasoning_content."""
    provider = OpenAIProvider("gpt-4o", api_key="dummy_key", settings={})
    provider.client = MagicMock()

    original_messages = [
        {"role": "user", "content": "What is the RSI on EURUSD?"},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "Calculating RSI over 14 bars..."},
                {"type": "text", "text": "RSI is currently 58.2."},
            ],
        },
        {"role": "user", "content": [{"type": "text", "text": "Is it overbought?"}]},
    ]
    messages_snapshot = copy.deepcopy(original_messages)
    captured_kwargs = {}

    async def mock_create(kwargs):
        nonlocal captured_kwargs
        captured_kwargs = kwargs
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "No, 58.2 is neutral."
        resp.choices[0].message.tool_calls = None
        resp.usage = None
        return resp

    with patch.object(provider, "_create_chat_completion", side_effect=mock_create):
        await provider.run_tool_agent(
            messages=original_messages,
            tools=[],
            system_prompt=("Base system instruction", "Dynamic Tier 3: Market Clock 14:00"),
        )

    # 1. Verify caller's messages list and dictionaries were completely unmutated
    assert original_messages == messages_snapshot
    assert "<context_snapshot>" not in original_messages[0]["content"]

    # 2. Verify payload has reasoning_content from thinking block
    sent_msgs = captured_kwargs.get("messages", [])
    # First message is system prompt
    assert sent_msgs[0]["role"] == "system"
    # Second message is user with context_snapshot injected in sent_msgs only
    assert sent_msgs[1]["role"] == "user"
    assert "<context_snapshot>" in sent_msgs[1]["content"]

    # Third message is assistant with reasoning_content preserved
    ast_msg = sent_msgs[2]
    assert ast_msg["role"] == "assistant"
    assert ast_msg.get("reasoning_content") == "Calculating RSI over 14 bars..."
    assert ast_msg.get("content") == "RSI is currently 58.2."


# ---------------------------------------------------------------------------
# 3. DeepSeekProvider Tests
# ---------------------------------------------------------------------------


def test_deepseek_session_affinity_headers():
    """Verify DeepSeekProvider session affinity headers helper."""
    provider = DeepSeekProvider("deepseek-reasoner", api_key="dummy_key")

    # Empty session, normal call
    h0 = provider.get_session_affinity_headers()
    assert h0 == {}

    # Session ID only
    h1 = provider.get_session_affinity_headers(session_id="session_eurusd_123")
    assert h1 == {"x-monika-session-id": "session_eurusd_123"}

    # Session ID with compaction flag
    h2 = provider.get_session_affinity_headers(session_id="session_eurusd_123", is_compaction=True)
    assert h2 == {
        "x-monika-session-id": "session_eurusd_123",
        "x-monika-compact": "1",
    }


# ---------------------------------------------------------------------------
# 4. AnthropicProvider Tests
# ---------------------------------------------------------------------------


def test_anthropic_sanitize_messages_preserves_signed_thinking_across_turns():
    """Verify _sanitize_messages preserves signed thinking & redacted_thinking before last_user_idx."""
    provider = AnthropicProvider("claude-sonnet-4-6", api_key="dummy_key")

    messages = [
        {"role": "user", "content": "Turn 1: Analyze structure"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "Historical reasoning Turn 1...",
                    "signature": "valid_crypto_sig_turn1",
                },
                {"type": "redacted_thinking", "data": "opaque_encrypted_data_turn1"},
                {"type": "thinking", "thinking": "Unsigned thinking should be stripped"},
                {"type": "text", "text": "Structure is bullish BOS."},
            ],
        },
        {"role": "user", "content": "Turn 2: Confirm order block"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "Turn 2 reasoning...",
                    "signature": "valid_crypto_sig_turn2",
                },
                {"type": "text", "text": "OB is confirmed at 1.0820."},
            ],
        },
        {"role": "user", "content": "Turn 3: Execute trade?"},
    ]

    # With preserve_historical_thinking=True (default)
    sanitized = provider._sanitize_messages(messages, preserve_historical_thinking=True)

    # Turn 1 assistant content check
    turn1_content = sanitized[1]["content"]
    types_present = [b["type"] for b in turn1_content]
    assert "text" in types_present
    assert "redacted_thinking" in types_present
    # Signed thinking block is preserved
    signed_block = next((b for b in turn1_content if b.get("signature") == "valid_crypto_sig_turn1"), None)
    assert signed_block is not None
    # Unsigned thinking block is stripped
    unsigned_block = next((b for b in turn1_content if b.get("type") == "thinking" and not b.get("signature")), None)
    assert unsigned_block is None

    # Turn 2 assistant content check (also before Turn 3 user message)
    turn2_content = sanitized[3]["content"]
    assert any(b.get("signature") == "valid_crypto_sig_turn2" for b in turn2_content)

    # With preserve_historical_thinking=False: historical thinking blocks are stripped
    stripped = provider._sanitize_messages(messages, preserve_historical_thinking=False)
    turn1_stripped = stripped[1]["content"]
    assert not any(b.get("type") in ("thinking", "redacted_thinking") for b in turn1_stripped)
    assert turn1_stripped[0]["type"] == "text"


# ---------------------------------------------------------------------------
# 5. ContextCompactionEngine Tests
# ---------------------------------------------------------------------------


def test_tool_result_pruner_one_pass_idempotence():
    """Verify tool result pruning middle-truncation and 1-pass idempotence."""
    # Text shorter than threshold
    short_text = "Status: OK. Indicators neutral."
    pruned, did_prune = prune_tool_result_text(short_text, threshold_chars=8192)
    assert not did_prune
    assert pruned == short_text

    # Text exceeding threshold (e.g. 15,000 characters)
    oversized_text = "HEAD_" + ("A" * 6000) + "_MIDDLE_" + ("B" * 6000) + "_TAIL"
    pruned_text, did_prune = prune_tool_result_text(
        oversized_text, threshold_chars=8192, head_chars=4096, tail_chars=1024
    )
    assert did_prune
    assert len(pruned_text) < len(oversized_text)
    assert "[... tool result middle pruned ...]" in pruned_text
    assert pruned_text.startswith("HEAD_")
    assert pruned_text.endswith("_TAIL")

    # 1-pass idempotence check: re-pruning an already-pruned text must NOT prune again
    second_prune, second_did_prune = prune_tool_result_text(
        pruned_text, threshold_chars=8192, head_chars=4096, tail_chars=1024
    )
    assert not second_did_prune
    assert second_prune == pruned_text


def test_prune_session_tool_results_batch_and_immutability():
    """Verify prune_session_tool_results prunes tool messages without mutating input."""
    huge_payload = "X" * 12000
    messages = [
        {"role": "user", "content": "Fetch market depth"},
        {"role": "assistant", "content": "Calling tool", "tool_calls": [{"id": "tc_1", "function": {"name": "depth"}}]},
        {"role": "tool", "tool_call_id": "tc_1", "name": "depth", "content": huge_payload},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tc_2", "content": huge_payload},
                {"type": "text", "text": "Proceed"},
            ],
        },
    ]

    messages_snapshot = copy.deepcopy(messages)
    pruned_msgs, count = prune_session_tool_results(messages, threshold_chars=8192)

    assert count == 2
    # Verify input messages was not mutated
    assert messages == messages_snapshot

    # Verify pruned results in output
    assert len(pruned_msgs[2]["content"]) < 6000
    assert "[... tool result middle pruned ...]" in pruned_msgs[2]["content"]
    assert "[... tool result middle pruned ...]" in pruned_msgs[3]["content"][0]["content"]


def test_find_tool_pairing_balanced_cut():
    """Verify find_tool_pairing_balanced_cut never severs tool calls from their results."""
    messages = [
        {"role": "user", "content": "Initial prompt"},  # 0
        {
            "role": "assistant",
            "content": "Call two tools",
            "tool_calls": [
                {"id": "call_1", "function": {"name": "t1"}},
                {"id": "call_2", "function": {"name": "t2"}},
            ],
        },  # 1 (balance = 2)
        {"role": "tool", "tool_call_id": "call_1", "content": "result 1"},  # 2 (balance = 1)
        {"role": "tool", "tool_call_id": "call_2", "content": "result 2"},  # 3 (balance = 0)
        {"role": "assistant", "content": "Both tools processed successfully."},  # 4 (balance = 0)
        {"role": "user", "content": "Next turn instruction."},  # 5 (balance = 0)
        {
            "role": "assistant",
            "content": "Call third tool",
            "tool_calls": [{"id": "call_3", "function": {"name": "t3"}}],
        },  # 6 (balance = 1)
        {"role": "tool", "tool_call_id": "call_3", "content": "result 3"},  # 7 (balance = 0)
    ]

    # Target cut at 2 (lands on tool result with balance=1): must snap backward past assistant to 1
    cut_2 = find_tool_pairing_balanced_cut(messages, target_keep_from_idx=2, min_first_idx=1)
    assert cut_2 == 1

    # Target cut at 3 (lands on tool result with balance=0): must not start on a tool result, snaps back to 1
    cut_3 = find_tool_pairing_balanced_cut(messages, target_keep_from_idx=3, min_first_idx=1)
    assert cut_3 == 1

    # Target cut at 4 (lands on assistant with balance=0): clean cut at 4
    cut_4 = find_tool_pairing_balanced_cut(messages, target_keep_from_idx=4, min_first_idx=1)
    assert cut_4 == 4

    # Target cut at 5 (lands on user message with balance=0): clean cut at 5
    cut_5 = find_tool_pairing_balanced_cut(messages, target_keep_from_idx=5, min_first_idx=1)
    assert cut_5 == 5

    # Target cut at 7 (lands on tool result with balance=0): snaps back to 6 (assistant with call_3)
    cut_7 = find_tool_pairing_balanced_cut(messages, target_keep_from_idx=7, min_first_idx=1)
    assert cut_7 == 6


@pytest.mark.asyncio
async def test_compact_with_summary_model_forwards_warm_prefix():
    """Verify compact_with_summary_model forwards system_prompt and tools to run_tool_agent."""
    compactor = ContextCompactionEngine({})

    # Build 8 messages to exceed len(messages) > 6
    messages = [
        {"role": "user", "content": "Task instruction: compute volatility"},
    ]
    for i in range(7):
        messages.append({"role": "assistant", "content": f"Step {i} analysis " * 500})
        messages.append({"role": "user", "content": f"Continue step {i} " * 500})

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "<compacted-summary>\nPreserved volatility: ATR=0.0045\n</compacted-summary>"
    mock_client.run_tool_agent = AsyncMock(return_value=mock_resp)

    passed_tools = [{"type": "function", "function": {"name": "calc_atr"}}]
    passed_system_prompt = "You are a master algorithmic trading assistant."

    with patch("monika.infrastructure.providers.llm_factory.get_client_for_task", return_value=mock_client):
        compacted = await compactor.compact_with_summary_model(
            messages=messages,
            context_window=1000,  # Force ratio > SYNTHESIS_THRESHOLD
            system_prompt=passed_system_prompt,
            tools=passed_tools,
        )

        assert mock_client.run_tool_agent.called
        call_kwargs = mock_client.run_tool_agent.call_args.kwargs
        assert call_kwargs.get("system_prompt") == passed_system_prompt
        assert call_kwargs.get("tools") == passed_tools

        # Verify compacted structure preserves first turn and summary
        assert compacted[0] == messages[0]
        assert "<compacted-summary>" in compacted[1]["content"]
