"""
Compatibility facade shim for legacy session.py.
Re-exports from canonical monika.interfaces.cli.chat.session.
"""

from __future__ import annotations

import monika.interfaces.cli.chat.session as _canonical

from monika.interfaces.cli.chat.session import (
    ChatReplSession,
    DEFAULT_API_URL,
    acquire_cli_session_lock,
    logger,
    release_cli_session_lock,
)

__all__ = ['ChatReplSession', 'DEFAULT_API_URL', 'acquire_cli_session_lock', 'logger', 'release_cli_session_lock']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
