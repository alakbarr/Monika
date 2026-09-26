# ==============================================================================
# File: tests/providers/test_universal_provider.py
# ==============================================================================

"""
Unit Test Suite for Stage 5:
Universal Provider Fabric, Backend Identity, Failure Scope Candidate Skipping,
Streaming Think Scrubber, Decimal Pricing Accounting, and Trajectory Compression.
"""

from types import SimpleNamespace
import pytest

from analysis.providers.backend_identity import (
    BackendIdentity,
    FailoverCandidateSkipper,
    FailureScope,
)
from analysis.providers.streaming_think_scrubber import StreamingThinkScrubber
from analysis.providers.trajectory_compressor import TrajectoryCompressor
from utils.analytics.pricing import (
    CanonicalUsage,
    cost_usd,
    cost_from_canonical,
    get_price,
)


# ==============================================================================
# 1. Backend Identity & Candidate Skipper Tests
# ==============================================================================

def test_backend_identity_and_candidate_skipping():
    skipper = FailoverCandidateSkipper(ttl_seconds=60.0)

    id_opus = BackendIdentity.create("anthropic", "claude-opus-5", api_key="sk-ant-key-1")
    id_sonnet = BackendIdentity.create("anthropic", "claude-sonnet-5", api_key="sk-ant-key-1")
    id_gemini = BackendIdentity.create("gemini", "gemini-2.5-flash", api_key="sk-gem-key-2")

    # Initial state: no skips
    skip, _ = skipper.should_skip(id_opus)
    assert not skip

    # Case 1: MODEL failure scope (e.g., 404 Model Not Found on opus)
    skipper.record_failure(id_opus, FailureScope.MODEL)
    skip_opus, _ = skipper.should_skip(id_opus)
    skip_sonnet, _ = skipper.should_skip(id_sonnet)
    assert skip_opus is True
    assert skip_sonnet is False  # sonnet still valid

    # Case 2: CREDENTIAL failure scope (e.g., 401 Unauthorized or 402 Insufficient Balance)
    skipper.record_failure(id_sonnet, FailureScope.CREDENTIAL)
    skip_sonnet_after, reason = skipper.should_skip(id_sonnet)
    assert skip_sonnet_after is True
    assert "Credential" in reason

    # Gemini with different key should NOT be skipped
    skip_gemini, _ = skipper.should_skip(id_gemini)
    assert skip_gemini is False


# ==============================================================================
# 2. Streaming Think Scrubber Tests
# ==============================================================================

def test_streaming_think_scrubber_complete_flow():
    scrubber = StreamingThinkScrubber()

    # Stream chunks where <think> tag is split across chunks
    chunks = [
        "Trade signal: ",
        "<th",
        "ink>The RSI is oversold at 25 and MACD is crossing.",
        "</th",
        "ink>BUY EURUSD at 1.0850",
    ]

    for ch in chunks:
        scrubber.feed_chunk(ch)
    scrubber.finalize()

    # Clean content emitted to user
    assert scrubber.total_content == "Trade signal: BUY EURUSD at 1.0850"
    # Thought traces preserved separately
    assert scrubber.total_thinking == "The RSI is oversold at 25 and MACD is crossing."


# ==============================================================================
# 3. CanonicalUsage & Decimal Token Accounting Tests
# ==============================================================================

def test_canonical_usage_anthropic_no_double_cache_deduction():
    # Anthropic mock usage: input_tokens is uncached, cache_read_input_tokens is cached
    mock_usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=500,
        cache_read_input_tokens=4000,
        cache_creation_input_tokens=0,
    )
    usage = CanonicalUsage.from_anthropic(mock_usage)
    assert usage.input_tokens == 1000
    assert usage.cache_read_tokens == 4000
    assert usage.output_tokens == 500

    # Pricing calculation for claude-sonnet-4.5 ($3 / $0.30 / $15)
    cost = cost_from_canonical("claude-sonnet-4.5", usage, provider="anthropic")
    # Expected: (1000/1M * 3.00) + (4000/1M * 0.30) + (500/1M * 15.00)
    # = 0.003 + 0.0012 + 0.0075 = 0.011700
    assert cost == 0.011700


def test_canonical_usage_openai_separation():
    mock_usage = SimpleNamespace(
        prompt_tokens=5000,
        completion_tokens=200,
        prompt_tokens_details=SimpleNamespace(cached_tokens=4000),
    )
    usage = CanonicalUsage.from_openai(mock_usage)
    assert usage.input_tokens == 1000  # 5000 - 4000
    assert usage.cache_read_tokens == 4000
    assert usage.output_tokens == 200


# ==============================================================================
# 4. Trajectory Compressor & Boundary Snapping Tests
# ==============================================================================

def test_trajectory_compressor_boundary_snapping():
    compressor = TrajectoryCompressor(max_tool_output_chars=50, preserve_recent_turns=2)

    messages = [
        {"role": "system", "content": "You are Monika institutional agent."},  # Head anchor 1
        {"role": "user", "content": "Initial trade goal: backtest strategy A."}, # Head anchor 2
        {"role": "assistant", "content": "<think>Planning analysis</think>Here is the plan."}, # Intermediate
        {"role": "tool", "content": "A" * 200},                                # Intermediate tool
        {"role": "user", "content": "Intermediate query"},                     # Intermediate
        {"role": "assistant", "content": "Intermediate answer"},               # Intermediate
        {"role": "user", "content": "Recent question 1"},                      # Tail anchor
        {"role": "assistant", "content": "Recent answer 1"},                   # Tail anchor
        {"role": "user", "content": "Recent question 2"},                      # Tail anchor
        {"role": "assistant", "content": "Recent answer 2"},                   # Tail anchor
    ]

    compressed = compressor.compress_trajectory(messages)
    assert len(compressed) == len(messages)

    # Head anchors preserved intact
    assert compressed[0]["content"] == "You are Monika institutional agent."
    assert compressed[1]["content"] == "Initial trade goal: backtest strategy A."

    # Intermediate message has <think> tag stripped
    assert "<think>" not in compressed[2]["content"]
    assert "Here is the plan." in compressed[2]["content"]

    # Intermediate tool output truncated with notice
    assert len(compressed[3]["content"]) < 150
    assert "[Output truncated" in compressed[3]["content"]

    # Tail anchors preserved intact
    assert compressed[-1]["content"] == "Recent answer 2"
