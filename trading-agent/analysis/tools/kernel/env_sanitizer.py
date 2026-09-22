# ==============================================================================
# File: analysis/tools/kernel/env_sanitizer.py
# Description: Subprocess Environment Sanitizer & Credential Leakage Shield
# ==============================================================================

"""
Strict environment variable scrubbing for programmatic tool execution and subprocesses.
Guarantees that broker passwords, database connections, and API keys are never leaked
into user-facing script runners or arbitrary code execution environments.
"""

import os
import sys
import logging
from typing import Dict, Optional

logger = logging.getLogger("TradingAgent.Tools.EnvSanitizer")

# Patterns to strictly purge from child process environments
SENSITIVE_PATTERNS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "AUTH",
    "DSN",
    "WEBHOOK",
    "CREDS",
    "BEARER",
    "APIKEY",
    "DATABASE",
    "POSTGRES",
    "MT5",
    "TELEGRAM",
)

# Essential system environment variables allowed to pass through
SAFE_SYSTEM_KEYS = frozenset({
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONUTF8",
    "PYTHONIOENCODING",
    "HOMEDRIVE",
    "HOMEPATH",
    "USERPROFILE",
})


def get_sanitized_environment(base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Produce a scrubbed environment dictionary for child process execution.
    Removes all broker, database, and API credentials.
    """
    source = base_env if base_env is not None else os.environ
    sanitized: Dict[str, str] = {}

    for k, v in source.items():
        k_upper = k.upper()
        # Allow safe system essentials
        if k_upper in SAFE_SYSTEM_KEYS:
            sanitized[k] = v
            continue

        # Purge any key matching sensitive patterns
        if any(pat in k_upper for pat in SENSITIVE_PATTERNS):
            continue

        sanitized[k] = v

    return sanitized


# Alias for backward compatibility
sanitize_environment = get_sanitized_environment
