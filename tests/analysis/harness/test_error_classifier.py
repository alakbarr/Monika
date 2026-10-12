"""Unit tests for structured error classification pipeline (Phase 3)."""

import pytest
from analysis.harness.error_classifier import (
    ErrorCategory,
    RecoveryAction,
    ClassifiedError,
    ErrorClassifier,
)


class DummyExceptionWithStatus(Exception):
    def __init__(self, message: str, status_code: int, headers: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers or {}


def test_classify_context_overflow_status():
    exc = DummyExceptionWithStatus("Context length exceeded", 413)
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.CONTEXT_OVERFLOW
    assert result.recovery == RecoveryAction.RETRY_WITH_COMPACTION


def test_classify_context_overflow_text():
    exc = Exception("prompt is too long for model max context tokens")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.CONTEXT_OVERFLOW
    assert result.recovery == RecoveryAction.RETRY_WITH_COMPACTION


def test_classify_rate_limit_with_retry_after():
    exc = DummyExceptionWithStatus("Too many requests", 429, headers={"retry-after": "45.5"})
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.RATE_LIMIT
    assert result.recovery == RecoveryAction.ROTATE_CREDENTIAL
    assert result.retry_delay == 45.5


def test_classify_auth_error():
    exc = DummyExceptionWithStatus("Invalid API key provided", 401)
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.AUTH_ERROR
    assert result.recovery == RecoveryAction.FAIL_PERMANENT


def test_classify_billing_exhaustion():
    exc = DummyExceptionWithStatus("Insufficient quota or credit balance", 402)
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.BILLING_EXHAUSTION
    assert result.recovery == RecoveryAction.FALLBACK_MODEL


def test_classify_server_error():
    exc = DummyExceptionWithStatus("Internal server error", 500)
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.SERVER_ERROR
    assert result.recovery == RecoveryAction.RETRY_SAME
    assert result.retry_delay == 5.0


def test_classify_content_refusal():
    exc = Exception("Safety system blocked prompt content: content_policy_violation")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.CONTENT_REFUSAL
    assert result.recovery == RecoveryAction.FALLBACK_MODEL


def test_classify_malformed_tool_args():
    exc = Exception("JSONDecodeError: Expecting value at line 1 column 1 (char 0)")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.MALFORMED_TOOL_ARGS
    assert result.recovery == RecoveryAction.REPAIR_AND_RETRY


def test_classify_transient_network():
    exc = Exception("Connection reset by peer during read timeout")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.TRANSIENT_NETWORK
    assert result.recovery == RecoveryAction.RETRY_SAME
    assert result.retry_delay == 3.0


def test_classify_unknown():
    exc = RuntimeError("Unexpected internal algorithmic condition")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.UNKNOWN
    assert result.recovery == RecoveryAction.FAIL_PERMANENT


def test_classify_response_truncation_with_tools():
    resp = {
        "finish_reason": "length",
        "content": "I have calculated the trend...",
        "tool_calls": [{"name": "get_market_data", "arguments": "{}"}],
    }
    result = ErrorClassifier.classify_response(resp)
    assert result is not None
    assert result.category == ErrorCategory.OUTPUT_TRUNCATION
    assert result.recovery == RecoveryAction.INJECT_NUDGE
    assert "Tool calls were NOT executed" in result.nudge_text


def test_classify_response_truncation_without_tools():
    resp = {
        "stop_reason": "max_tokens",
        "content": "The economic indicators show that inflation is",
        "tool_calls": [],
    }
    result = ErrorClassifier.classify_response(resp)
    assert result is not None
    assert result.category == ErrorCategory.OUTPUT_TRUNCATION
    assert result.recovery == RecoveryAction.INJECT_CONTINUATION
    assert "Continue exactly where you left off" in result.nudge_text


def test_classify_response_thinking_exhaustion():
    resp = {
        "finish_reason": "stop",
        "content": "",
        "reasoning": "Let me think carefully about whether we should buy or sell...",
        "tool_calls": [],
    }
    result = ErrorClassifier.classify_response(resp)
    assert result is not None
    assert result.category == ErrorCategory.THINKING_EXHAUSTION
    assert result.recovery == RecoveryAction.RETRY_WITH_REDUCED_EFFORT


def test_classify_response_dropped_tool_call():
    resp = {
        "finish_reason": "stop",
        "content": "Let me use the market data tool to inspect the 4h trend.",
        "tool_calls": [],
    }
    result = ErrorClassifier.classify_response(resp)
    assert result is not None
    assert result.category == ErrorCategory.DROPPED_TOOL_CALL
    assert result.recovery == RecoveryAction.INJECT_NUDGE
    assert "You described a tool call but did not issue one" in result.nudge_text


def test_classify_response_clean():
    resp = {
        "finish_reason": "stop",
        "content": "Analysis completed. Trend is bullish.",
        "tool_calls": [],
    }
    result = ErrorClassifier.classify_response(resp)
    assert result is None


def test_sanitize_unicode_surrogates():
    from analysis.harness.error_classifier import sanitize_unicode_surrogates
    dirty = "EURUSD \ud83d\ude00 price \ud800\udc00 valid text"
    clean = sanitize_unicode_surrogates(dirty)
    assert "\ud800" not in clean
    assert "\udc00" not in clean
    assert "EURUSD" in clean
    assert "valid text" in clean

    # Nested dict / list support
    nested = {"key": "test \ud83d val", "list": ["safe", "dirty \udfff item"]}
    clean_nested = sanitize_unicode_surrogates(nested)
    assert "\ud83d" not in clean_nested["key"]
    assert "\udfff" not in clean_nested["list"][1]


def test_fallback_multimodal_to_text():
    from analysis.harness.error_classifier import fallback_multimodal_to_text
    messages = [
        {"role": "user", "content": "Check chart below"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Here is chart"},
                {"type": "image", "source": {"media_type": "image/png", "data": "BASE64_DATA_12345"}},
            ],
        },
    ]

    downgraded = fallback_multimodal_to_text(messages)
    assert len(downgraded) == 2
    blocks = downgraded[1]["content"]
    assert blocks[0]["type"] == "text"
    assert blocks[1]["type"] == "text"
    assert "CHART/IMAGE DOWGRADED TO TEXT" in blocks[1]["text"]


def test_classify_unicode_surrogate_error():
    exc = Exception("'utf-8' codec can't encode characters in position 12-13: surrogates not allowed")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.MALFORMED_TOOL_ARGS
    assert result.recovery == RecoveryAction.REPAIR_AND_RETRY


def test_classify_multimodal_size_rejection():
    exc = Exception("payload too large: image size exceeds provider limit")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.SERVER_ERROR
    assert result.recovery == RecoveryAction.RETRY_WITH_COMPACTION


def test_classify_with_nested_response_status():
    class DummyResponse:
        status_code = 503

    exc = Exception("Service unavailable from upstream")
    exc.response = DummyResponse()

    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.SERVER_ERROR
    assert result.recovery == RecoveryAction.RETRY_SAME


def test_classify_rate_limit_with_nested_response_headers():
    class DummyResponse:
        status_code = 429
        headers = {"retry-after": "25.0"}

    exc = Exception("Too Many Requests")
    exc.response = DummyResponse()

    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.RATE_LIMIT
    assert result.recovery == RecoveryAction.ROTATE_CREDENTIAL
    assert result.retry_delay == 25.0


