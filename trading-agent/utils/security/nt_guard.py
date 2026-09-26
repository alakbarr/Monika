# ==============================================================================
# File: utils/security/nt_guard.py
# ==============================================================================

"""
Windows NT-Namespace & Extended UNC Path Guard.
Protects against SMB/WebDAV NTLM hash theft vectors and path normalization bypasses
caused by raw NT-namespace paths (\\??\\, \\\\.\\, \\\\?\\UNC\\, \\\\?\\GLOBALROOT\\).
"""

from pathlib import Path
from typing import Union


class SecurityViolationError(PermissionError):
    """Raised when an operation violates host security boundaries."""
    pass


def is_dangerous_nt_namespace(path_input: Union[str, Path]) -> bool:
    """
    Check if a raw path uses Windows NT-namespace or extended UNC prefix.
    Detects:
      - \\??\\ (NT object manager namespace)
      - \\\\.\\ (Device namespace)
      - \\\\?\\UNC\\ (Extended UNC share path)
      - \\\\?\\GLOBALROOT\\ (Direct kernel device reference)
      - Trailing/embedded null bytes (%00)
    """
    if path_input is None:
        return False

    raw = str(path_input)
    if "\x00" in raw or "%00" in raw:
        return True

    # Normalize forward slashes to backward slashes for uniform NT prefix check
    normalized = raw.replace("/", "\\").strip()

    if normalized.startswith("\\??\\"):
        return True
    if normalized.startswith("\\\\.\\"):
        return True
    if normalized.startswith("\\\\?\\"):
        upper = normalized[4:].upper()
        if upper.startswith("UNC\\") or upper.startswith("GLOBALROOT\\") or upper.startswith("GLOBAL??\\"):
            return True

    return False


def assert_safe_nt_path(path_input: Union[str, Path]) -> str:
    """
    Assert that the path is not a dangerous NT-namespace path.
    Returns string representation of safe path or raises SecurityViolationError.
    """
    if is_dangerous_nt_namespace(path_input):
        raise SecurityViolationError(
            f"Access denied: Dangerous Windows NT-namespace path detected: '{path_input}'."
        )
    return str(path_input)


sanitize_path = assert_safe_nt_path
