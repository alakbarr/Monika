"""
Monika v2 Unified Error Taxonomy & Recovery Strategy Assignment.
Synthesizes provider failover reasons, agent harness error categories, and MT5 trading domain constraints.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any, Dict, List, Set, Union
import copy
import logging
import re

logger = logging.getLogger("TradingAgent.Provider.ErrorTaxonomy")

# U+D800 to U+DFFF isolated surrogate code points
SURROGATE_PATTERN = re.compile(r"[\uD800-\uDFFF]")


def sanitize_unicode_surrogates(data: Any) -> Any:
    """Strip illegal isolated Unicode surrogate pairs (U+D800 to U+DFFF) to prevent JSON serialization errors."""
    if isinstance(data, str):
        return SURROGATE_PATTERN.sub("", data)
    elif isinstance(data, dict):
        return {sanitize_unicode_surrogates(k): sanitize_unicode_surrogates(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_unicode_surrogates(item) for item in data]
    return data


def fallback_multimodal_to_text(messages: List[dict]) -> List[dict]:
    """Graceful multimodal fallback: If image/chart payload fails or exceeds size limit,
    downgrade multimodal blocks to structured textual JSON descriptions without aborting turn."""
    safe_messages = copy.deepcopy(messages)
    for msg in safe_messages:
        content = msg.get("content")
        if isinstance(content, list):
            new_blocks = []
            for block in content:
                if isinstance(block, dict):
                    b_type = block.get("type") or ""
                    if b_type in ("image", "image_url") or "inline_data" in block:
                        source = block.get("source", {})
                        media_type = source.get("media_type", "image/png")
                        data_len = len(str(source.get("data", "")))
                        new_blocks.append({
                            "type": "text",
                            "text": f"[CHART/IMAGE DOWGRADED TO TEXT: Type={media_type}, Size={data_len} bytes. Visual data omitted to maintain connection stability.]"
                        })
                    else:
                        new_blocks.append(block)
                else:
                    new_blocks.append(block)
            msg["content"] = new_blocks
    return safe_messages


class FailoverReason(str, Enum):
    """
    Granular reason for provider failover or trading system recovery.
    Includes 30+ LLM API error causes + MT5 execution exceptions.
    """
    # Provider Auth & Quota
    AUTH_TRANSIENT = "auth_transient"
    AUTH_PERMANENT = "auth_permanent"
    AUTH_ERROR = "auth_error"
    BILLING_EXHAUSTED = "billing"
    BILLING_EXHAUSTION = "billing"
    HARD_QUOTA_EXHAUSTED = "hard_quota_exhausted"
    RATE_LIMIT_API = "rate_limit_api"
    RATE_LIMIT_MODEL = "rate_limit_model"
    RATE_LIMIT = "rate_limit"
    TRANSIENT_RATE_LIMIT = "transient_rate_limit"
    UPSTREAM_RATE_LIMIT = "upstream_rate_limit"
    UPSTREAM_BLOCKED = "upstream_blocked"
    MODEL_ENTITLEMENT = "model_entitlement"

    # Context & Token Limits
    CONTEXT_OVERFLOW = "context_overflow"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    SILENT_OVERFLOW = "silent_overflow"
    LENGTH_STOP_OVERFLOW = "length_stop_overflow"
    OUTPUT_CAP_REACHED = "output_cap_reached"
    COMPLETION_CEILING_EXCEEDED = "completion_ceiling_exceeded"
    OUTPUT_TRUNCATION = "output_truncation"
    THINKING_EXHAUSTION = "thinking_exhaustion"
    THINKING_SIGNATURE = "thinking_signature"

    # Model & Network Availability
    MODEL_OVERLOADED = "overloaded"
    MODEL_NOT_FOUND = "model_not_found"
    MODEL_UNAVAILABLE = "unavailable"
    INVALID_REQUEST = "invalid_request"
    NETWORK_TIMEOUT = "timeout"
    NETWORK_CONNECTION = "connection"
    TRANSIENT_NETWORK = "transient_network"
    CONTENT_FILTERED = "content_filtered"
    CONTENT_REFUSAL = "content_refusal"
    SERVER_ERROR = "server_error"

    # Tool Calling & Formatting
    ROLE_ALTERNATION = "role_alternation"
    IMAGE_TOO_LARGE = "image_too_large"
    IMAGE_CORRUPT = "image_corrupt"
    DROPPED_TOOL_CALL = "dropped_tool_call"
    MALFORMED_TOOL_ARGS = "malformed_tool_args"

    # Trading Domain Specific (MT5 Execution & Risk)
    REQUOTE = "requote"
    PARTIAL_FILL = "partial_fill"
    BROKER_MARGIN_CALL = "broker_margin_call"
    MARGIN_INSUFFICIENT = "margin_insufficient"
    BROKER_DISCONNECT = "broker_disconnect"
    DATA_FEED_STALE = "data_feed_stale"
    KILL_SWITCH_ACTIVE = "kill_switch_active"
    INVARIANT_VIOLATION = "invariant_violation"
    SPREAD_TOO_WIDE = "spread_too_wide"
    ORDER_TIMEOUT = "order_timeout"

    UNKNOWN = "unknown"

    @property
    def is_trading_domain(self) -> bool:
        """Check if error originates from trading domain / broker layer."""
        return self in {
            FailoverReason.REQUOTE,
            FailoverReason.PARTIAL_FILL,
            FailoverReason.BROKER_MARGIN_CALL,
            FailoverReason.MARGIN_INSUFFICIENT,
            FailoverReason.BROKER_DISCONNECT,
            FailoverReason.DATA_FEED_STALE,
            FailoverReason.KILL_SWITCH_ACTIVE,
            FailoverReason.INVARIANT_VIOLATION,
            FailoverReason.SPREAD_TOO_WIDE,
            FailoverReason.ORDER_TIMEOUT,
        }

    @property
    def should_failover(self) -> bool:
        """Whether this error warrants trying a different LLM model."""
        NO_FAILOVER = {
            FailoverReason.CONTEXT_OVERFLOW,
            FailoverReason.PAYLOAD_TOO_LARGE,
            FailoverReason.SILENT_OVERFLOW,
            FailoverReason.LENGTH_STOP_OVERFLOW,
            FailoverReason.OUTPUT_CAP_REACHED,
            FailoverReason.COMPLETION_CEILING_EXCEEDED,
            FailoverReason.OUTPUT_TRUNCATION,
            FailoverReason.THINKING_EXHAUSTION,
            FailoverReason.DROPPED_TOOL_CALL,
            FailoverReason.MALFORMED_TOOL_ARGS,
            FailoverReason.RATE_LIMIT_API,
            FailoverReason.RATE_LIMIT,
            FailoverReason.TRANSIENT_RATE_LIMIT,
            FailoverReason.MODEL_OVERLOADED,
            FailoverReason.NETWORK_TIMEOUT,
            FailoverReason.NETWORK_CONNECTION,
            FailoverReason.TRANSIENT_NETWORK,
            FailoverReason.CONTENT_FILTERED,
            FailoverReason.SERVER_ERROR,
            FailoverReason.INVALID_REQUEST,
            FailoverReason.IMAGE_TOO_LARGE,
            FailoverReason.ROLE_ALTERNATION,
            # Trading domain errors should never switch LLM models
            FailoverReason.REQUOTE,
            FailoverReason.PARTIAL_FILL,
            FailoverReason.BROKER_MARGIN_CALL,
            FailoverReason.MARGIN_INSUFFICIENT,
            FailoverReason.BROKER_DISCONNECT,
            FailoverReason.DATA_FEED_STALE,
            FailoverReason.KILL_SWITCH_ACTIVE,
            FailoverReason.INVARIANT_VIOLATION,
            FailoverReason.SPREAD_TOO_WIDE,
            FailoverReason.ORDER_TIMEOUT,
        }
        return self not in NO_FAILOVER

    def can_failover(self, is_hot_path: bool = False) -> bool:
        """Whether this error warrants trying a different model, accounting for hot-path zero-downtime urgency."""
        if is_hot_path and self in (
            FailoverReason.RATE_LIMIT_API,
            FailoverReason.RATE_LIMIT_MODEL,
            FailoverReason.RATE_LIMIT,
            FailoverReason.TRANSIENT_RATE_LIMIT,
            FailoverReason.UPSTREAM_RATE_LIMIT,
            FailoverReason.MODEL_OVERLOADED,
            FailoverReason.UPSTREAM_BLOCKED,
            FailoverReason.MODEL_ENTITLEMENT,
            FailoverReason.THINKING_SIGNATURE,
        ):
            return True
        return self.should_failover

    @property
    def should_compress(self) -> bool:
        """Whether to compact context instead of failover."""
        return self in {
            FailoverReason.CONTEXT_OVERFLOW,
            FailoverReason.PAYLOAD_TOO_LARGE,
            FailoverReason.SILENT_OVERFLOW,
            FailoverReason.LENGTH_STOP_OVERFLOW,
            FailoverReason.IMAGE_TOO_LARGE,
        }

    @property
    def is_output_cap(self) -> bool:
        return self in (FailoverReason.OUTPUT_CAP_REACHED, FailoverReason.LENGTH_STOP_OVERFLOW)

    @property
    def is_completion_ceiling(self) -> bool:
        return self == FailoverReason.COMPLETION_CEILING_EXCEEDED

    @property
    def is_hard_quota_exhausted(self) -> bool:
        return self in (FailoverReason.HARD_QUOTA_EXHAUSTED, FailoverReason.BILLING_EXHAUSTED)

    @property
    def backoff_seconds(self) -> float:
        _MAP = {
            FailoverReason.RATE_LIMIT_API: 15.0,
            FailoverReason.RATE_LIMIT_MODEL: 60.0,
            FailoverReason.RATE_LIMIT: 15.0,
            FailoverReason.TRANSIENT_RATE_LIMIT: 15.0,
            FailoverReason.UPSTREAM_RATE_LIMIT: 20.0,
            FailoverReason.MODEL_OVERLOADED: 10.0,
            FailoverReason.NETWORK_TIMEOUT: 5.0,
            FailoverReason.NETWORK_CONNECTION: 5.0,
            FailoverReason.TRANSIENT_NETWORK: 3.0,
            FailoverReason.SERVER_ERROR: 10.0,
            FailoverReason.CONTENT_FILTERED: 2.0,
            FailoverReason.CONTENT_REFUSAL: 0.0,
            FailoverReason.INVALID_REQUEST: 0.0,
            FailoverReason.BROKER_MARGIN_CALL: 0.0,
            FailoverReason.MARGIN_INSUFFICIENT: 0.0,
            FailoverReason.SILENT_OVERFLOW: 0.0,
            FailoverReason.LENGTH_STOP_OVERFLOW: 0.0,
            FailoverReason.OUTPUT_CAP_REACHED: 0.0,
            FailoverReason.COMPLETION_CEILING_EXCEEDED: 0.0,
            FailoverReason.HARD_QUOTA_EXHAUSTED: 0.0,
            FailoverReason.BILLING_EXHAUSTED: 0.0,
            FailoverReason.UPSTREAM_BLOCKED: 30.0,
            FailoverReason.IMAGE_TOO_LARGE: 0.0,
            FailoverReason.IMAGE_CORRUPT: 0.0,
            FailoverReason.ROLE_ALTERNATION: 0.0,
            FailoverReason.THINKING_SIGNATURE: 0.0,
            FailoverReason.MODEL_ENTITLEMENT: 0.0,
            FailoverReason.REQUOTE: 1.0,
            FailoverReason.BROKER_DISCONNECT: 5.0,
            FailoverReason.DATA_FEED_STALE: 10.0,
            FailoverReason.SPREAD_TOO_WIDE: 15.0,
            FailoverReason.ORDER_TIMEOUT: 2.0,
        }
        return _MAP.get(self, 0.0)

    @property
    def max_retries(self) -> int:
        _MAP = {
            FailoverReason.RATE_LIMIT_API: 3,
            FailoverReason.RATE_LIMIT_MODEL: 2,
            FailoverReason.RATE_LIMIT: 3,
            FailoverReason.TRANSIENT_RATE_LIMIT: 3,
            FailoverReason.UPSTREAM_RATE_LIMIT: 1,
            FailoverReason.MODEL_OVERLOADED: 3,
            FailoverReason.NETWORK_TIMEOUT: 2,
            FailoverReason.NETWORK_CONNECTION: 2,
            FailoverReason.TRANSIENT_NETWORK: 3,
            FailoverReason.CONTEXT_OVERFLOW: 1,
            FailoverReason.PAYLOAD_TOO_LARGE: 1,
            FailoverReason.SILENT_OVERFLOW: 1,
            FailoverReason.LENGTH_STOP_OVERFLOW: 1,
            FailoverReason.OUTPUT_CAP_REACHED: 0,
            FailoverReason.COMPLETION_CEILING_EXCEEDED: 1,
            FailoverReason.HARD_QUOTA_EXHAUSTED: 0,
            FailoverReason.BILLING_EXHAUSTED: 0,
            FailoverReason.SERVER_ERROR: 2,
            FailoverReason.CONTENT_FILTERED: 1,
            FailoverReason.CONTENT_REFUSAL: 0,
            FailoverReason.INVALID_REQUEST: 0,
            FailoverReason.BROKER_MARGIN_CALL: 0,
            FailoverReason.MARGIN_INSUFFICIENT: 0,
            FailoverReason.UPSTREAM_BLOCKED: 1,
            FailoverReason.IMAGE_TOO_LARGE: 1,
            FailoverReason.IMAGE_CORRUPT: 0,
            FailoverReason.ROLE_ALTERNATION: 1,
            FailoverReason.THINKING_SIGNATURE: 0,
            FailoverReason.MODEL_ENTITLEMENT: 0,
            FailoverReason.REQUOTE: 2,
            FailoverReason.PARTIAL_FILL: 1,
            FailoverReason.BROKER_DISCONNECT: 2,
            FailoverReason.DATA_FEED_STALE: 1,
            FailoverReason.KILL_SWITCH_ACTIVE: 0,
            FailoverReason.INVARIANT_VIOLATION: 0,
            FailoverReason.SPREAD_TOO_WIDE: 2,
            FailoverReason.ORDER_TIMEOUT: 1,
        }
        return _MAP.get(self, 0)


class ErrorCategory(str, Enum):
    """Broad error category for harness routing, maintaining 100% backward compatibility."""
    CONTEXT_OVERFLOW = "context_overflow"
    RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"
    SERVER_ERROR = "server_error"
    OUTPUT_TRUNCATION = "output_truncation"
    THINKING_EXHAUSTION = "thinking_exhaustion"
    CONTENT_REFUSAL = "content_refusal"
    BILLING_EXHAUSTION = "billing_exhaustion"
    DROPPED_TOOL_CALL = "dropped_tool_call"
    MALFORMED_TOOL_ARGS = "malformed_tool_args"
    TRANSIENT_NETWORK = "transient_network"

    # Trading Domain Specific Categories
    REQUOTE = "requote"
    PARTIAL_FILL = "partial_fill"
    MARGIN_INSUFFICIENT = "margin_insufficient"
    BROKER_DISCONNECT = "broker_disconnect"
    DATA_FEED_STALE = "data_feed_stale"
    KILL_SWITCH_ACTIVE = "kill_switch_active"
    INVARIANT_VIOLATION = "invariant_violation"
    SPREAD_TOO_WIDE = "spread_too_wide"
    ORDER_TIMEOUT = "order_timeout"

    UNKNOWN = "unknown"


class RecoveryAction(str, Enum):
    """Actionable mitigation policy assigned by the classifier."""
    RETRY_SAME = "retry_same"
    RETRY_WITH_COMPACTION = "retry_with_compaction"
    RETRY_WITH_REDUCED_EFFORT = "retry_with_reduced_effort"
    ROTATE_CREDENTIAL = "rotate_credential"
    FALLBACK_MODEL = "fallback_model"
    INJECT_NUDGE = "inject_nudge"
    INJECT_CONTINUATION = "inject_continuation"
    REPAIR_AND_RETRY = "repair_and_retry"
    FAIL_PERMANENT = "fail_permanent"
    COOLDOWN_AND_RETRY = "cooldown_and_retry"
    DEGRADE_DEFENSIVE = "degrade_defensive"


@dataclass
class ClassifiedError:
    """Classified error token providing prescriptive recovery instructions."""
    category: ErrorCategory
    recovery: RecoveryAction
    message: str
    retry_delay: float = 0.0
    nudge_text: Optional[str] = None
    max_retries: int = 3
    reason: Optional[FailoverReason] = None

    @property
    def retryable(self) -> bool:
        """Whether this error allows any retry attempt."""
        return self.recovery not in (
            RecoveryAction.FAIL_PERMANENT,
            RecoveryAction.DEGRADE_DEFENSIVE,
        )

    @property
    def should_compress(self) -> bool:
        return self.recovery == RecoveryAction.RETRY_WITH_COMPACTION or (
            self.reason is not None and self.reason.should_compress
        )

    @property
    def should_rotate_cred(self) -> bool:
        return self.recovery == RecoveryAction.ROTATE_CREDENTIAL

    @property
    def should_fallback_model(self) -> bool:
        return self.recovery == RecoveryAction.FALLBACK_MODEL

    @property
    def is_trading_domain(self) -> bool:
        if self.reason and self.reason.is_trading_domain:
            return True
        return self.category in {
            ErrorCategory.REQUOTE,
            ErrorCategory.PARTIAL_FILL,
            ErrorCategory.MARGIN_INSUFFICIENT,
            ErrorCategory.BROKER_DISCONNECT,
            ErrorCategory.DATA_FEED_STALE,
            ErrorCategory.KILL_SWITCH_ACTIVE,
            ErrorCategory.INVARIANT_VIOLATION,
            ErrorCategory.SPREAD_TOO_WIDE,
            ErrorCategory.ORDER_TIMEOUT,
        }

    @property
    def cooldown_seconds(self) -> float:
        if self.retry_delay > 0.0:
            return self.retry_delay
        if self.reason:
            return self.reason.backoff_seconds
        return 0.0


def _extract_retry_after(exc: Exception) -> float:
    """Extract Retry-After header value from exception if available."""
    headers = getattr(exc, "headers", None)
    if headers is None:
        response_obj = getattr(exc, "response", None)
        if response_obj is not None:
            headers = getattr(response_obj, "headers", None)
    if headers and hasattr(headers, "get"):
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    return 30.0


# Pre-compiled patterns for fast classification
_COMPLETION_CEILING_PATTERNS = re.compile(
    r"max_(?:completion_)?tokens.?is.?too.?large|"
    r"completion.?tokens.?exceed|"
    r"maximum.?completion.?tokens|"
    r"max_(?:completion_)?tokens.?cannot.?exceed|"
    r"cannot.?be.?greater.?than.*max_(?:completion_)?tokens|"
    r"max_(?:completion_)?tokens.*(?:must be |cannot be )?(?:less than or equal to|<=|greater than|exceeds|too large)|"
    r"(?:must be |cannot be )?(?:less than or equal to|<=).*max_(?:completion_)?tokens|"
    r"max_completion_tokens.?exceeded|"
    r"max_(?:completion_)?tokens\s*:\s*\d+\s*>\s*\d+",
    re.IGNORECASE,
)
_HARD_QUOTA_PATTERNS = re.compile(
    r"insufficient_quota|"
    r"exceeded.?your.?current.?quota|"
    r"quota.?exceeded|"
    r"credit.?balance.?is.?too.?low|"
    r"account.?has.?run.?out.?of.?credits|"
    r"monthly.?quota.?reached|"
    r"check.?your.?plan.?and.?billing",
    re.IGNORECASE,
)
_OVERFLOW_PATTERNS = re.compile(
    r"context.?length|maximum context|prompt.?is.?too.?long|token.?limit|"
    r"content.?too.?large|exceeds.?the.?model|exceeds.?the.?maximum.?number.?of.?tokens|"
    r"request.?too.?large|413|max_tokens_exceeded",
    re.IGNORECASE,
)


class ErrorClassifier:
    """Unified error classifier diagnosing LLM provider exceptions & trading domain anomalies."""

    @classmethod
    def classify(cls, exc: Exception, response: Optional[dict] = None) -> ClassifiedError:
        status = getattr(exc, "status_code", getattr(exc, "code", None))
        if status is None:
            response_obj = getattr(exc, "response", None)
            if response_obj is not None:
                status = getattr(response_obj, "status_code", None)
        err_str = str(exc).lower()

        # Check trading domain errors first if matching signatures present
        trading_res = cls._classify_trading_string(err_str)
        if trading_res:
            return trading_res

        # Context overflow / Completion ceiling
        if status == 413 or _OVERFLOW_PATTERNS.search(err_str):
            if _COMPLETION_CEILING_PATTERNS.search(err_str):
                return ClassifiedError(
                    category=ErrorCategory.CONTEXT_OVERFLOW,
                    recovery=RecoveryAction.RETRY_WITH_COMPACTION,
                    message="Model completion ceiling exceeded. Clamping requested output tokens.",
                    reason=FailoverReason.COMPLETION_CEILING_EXCEEDED,
                )
            return ClassifiedError(
                category=ErrorCategory.CONTEXT_OVERFLOW,
                recovery=RecoveryAction.RETRY_WITH_COMPACTION,
                message="Context window exceeded. Triggering emergency compaction.",
                reason=FailoverReason.CONTEXT_OVERFLOW,
            )

        # Rate limit
        if status == 429 or "rate limit" in err_str or "too many requests" in err_str or "resource_exhausted" in err_str:
            retry_after = _extract_retry_after(exc)
            return ClassifiedError(
                category=ErrorCategory.RATE_LIMIT,
                recovery=RecoveryAction.ROTATE_CREDENTIAL,
                message="Rate limit hit. Rotating credential.",
                retry_delay=retry_after,
                reason=FailoverReason.RATE_LIMIT_API,
            )

        # Hard Quota / Billing Exhaustion
        if status == 402 or _HARD_QUOTA_PATTERNS.search(err_str):
            return ClassifiedError(
                category=ErrorCategory.BILLING_EXHAUSTION,
                recovery=RecoveryAction.FALLBACK_MODEL,
                message="Billing/quota exhausted. Switching to fallback model.",
                reason=FailoverReason.BILLING_EXHAUSTION,
            )

        # Auth Error (401, 403)
        if status in (401, 403) or "unauthorized" in err_str or "invalid_api_key" in err_str:
            if any(marker in err_str for marker in ("billing", "quota", "credit", "payment")):
                return ClassifiedError(
                    category=ErrorCategory.BILLING_EXHAUSTION,
                    recovery=RecoveryAction.FALLBACK_MODEL,
                    message="Billing/quota exhausted. Switching to fallback model.",
                    reason=FailoverReason.BILLING_EXHAUSTION,
                )
            return ClassifiedError(
                category=ErrorCategory.AUTH_ERROR,
                recovery=RecoveryAction.FAIL_PERMANENT,
                message="Authentication failed.",
                reason=FailoverReason.AUTH_PERMANENT,
            )

        # Server errors (500, 502, 503, 504, 529)
        if status in (500, 502, 503, 504, 529) or any(
            code in err_str for code in ("500 internal", "502 bad gateway", "503 service", "504 gateway", "overloaded")
        ):
            reason = FailoverReason.MODEL_OVERLOADED if (status == 529 or "overloaded" in err_str) else FailoverReason.SERVER_ERROR
            return ClassifiedError(
                category=ErrorCategory.SERVER_ERROR,
                recovery=RecoveryAction.RETRY_SAME,
                message=f"Server error {status or '5xx'}. Retrying with backoff.",
                retry_delay=5.0,
                reason=reason,
            )

        # Content refusal / Safety filter
        if any(marker in err_str for marker in ("refused", "safety", "content_policy", "content filter", "blocked")):
            return ClassifiedError(
                category=ErrorCategory.CONTENT_REFUSAL,
                recovery=RecoveryAction.FALLBACK_MODEL,
                message="Content refused by safety filter.",
                reason=FailoverReason.CONTENT_REFUSAL,
            )

        # Malformed tool arguments / JSON parse
        if "json" in err_str and ("parse" in err_str or "decode" in err_str or "syntax" in err_str or "expecting value" in err_str):
            return ClassifiedError(
                category=ErrorCategory.MALFORMED_TOOL_ARGS,
                recovery=RecoveryAction.REPAIR_AND_RETRY,
                message="Malformed JSON in tool arguments.",
                reason=FailoverReason.MALFORMED_TOOL_ARGS,
            )

        # Unicode surrogate encoding error
        if any(w in err_str for w in ("surrogate", "utf-8", "codec can't encode")):
            return ClassifiedError(
                category=ErrorCategory.MALFORMED_TOOL_ARGS,
                recovery=RecoveryAction.REPAIR_AND_RETRY,
                message="Unicode surrogate pair encoding error detected. Sanitizing text.",
                reason=FailoverReason.MALFORMED_TOOL_ARGS,
            )

        # Multimodal size rejection
        if any(w in err_str for w in ("image size", "payload too large", "unsupported image", "multimodal", "image decode")):
            return ClassifiedError(
                category=ErrorCategory.SERVER_ERROR,
                recovery=RecoveryAction.RETRY_WITH_COMPACTION,
                message="Multimodal payload rejected. Falling back to textual representation.",
                reason=FailoverReason.PAYLOAD_TOO_LARGE,
            )

        # Transient network timeouts and resets
        if any(m in err_str for m in ("timeout", "connection", "reset", "eof", "broken pipe", "timed out")):
            return ClassifiedError(
                category=ErrorCategory.TRANSIENT_NETWORK,
                recovery=RecoveryAction.RETRY_SAME,
                message="Transient network error.",
                retry_delay=3.0,
                reason=FailoverReason.TRANSIENT_NETWORK,
            )

        return ClassifiedError(
            category=ErrorCategory.UNKNOWN,
            recovery=RecoveryAction.FAIL_PERMANENT,
            message=f"Unknown error: {str(exc)[:200]}",
            reason=FailoverReason.UNKNOWN,
        )

    @staticmethod
    def _classify_trading_string(err_str: str) -> Optional[ClassifiedError]:
        """Sub-classifier for trading and MT5 broker error strings."""
        if "requote" in err_str or "10004" in err_str:
            return ClassifiedError(
                category=ErrorCategory.REQUOTE,
                recovery=RecoveryAction.RETRY_SAME,
                message="MT5 requote received. Refreshing quotes and retrying.",
                retry_delay=1.0,
                reason=FailoverReason.REQUOTE,
            )
        if "partial" in err_str and ("fill" in err_str or "execution" in err_str):
            return ClassifiedError(
                category=ErrorCategory.PARTIAL_FILL,
                recovery=RecoveryAction.COOLDOWN_AND_RETRY,
                message="Partial fill executed. Tracking remaining volume.",
                reason=FailoverReason.PARTIAL_FILL,
            )
        if any(m in err_str for m in ("not enough money", "margin", "10019", "margin_insufficient")):
            return ClassifiedError(
                category=ErrorCategory.MARGIN_INSUFFICIENT,
                recovery=RecoveryAction.FAIL_PERMANENT,
                message="Insufficient margin for requested lot size.",
                reason=FailoverReason.MARGIN_INSUFFICIENT,
            )
        if any(m in err_str for m in ("disconnected", "terminal not responding", "connection lost", "broker_disconnect")):
            return ClassifiedError(
                category=ErrorCategory.BROKER_DISCONNECT,
                recovery=RecoveryAction.RETRY_SAME,
                message="MT5 terminal disconnected. Attempting auto-reconnect.",
                retry_delay=5.0,
                reason=FailoverReason.BROKER_DISCONNECT,
            )
        if "kill_switch" in err_str or "emergency stop" in err_str or "kill switch active" in err_str:
            return ClassifiedError(
                category=ErrorCategory.KILL_SWITCH_ACTIVE,
                recovery=RecoveryAction.FAIL_PERMANENT,
                message="Trading halt: Kill-switch is currently active.",
                reason=FailoverReason.KILL_SWITCH_ACTIVE,
            )
        if "invariant" in err_str or "sl < entry" in err_str or "sl > entry" in err_str:
            return ClassifiedError(
                category=ErrorCategory.INVARIANT_VIOLATION,
                recovery=RecoveryAction.FAIL_PERMANENT,
                message="Order geometry invariant violated.",
                reason=FailoverReason.INVARIANT_VIOLATION,
            )
        if "spread too wide" in err_str or "spread ceiling" in err_str:
            return ClassifiedError(
                category=ErrorCategory.SPREAD_TOO_WIDE,
                recovery=RecoveryAction.COOLDOWN_AND_RETRY,
                message="Market spread exceeds permissible ceiling.",
                retry_delay=15.0,
                reason=FailoverReason.SPREAD_TOO_WIDE,
            )
        if "stale feed" in err_str or "data_feed_stale" in err_str:
            return ClassifiedError(
                category=ErrorCategory.DATA_FEED_STALE,
                recovery=RecoveryAction.DEGRADE_DEFENSIVE,
                message="Market or macro data feed is stale. Degrading to defensive mode.",
                retry_delay=10.0,
                reason=FailoverReason.DATA_FEED_STALE,
            )
        return None

    @classmethod
    def classify_trading_error(cls, exc_or_code: Union[Exception, int, str], context: Optional[dict] = None) -> ClassifiedError:
        """Dedicated classifier for MT5 return codes and execution exceptions."""
        code_str = str(exc_or_code).lower()

        # MT5 Return Codes Mapping
        if code_str == "10004" or "requote" in code_str:
            return ClassifiedError(
                category=ErrorCategory.REQUOTE,
                recovery=RecoveryAction.RETRY_SAME,
                message="MT5 Requote (10004). Re-fetching tick price.",
                retry_delay=1.0,
                reason=FailoverReason.REQUOTE,
            )
        if code_str == "10019" or "margin" in code_str:
            return ClassifiedError(
                category=ErrorCategory.MARGIN_INSUFFICIENT,
                recovery=RecoveryAction.FAIL_PERMANENT,
                message="MT5 Insufficient Margin (10019).",
                reason=FailoverReason.MARGIN_INSUFFICIENT,
            )
        if code_str in ("10006", "10007") or "rejected" in code_str:
            return ClassifiedError(
                category=ErrorCategory.UNKNOWN,
                recovery=RecoveryAction.FAIL_PERMANENT,
                message=f"MT5 Order Rejected ({code_str}).",
                reason=FailoverReason.INVALID_REQUEST,
            )
        if "timeout" in code_str:
            return ClassifiedError(
                category=ErrorCategory.ORDER_TIMEOUT,
                recovery=RecoveryAction.RETRY_SAME,
                message="MT5 Order Send Timeout.",
                retry_delay=2.0,
                reason=FailoverReason.ORDER_TIMEOUT,
            )

        res = cls._classify_trading_string(code_str)
        if res:
            return res

        return ClassifiedError(
            category=ErrorCategory.UNKNOWN,
            recovery=RecoveryAction.FAIL_PERMANENT,
            message=f"Unclassified trading error: {code_str}",
            reason=FailoverReason.UNKNOWN,
        )

    @staticmethod
    def classify_response(response: dict) -> Optional[ClassifiedError]:
        """Classify issues from a successful but problematic response."""
        stop_reason = (response.get("stop_reason") or response.get("finish_reason") or "").lower()
        content = response.get("content") or ""
        tool_calls = response.get("tool_calls") or []
        thinking = response.get("reasoning") or response.get("thinking") or response.get("reasoning_content") or ""

        # Output truncation
        if stop_reason in ("length", "max_tokens"):
            if tool_calls:
                return ClassifiedError(
                    category=ErrorCategory.OUTPUT_TRUNCATION,
                    recovery=RecoveryAction.INJECT_NUDGE,
                    message="Response truncated with pending tool calls.",
                    nudge_text="[System: Your response was truncated. Tool calls were NOT executed. Reduce reasoning and re-issue tool calls.]",
                    reason=FailoverReason.OUTPUT_TRUNCATION,
                )
            return ClassifiedError(
                category=ErrorCategory.OUTPUT_TRUNCATION,
                recovery=RecoveryAction.INJECT_CONTINUATION,
                message="Response truncated mid-content.",
                nudge_text="[System: Your response was truncated. Continue exactly where you left off.]",
                reason=FailoverReason.OUTPUT_TRUNCATION,
            )

        # Thinking budget exhaustion
        if thinking and not content and not tool_calls:
            return ClassifiedError(
                category=ErrorCategory.THINKING_EXHAUSTION,
                recovery=RecoveryAction.RETRY_WITH_REDUCED_EFFORT,
                message="Thinking consumed all output tokens. No content produced.",
                reason=FailoverReason.THINKING_EXHAUSTION,
            )

        # Dropped tool call
        content_str = content if isinstance(content, str) else str(content)
        if not tool_calls and any(
            phrase in content_str.lower()
            for phrase in ("i'll call", "let me use", "i will use the", "calling the", "i'm going to call")
        ):
            return ClassifiedError(
                category=ErrorCategory.DROPPED_TOOL_CALL,
                recovery=RecoveryAction.INJECT_NUDGE,
                message="Model narrated a tool call but didn't issue one.",
                nudge_text="[System: You described a tool call but did not issue one. Issue the actual tool call now. Do not narrate.]",
                reason=FailoverReason.DROPPED_TOOL_CALL,
            )

        return None
