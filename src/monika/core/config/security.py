"""
File: config/security.py
Security validation and environment mutation guards for Monika.
Prevents unauthorized modifications to critical system variables.
"""

from typing import FrozenSet

BLOCKED_ENV_VARS: frozenset[str] = frozenset(
    {
        "PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        "SHELL",
        "COMSPEC",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "DATABASE_URL",
        "MONIKA_WRITE_SAFE_ROOT",
        "MONIKA_VAULT_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    }
)


def validate_env_mutation(key: str) -> None:
    """Validates whether an environment variable is safe to mutate via CLI/API.

    Raises:
        ValueError: If key is in the security blocked denylist.
    """
    if key.upper() in BLOCKED_ENV_VARS:
        raise ValueError(f"Modifikasi variabel lingkungan '{key}' dilarang demi keamanan sistem.")
