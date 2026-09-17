"""
Structured error classification and recovery strategy assignment (Phase 3).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any, Dict, List
import copy
import logging
import re

logger = logging.getLogger("TradingAgent.Harness.ErrorClassifier")

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


class ErrorCategory(Enum):
    CONTEXT_OVERFLOW = "context_overflow"       # 413, context too long
    RATE_LIMIT = "rate_limit"                   # 429, too many requests
    AUTH_ERROR = "auth_error"                   # 401, 403
    SERVER_ERROR = "server_error"               # 500, 502, 503, 504
    OUTPUT_TRUNCATION = "output_truncation"     # finish_reason == "length"
    THINKING_EXHAUSTION = "thinking_exhaustion" # All tokens used in <think>
    CONTENT_REFUSAL = "content_refusal"         # Safety filter block
    BILLING_EXHAUSTION = "billing_exhaustion"   # Credit/quota exhausted
    DROPPED_TOOL_CALL = "dropped_tool_call"     # Model said it would call tool but didn't
    MALFORMED_TOOL_ARGS = "malformed_tool_args" # Invalid JSON in tool arguments
    TRANSIENT_NETWORK = "transient_network"     # Connection reset, timeout
    UNKNOWN = "unknown"


class RecoveryAction(Enum):
    RETRY_SAME = "retry_same"
    RETRY_WITH_COMPACTION = "retry_with_compaction"
    RETRY_WITH_REDUCED_EFFORT = "retry_with_reduced_effort"
    ROTATE_CREDENTIAL = "rotate_credential"
    FALLBACK_MODEL = "fallback_model"
    INJECT_NUDGE = "inject_nudge"
    INJECT_CONTINUATION = "inject_continuation"
    REPAIR_AND_RETRY = "repair_and_retry"
    FAIL_PERMANENT = "fail_permanent"


@dataclass
class ClassifiedError:
    category: ErrorCategory
    recovery: RecoveryAction
    message: str
    retry_delay: float = 0.0
    nudge_text: Optional[str] = None
    max_retries: int = 3


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


class ErrorClassifier:
    """Classifies LLM/API errors and assigns recovery strategies."""

    @staticmethod
    def classify(exc: Exception, response: Optional[dict] = None) -> ClassifiedError:
        status = getattr(exc, "status_code", getattr(exc, "code", None))
        if status is None:
            response_obj = getattr(exc, "response", None)
            if response_obj is not None:
                status = getattr(response_obj, "status_code", None)
        err_str = str(exc).lower()

        # Context overflow
        if status == 413 or (
            ("context" in err_str or "prompt" in err_str or "token" in err_str)
            and ("too long" in err_str or "exceeded" in err_str or "limit" in err_str or "maximum" in err_str)
        ):
            return ClassifiedError(
                category=ErrorCategory.CONTEXT_OVERFLOW,
                recovery=RecoveryAction.RETRY_WITH_COMPACTION,
                message="Context window exceeded. Triggering emergency compaction.",
            )

        # Rate limit
        if status == 429 or "rate limit" in err_str or "too many requests" in err_str or "resource_exhausted" in err_str:
            retry_after = _extract_retry_after(exc)
            return ClassifiedError(
                category=ErrorCategory.RATE_LIMIT,
                recovery=RecoveryAction.ROTATE_CREDENTIAL,
                message="Rate limit hit. Rotating credential.",
                retry_delay=retry_after,
            )

        # Auth / Billing
        if status in (401, 403) or "unauthorized" in err_str or "invalid_api_key" in err_str:
            if "billing" in err_str or "quota" in err_str or "credit" in err_str or "payment" in err_str:
                return ClassifiedError(
                    category=ErrorCategory.BILLING_EXHAUSTION,
                    recovery=RecoveryAction.FALLBACK_MODEL,
                    message="Billing/quota exhausted. Switching to fallback model.",
                )
            return ClassifiedError(
                category=ErrorCategory.AUTH_ERROR,
                recovery=RecoveryAction.FAIL_PERMANENT,
                message="Authentication failed.",
            )
        if status == 402 or "insufficient quota" in err_str or "quota exceeded" in err_str:
            return ClassifiedError(
                category=ErrorCategory.BILLING_EXHAUSTION,
                recovery=RecoveryAction.FALLBACK_MODEL,
                message="Billing/quota exhausted. Switching to fallback model.",
            )

        # Server errors
        if status in (500, 502, 503, 504, 529) or any(
            code in err_str for code in ("500 internal", "502 bad gateway", "503 service", "504 gateway", "overloaded")
        ):
            return ClassifiedError(
                category=ErrorCategory.SERVER_ERROR,
                recovery=RecoveryAction.RETRY_SAME,
                message=f"Server error {status or '5xx'}. Retrying with backoff.",
                retry_delay=5.0,
            )

        # Content refusal
        if "refused" in err_str or "safety" in err_str or "content_policy" in err_str or "content filter" in err_str or "blocked" in err_str:
            return ClassifiedError(
                category=ErrorCategory.CONTENT_REFUSAL,
                recovery=RecoveryAction.FALLBACK_MODEL,
                message="Content refused by safety filter.",
            )

        # Malformed tool arguments
        if "json" in err_str and ("parse" in err_str or "decode" in err_str or "syntax" in err_str or "expecting value" in err_str):
            return ClassifiedError(
                category=ErrorCategory.MALFORMED_TOOL_ARGS,
                recovery=RecoveryAction.REPAIR_AND_RETRY,
                message="Malformed JSON in tool arguments.",
            )

        # Unicode surrogate or serialization error (HIGH-7)
        if "surrogate" in err_str or "utf-8" in err_str or "codec can't encode" in err_str:
            return ClassifiedError(
                category=ErrorCategory.MALFORMED_TOOL_ARGS,
                recovery=RecoveryAction.REPAIR_AND_RETRY,
                message="Unicode surrogate pair encoding error detected. Sanitizing text.",
            )

        # Multimodal size or format rejection (HIGH-7)
        if any(w in err_str for w in ("image size", "payload too large", "unsupported image", "multimodal", "image decode")):
            return ClassifiedError(
                category=ErrorCategory.SERVER_ERROR,
                recovery=RecoveryAction.RETRY_WITH_COMPACTION,
                message="Multimodal payload rejected. Falling back to textual representation.",
            )

        # Network transient
        if any(m in err_str for m in ("timeout", "connection", "reset", "eof", "broken pipe", "timed out")):
            return ClassifiedError(
                category=ErrorCategory.TRANSIENT_NETWORK,
                recovery=RecoveryAction.RETRY_SAME,
                message="Transient network error.",
                retry_delay=3.0,
            )

        return ClassifiedError(
            category=ErrorCategory.UNKNOWN,
            recovery=RecoveryAction.FAIL_PERMANENT,
            message=f"Unknown error: {str(exc)[:200]}",
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
                )
            return ClassifiedError(
                category=ErrorCategory.OUTPUT_TRUNCATION,
                recovery=RecoveryAction.INJECT_CONTINUATION,
                message="Response truncated mid-content.",
                nudge_text="[System: Your response was truncated. Continue exactly where you left off.]",
            )

        # Thinking budget exhaustion
        if thinking and not content and not tool_calls:
            return ClassifiedError(
                category=ErrorCategory.THINKING_EXHAUSTION,
                recovery=RecoveryAction.RETRY_WITH_REDUCED_EFFORT,
                message="Thinking consumed all output tokens. No content produced.",
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
            )

        return None
