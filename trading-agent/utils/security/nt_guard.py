# ==============================================================================
# File: utils/security/nt_guard.py
# ==============================================================================

"""
Backward-compatibility re-export shim for nt_guard.
Canonical location: security.nt_guard
"""

from security.nt_guard import (
    SecurityViolationError,
    assert_safe_nt_path,
    is_dangerous_nt_namespace,
    sanitize_path,
)

__all__ = [
    "SecurityViolationError",
    "assert_safe_nt_path",
    "is_dangerous_nt_namespace",
    "sanitize_path",
]
