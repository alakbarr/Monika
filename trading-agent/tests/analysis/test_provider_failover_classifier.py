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


def test_provider_circuit_breaker():
    """Verify ProviderCircuitBreaker transitions CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
    import time
    from analysis.providers.llm_factory import ProviderCircuitBreaker

    ProviderCircuitBreaker.reset()
    provider = "test_prov"

    assert ProviderCircuitBreaker.is_provider_available(provider) is True

    # 2 failures shouldn't trip breaker (threshold = 3)
    ProviderCircuitBreaker.record_provider_failure(provider, is_server_or_timeout=True, reason="500 Internal Error")
    ProviderCircuitBreaker.record_provider_failure(provider, is_server_or_timeout=True, reason="timeout")
    assert ProviderCircuitBreaker.is_provider_available(provider) is True

    # 3rd failure trips breaker
    ProviderCircuitBreaker.record_provider_failure(provider, is_server_or_timeout=True, reason="503 Service Unavailable")
    assert ProviderCircuitBreaker.is_provider_available(provider) is False

    # Simulate cooldown expiry
    ProviderCircuitBreaker._open_until[provider] = time.time() - 1.0
    # Next check transitions to HALF_OPEN (returns True for 1 canary probe)
    assert ProviderCircuitBreaker.is_provider_available(provider) is True
    assert ProviderCircuitBreaker._states[provider] == "HALF_OPEN"

    # Success restores to CLOSED
    ProviderCircuitBreaker.record_provider_success(provider)
    assert ProviderCircuitBreaker.is_provider_available(provider) is True
    assert ProviderCircuitBreaker._states[provider] == "CLOSED"


def test_capability_blacklist():
    """Verify model blacklisting with expiration."""
    import time
    from analysis.providers.llm_factory import ProviderCircuitBreaker

    ProviderCircuitBreaker.reset()
    provider = "openrouter"
    model = "anthropic/claude-3-haiku:broken"

    assert ProviderCircuitBreaker.is_model_blacklisted(provider, model) is False

    ProviderCircuitBreaker.blacklist_model(provider, model, reason="billing_exhausted", duration=60.0)
    assert ProviderCircuitBreaker.is_model_blacklisted(provider, model) is True

    # Expire blacklist
    ProviderCircuitBreaker._blacklisted_models[(provider, model)] = time.time() - 1.0
    assert ProviderCircuitBreaker.is_model_blacklisted(provider, model) is False


def test_failover_reason_hot_path_eager():
    """Verify RATE_LIMIT_API enables immediate failover when is_hot_path is True."""
    from analysis.providers.provider_failover_classifier import FailoverReason
    # In background mode: should_failover is False (retries)
    assert FailoverReason.RATE_LIMIT_API.should_failover is False
    assert FailoverReason.RATE_LIMIT_API.can_failover(is_hot_path=False) is False
    # In hot path mode: can_failover is True (eager failover, 0s stall)
    assert FailoverReason.RATE_LIMIT_API.can_failover(is_hot_path=True) is True
    assert FailoverReason.RATE_LIMIT_MODEL.can_failover(is_hot_path=True) is True


@pytest.mark.asyncio
async def test_streaming_heartbeat_monitor():
    """Verify StreamingHeartbeatMonitor emits pulses and stops cleanly."""
    import asyncio
    from utils.api.streaming import StreamingHeartbeatMonitor

    pulse_count = 0

    def on_touch():
        nonlocal pulse_count
        pulse_count += 1

    monitor = StreamingHeartbeatMonitor(interval=0.05, touch_fn=on_touch)
    monitor.start()
    await asyncio.sleep(0.12)
    monitor.stop()

    assert pulse_count >= 2


