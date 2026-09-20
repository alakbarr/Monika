import pytest
from utils.streaming.stream_scrubber import StatefulStreamScrubber


def test_scrubber_clean_text():
    scrubber = StatefulStreamScrubber()
    chunks = ["EURUSD ", "momentum is ", "positive. ", "Target: 1.0850."]
    emitted = "".join(scrubber.process_delta(c) for c in chunks) + scrubber.flush()
    assert emitted == "EURUSD momentum is positive. Target: 1.0850."
    assert scrubber.accumulated_thinking == ""


def test_scrubber_complete_think_block():
    scrubber = StatefulStreamScrubber()
    chunks = [
        "Analysis summary: ",
        "<think>Checking 200 EMA and RSI 14 on H4 chart.</think>",
        "Bullish continuation expected.",
    ]
    emitted = "".join(scrubber.process_delta(c) for c in chunks) + scrubber.flush()
    assert emitted == "Analysis summary: Bullish continuation expected."
    assert "Checking 200 EMA" in scrubber.accumulated_thinking


def test_scrubber_split_boundary_think_block():
    scrubber = StatefulStreamScrubber()
    # Tag split across multiple chunk boundaries
    chunks = [
        "Executive Summary:\n",
        "<th",
        "ink>Calculating stop loss distance and ATR multiplier ",
        "across 14 candles...</th",
        "ink>\nFinal trade signal: BUY EURUSD.",
    ]
    emitted = "".join(scrubber.process_delta(c) for c in chunks) + scrubber.flush()
    assert "<think>" not in emitted
    assert "</think>" not in emitted
    assert "Calculating stop loss distance" not in emitted
    assert "Final trade signal: BUY EURUSD." in emitted
    assert "Calculating stop loss distance" in scrubber.accumulated_thinking


def test_scrubber_internal_context_tags():
    scrubber = StatefulStreamScrubber()
    chunks = [
        "Market report: ",
        "<market-memory-context>\nInternal playbook rule active\n</market-memory-context>",
        "Execution confirmed.",
    ]
    emitted = "".join(scrubber.process_delta(c) for c in chunks) + scrubber.flush()
    assert "<market-memory-context>" not in emitted
    assert "Internal playbook rule active" not in emitted
    assert emitted == "Market report: Execution confirmed."


def test_scrubber_secret_redaction():
    scrubber = StatefulStreamScrubber(redact_secrets=True)
    text = "Configured with api_key='sk-1234567890abcdef1234567890' and bot123456789:ABCdefGhIjkLmNoPqRsTuVwXyZ123456789."
    emitted = scrubber.process_delta(text) + scrubber.flush()
    assert "sk-1234567890abcdef1234567890" not in emitted
    assert "[REDACTED_API_KEY]" in emitted or "[REDACTED_SECRET]" in emitted
    assert "ABCdefGhIjkLmNoPqRsTuVwXyZ" not in emitted
    assert "[REDACTED_TELEGRAM_TOKEN]" in emitted


def test_scrubber_unmatched_trailing_less_than():
    scrubber = StatefulStreamScrubber()
    chunks = ["Spread is < 1.5 pips."]
    emitted = "".join(scrubber.process_delta(c) for c in chunks) + scrubber.flush()
    assert emitted == "Spread is < 1.5 pips."
