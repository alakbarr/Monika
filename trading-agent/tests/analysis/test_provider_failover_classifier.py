import pytest
from analysis.providers.provider_failover_classifier import (
    FailoverReason,
    classify_error,
)
from utils.api.streaming import StreamWriterFence
from utils.plugins.manager import PluginHook


def test_overflow_variants():
    """Verify new overflow variants have correct failover & compaction policies."""
    silent = FailoverReason.SILENT_OVERFLOW
    length_stop = FailoverReason.LENGTH_STOP_OVERFLOW

    assert silent.should_compress is True
    assert silent.should_failover is False
    assert silent.max_retries == 1

    assert length_stop.should_compress is True
    assert length_stop.should_failover is False
    assert length_stop.max_retries == 1


def test_classify_standard_errors():
    """Verify classification of standard errors."""
    err_overflow = Exception("maximum context length exceeded: 128000 tokens")
    reason, detail = classify_error(err_overflow)
    assert reason == FailoverReason.CONTEXT_OVERFLOW
    assert reason.should_compress is True

    err_rate = Exception("HTTP 429 Too Many Requests: Rate limit exceeded")
    reason, detail = classify_error(err_rate)
    assert reason == FailoverReason.RATE_LIMIT_API
    assert reason.should_failover is False


def test_stream_writer_fence():
    """Verify StreamWriterFence enforces single-writer token isolation."""
    fence = StreamWriterFence()
    assert fence.generation() == 0

    token1 = fence.claim()
    assert token1 == 1
    assert fence.is_current(token1) is True
    assert fence.generation() == 1

    # New retry claims write ownership
    token2 = fence.claim()
    assert token2 == 2
    assert fence.is_current(token2) is True
    # Previous writer is now stale
    assert fence.is_current(token1) is False


def test_plugin_hook_on_llm_error():
    """Verify ON_LLM_ERROR hook exists in PluginHook."""
    assert hasattr(PluginHook, "ON_LLM_ERROR")
    assert PluginHook.ON_LLM_ERROR == "on_llm_error"
