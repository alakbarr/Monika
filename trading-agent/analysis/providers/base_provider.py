# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.base_provider
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.base_provider"""

import sys
import monika.infrastructure.providers.base_provider as _canonical

from monika.infrastructure.providers.base_provider import (
    BaseLLMClient,
    MockBlock,
    MockResponse,
    _flatten_system_prompt,
    _flush_token_usage_worker,
    _get_token_usage_queue,
    _token_flush_task,
    _token_usage_queue,
    extract_and_parse_json,
    extract_retry_after,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "BaseLLMClient",
    "MockBlock",
    "MockResponse",
    "_flatten_system_prompt",
    "_flush_token_usage_worker",
    "_get_token_usage_queue",
    "_token_flush_task",
    "_token_usage_queue",
    "extract_and_parse_json",
    "extract_retry_after",
    "logger",
]
