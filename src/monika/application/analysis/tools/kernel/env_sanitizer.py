# ==============================================================================
# File: analysis/tools/kernel/env_sanitizer.py
# Description: Subprocess Environment Sanitizer & Credential Leakage Shield
# ==============================================================================

"""
Backward compatibility facade for Subprocess Environment Sanitizer.
Canonical implementation is now in monika.core.security.env_sanitizer.
"""

from monika.core.security.env_sanitizer import (
    SAFE_SYSTEM_KEYS,
    SENSITIVE_PATTERNS,
    get_sanitized_environment,
    sanitize_environment,
)

__all__ = [
    "SENSITIVE_PATTERNS",
    "SAFE_SYSTEM_KEYS",
    "get_sanitized_environment",
    "sanitize_environment",
]
