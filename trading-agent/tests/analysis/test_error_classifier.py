"""
Unit tests for structured error classification (C4).
"""
import pytest
from analysis.providers.provider_failover_classifier import FailoverReason, classify_error


def test_backward_compatibility_shim():
    from analysis.providers.error_classifier import FailoverReason as ShimReason, classify_error as shim_classify
    assert ShimReason is FailoverReason
    assert shim_classify is classify_error


def test_error_classifier_rate_limit():
    exc = Exception("Error code 429: rate limit exceeded. Please retry after 30s")
    reason, detail = classify_error(exc)
    assert reason in (FailoverReason.RATE_LIMIT_API, FailoverReason.RATE_LIMIT_MODEL)
    assert reason.should_compress is False


def test_error_classifier_context_overflow():
    exc = Exception("InvalidParameterError: maximum context length is 8192 tokens, but request has 9400 tokens")
    reason, detail = classify_error(exc)
    assert reason == FailoverReason.CONTEXT_OVERFLOW
    assert reason.should_compress is True
    assert reason.should_failover is False


def test_error_classifier_auth_failure():
    exc = Exception("AuthenticationError: invalid_api_key provided")
    reason, detail = classify_error(exc)
    assert reason == FailoverReason.AUTH_PERMANENT
    assert reason.should_failover is True


def test_error_classifier_transient_overload():
    exc = Exception("API Server is overloaded (status 529). Please try again.")
    reason, detail = classify_error(exc)
    assert reason == FailoverReason.MODEL_OVERLOADED


def test_error_classifier_network_timeout():
    import asyncio
    exc = asyncio.TimeoutError()
    reason, detail = classify_error(exc)
    assert reason == FailoverReason.NETWORK_TIMEOUT


def test_error_classifier_upstream_rate_limit():
    exc = Exception("OpenRouter upstream provider error: 429 rate limit exceeded")
    reason, detail = classify_error(exc)
    assert reason == FailoverReason.UPSTREAM_RATE_LIMIT
    assert reason.should_failover is True
    assert reason.backoff_seconds == 20.0


def test_error_classifier_invalid_request():
    exc = Exception("BadRequestError 400: schema validation failed for tool parameters")
    reason, detail = classify_error(exc)
    assert reason == FailoverReason.INVALID_REQUEST
    assert reason.should_failover is False
    assert reason.max_retries == 0


def test_error_classifier_broker_margin_call():
    exc = Exception("Order rejected: margin call reached, not enough money to open position")
    reason, detail = classify_error(exc)
    assert reason == FailoverReason.BROKER_MARGIN_CALL
    assert reason.should_failover is False
    assert reason.max_retries == 0


def test_all_failover_reasons_exist():
    assert len(FailoverReason) == 20
    expected_members = {
        "AUTH_TRANSIENT", "AUTH_PERMANENT", "BILLING_EXHAUSTED",
        "RATE_LIMIT_API", "RATE_LIMIT_MODEL", "UPSTREAM_RATE_LIMIT",
        "CONTEXT_OVERFLOW", "PAYLOAD_TOO_LARGE", "MODEL_OVERLOADED",
        "MODEL_NOT_FOUND", "MODEL_UNAVAILABLE", "INVALID_REQUEST",
        "NETWORK_TIMEOUT", "NETWORK_CONNECTION", "CONTENT_FILTERED",
        "SERVER_ERROR", "BROKER_MARGIN_CALL", "SILENT_OVERFLOW",
        "LENGTH_STOP_OVERFLOW", "UNKNOWN"
    }
    actual_members = {r.name for r in FailoverReason}
    assert actual_members == expected_members

