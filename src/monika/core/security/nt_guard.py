# ==============================================================================
# File: security/nt_guard.py
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


# Windows DOS device names that cause deadlock/hang or access raw devices
DOS_DEVICE_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)


def is_dangerous_nt_namespace(path_input: Union[str, Path]) -> bool:
    """
    Check if a raw path uses Windows NT-namespace or extended UNC prefix.
    Detects:
      - \\??\\ (NT object manager namespace)
      - \\\\.\\ (Device namespace)
      - \\\\?\\UNC\\ (Extended UNC share path)
      - \\\\?\\GLOBALROOT\\ (Direct kernel device reference)
      - Trailing/embedded null bytes (%00)
      - Windows legacy DOS device names (CON, NUL, AUX, PRN, COM1-9, LPT1-9)
    """
    if path_input is None:
        return False

    raw = str(path_input).strip("\"' \t\r\n")
    if "\x00" in raw or "%00" in raw:
        return True

    # Normalize forward slashes to backward slashes for uniform NT prefix check
    normalized = raw.replace("/", "\\").strip("\"' \t\r\n")

    if normalized.startswith("\\??\\"):
        return True
    # Block all UNC network shares (\\server\share, //server/share) and NT device namespaces (\\.\, \\?\)
    if normalized.startswith("\\\\"):
        return True

    # Check for Windows legacy DOS device names in path components
    for part in normalized.split("\\"):
        stem = part.split(".")[0].strip().upper()
        if stem in DOS_DEVICE_NAMES:
            return True

    return False


def assert_safe_nt_path(path_input: Union[str, Path]) -> str:
    """
    Assert that the path is not a dangerous NT-namespace path.
    Returns string representation of safe path or raises SecurityViolationError.
    """
    if is_dangerous_nt_namespace(path_input):
        raise SecurityViolationError(f"Access denied: Dangerous Windows NT-namespace path detected: '{path_input}'.")
    return str(path_input).strip("\"'")


sanitize_path = assert_safe_nt_path
