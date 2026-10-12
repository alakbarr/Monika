# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.structured_fallback
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.structured_fallback"""

import sys
import monika.infrastructure.providers.structured_fallback as _canonical

from monika.infrastructure.providers.structured_fallback import (
    StructuredOutputResult,
    extract_key_values_by_regex,
    invoke_structured_or_freetext,
    logger,
    parse_structured_output,
)

sys.modules[__name__] = _canonical

__all__ = [
    "StructuredOutputResult",
    "extract_key_values_by_regex",
    "invoke_structured_or_freetext",
    "logger",
    "parse_structured_output",
]
