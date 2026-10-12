# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.provider_profile
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.provider_profile"""

import sys
import monika.infrastructure.providers.provider_profile as _canonical

from monika.infrastructure.providers.provider_profile import (
    NormalizedResponse,
    NormalizedToolCall,
    ProviderProfile,
    TokenUsage,
    _PROVIDER_PROFILES,
    _THINK_TAG_REGEX,
    get_provider_profile,
)

sys.modules[__name__] = _canonical

__all__ = [
    "NormalizedResponse",
    "NormalizedToolCall",
    "ProviderProfile",
    "TokenUsage",
    "_PROVIDER_PROFILES",
    "_THINK_TAG_REGEX",
    "get_provider_profile",
]
