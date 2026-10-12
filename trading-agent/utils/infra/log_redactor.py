"""
Compatibility facade shim for legacy log_redactor.py.
Re-exports from canonical monika.infrastructure.infra.log_redactor.
"""

from __future__ import annotations

import monika.infrastructure.infra.log_redactor as _canonical

from monika.infrastructure.infra.log_redactor import (
    RedactingFormatter,
    redact_sensitive_text,
)

__all__ = ['RedactingFormatter', 'redact_sensitive_text']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
