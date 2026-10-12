"""
Compatibility facade shim for legacy terminal_guard.py.
Re-exports from canonical monika.core.security.terminal_guard.
"""

from __future__ import annotations

import monika.core.security.terminal_guard as _canonical

from monika.core.security.terminal_guard import (
    CommandSecurityViolationError,
    DenialCircuitBreaker,
    HARDLINE_BLOCKLIST_PATTERNS,
    assert_safe_read_path,
    assert_safe_write_path,
    deobfuscate_command,
    is_hardline_blocked_command,
    is_secret_credential_file,
    unwrap_command_quotes,
    validate_command,
)

__all__ = ['CommandSecurityViolationError', 'DenialCircuitBreaker', 'HARDLINE_BLOCKLIST_PATTERNS', 'assert_safe_read_path', 'assert_safe_write_path', 'deobfuscate_command', 'is_hardline_blocked_command', 'is_secret_credential_file', 'unwrap_command_quotes', 'validate_command']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
