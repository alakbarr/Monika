"""
File: config/security.py
Security validation and environment mutation guards for Monika.
Prevents unauthorized modifications to critical system variables.
"""

from typing import FrozenSet

BLOCKED_ENV_VARS: FrozenSet[str] = frozenset({
    "PATH", "PYTHONPATH", "LD_PRELOAD", "SHELL", "COMSPEC",
    "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "DATABASE_URL"
})


def validate_env_mutation(key: str) -> None:
    """Validates whether an environment variable is safe to mutate via CLI/API.
    
    Raises:
        ValueError: If key is in the security blocked denylist.
    """
    if key.upper() in BLOCKED_ENV_VARS:
        raise ValueError(
            f"Modifikasi variabel lingkungan '{key}' dilarang demi keamanan sistem."
        )
