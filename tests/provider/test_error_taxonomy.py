"""
Unit tests for Monika Unified Error Taxonomy (provider/error_taxonomy.py).
Tests provider failover reasons, trading domain exceptions, and actionable properties.
"""

import pytest
from provider.error_taxonomy import (
    FailoverReason,
    ErrorCategory,
    RecoveryAction,
    ClassifiedError,
    ErrorClassifier,
)


def test_trading_requote_classification():
    exc = Exception("MT5 execution error: 10004 requote from broker FBS")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.REQUOTE
    assert result.recovery == RecoveryAction.RETRY_SAME
    assert result.is_trading_domain is True
    assert result.retryable is True
    assert result.cooldown_seconds == 1.0


def test_trading_margin_insufficient():
    exc = Exception("Order rejected: 10019 not enough money for lot size 2.5")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.MARGIN_INSUFFICIENT
    assert result.recovery == RecoveryAction.FAIL_PERMANENT
    assert result.is_trading_domain is True
    assert result.retryable is False


def test_trading_broker_disconnect():
    exc = Exception("MetaTrader5 API: terminal not responding or connection lost")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.BROKER_DISCONNECT
    assert result.recovery == RecoveryAction.RETRY_SAME
    assert result.is_trading_domain is True
    assert result.cooldown_seconds == 5.0


def test_trading_kill_switch_active():
    exc = Exception("OrderExecutionBlocked: emergency stop / kill switch active")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.KILL_SWITCH_ACTIVE
    assert result.recovery == RecoveryAction.FAIL_PERMANENT
    assert result.is_trading_domain is True
    assert result.retryable is False


def test_trading_spread_too_wide():
    exc = Exception("RiskGate: market spread too wide (4.8 pips > ceiling 3.0 pips)")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.SPREAD_TOO_WIDE
    assert result.recovery == RecoveryAction.COOLDOWN_AND_RETRY
    assert result.is_trading_domain is True
    assert result.cooldown_seconds == 15.0


def test_trading_stale_feed():
    exc = Exception("PreFlightGate: data_feed_stale for XAUUSD (last tick 180s ago)")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.DATA_FEED_STALE
    assert result.recovery == RecoveryAction.DEGRADE_DEFENSIVE
    assert result.is_trading_domain is True
    assert result.retryable is False


def test_classify_trading_error_code_direct():
    result_requote = ErrorClassifier.classify_trading_error(10004)
    assert result_requote.category == ErrorCategory.REQUOTE
    assert result_requote.reason == FailoverReason.REQUOTE

    result_margin = ErrorClassifier.classify_trading_error(10019)
    assert result_margin.category == ErrorCategory.MARGIN_INSUFFICIENT
    assert result_margin.reason == FailoverReason.MARGIN_INSUFFICIENT

    result_timeout = ErrorClassifier.classify_trading_error("order_send timeout after 2000ms")
    assert result_timeout.category == ErrorCategory.ORDER_TIMEOUT
    assert result_timeout.reason == FailoverReason.ORDER_TIMEOUT


def test_provider_rate_limit_properties():
    exc = Exception("429 resource_exhausted rate limit exceeded")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.RATE_LIMIT
    assert result.should_rotate_cred is True
    assert result.is_trading_domain is False


def test_provider_context_overflow_properties():
    exc = Exception("maximum context length is 128000 tokens, but request was 132000 tokens")
    result = ErrorClassifier.classify(exc)
    assert result.category == ErrorCategory.CONTEXT_OVERFLOW
    assert result.should_compress is True
    assert result.recovery == RecoveryAction.RETRY_WITH_COMPACTION


def test_failover_reason_properties():
    reason = FailoverReason.RATE_LIMIT_MODEL
    assert reason.should_failover is True
    assert reason.backoff_seconds == 60.0
    assert reason.max_retries == 2

    # Trading reasons should never failover LLM
    assert FailoverReason.REQUOTE.should_failover is False
    assert FailoverReason.MARGIN_INSUFFICIENT.should_failover is False
    assert FailoverReason.KILL_SWITCH_ACTIVE.should_failover is False
