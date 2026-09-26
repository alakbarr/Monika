# ==============================================================================
# File: agent/thinking_timeout_guidance.py
# ==============================================================================

"""
Reasoning Model Timeout Diagnostic & Mitigation Guidance.
Identifies reverse-proxy idle disconnects during extended thinking phases
and provides actionable configuration recommendations.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger("TradingAgent.Agent.ThinkingTimeoutGuidance")

_PROXY_IDLE_DISCONNECT_PATTERNS = [
    re.compile(r"broken pipe", re.IGNORECASE),
    re.compile(r"connection reset by peer", re.IGNORECASE),
    re.compile(r"errno 32", re.IGNORECASE),
    re.compile(r"errno 104", re.IGNORECASE),
    re.compile(r"peer closed connection", re.IGNORECASE),
    re.compile(r"incomplete read", re.IGNORECASE),
    re.compile(r"remoteprotocolerror", re.IGNORECASE),
]

_REASONING_MODEL_HINTS = [
    "deepseek-reasoner",
    "deepseek-r1",
    "o1",
    "o3",
    "claude-3-7-sonnet",
    "nemotron",
    "qwq",
]


def detect_thinking_timeout(
    error_message: str,
    model_name: Optional[str] = None,
    elapsed_seconds: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether an API disconnection was caused by proxy idle timeout
    during a prolonged model thinking phase.
    """
    if not error_message:
        return False, None

    is_disconnect = any(pat.search(error_message) for pat in _PROXY_IDLE_DISCONNECT_PATTERNS)
    if not is_disconnect:
        return False, None

    model_lower = (model_name or "").lower()
    is_reasoning_model = any(hint in model_lower for hint in _REASONING_MODEL_HINTS)

    # If it was a reasoning model and disconnected after a delay
    if is_reasoning_model or (elapsed_seconds and elapsed_seconds >= 30.0):
        guidance = (
            f"Detected reverse-proxy idle timeout during model reasoning phase ({elapsed_seconds or 0:.1f}s). "
            "The upstream gateway closed the connection because no tokens were emitted while thinking. "
            "Mitigation: Increase proxy idle timeout to 300s+ or configure a lower thinking budget."
        )
        return True, guidance

    return False, None
