"""
Compatibility facade shim for legacy ssrf_guard.py.
Re-exports from canonical monika.core.security.ssrf_guard.
"""

from __future__ import annotations

import monika.core.security.ssrf_guard as _canonical

from monika.core.security.ssrf_guard import (
    ALLOWED_DEFAULT_PORTS,
    BLOCKED_HOSTNAMES,
    BLOCKED_NETWORKS,
    SAFE_SCHEMES,
    SSRFViolationError,
    is_ip_private_or_reserved,
    is_url_safe,
    logger,
    validate_request_url,
)

__all__ = ['ALLOWED_DEFAULT_PORTS', 'BLOCKED_HOSTNAMES', 'BLOCKED_NETWORKS', 'SAFE_SCHEMES', 'SSRFViolationError', 'is_ip_private_or_reserved', 'is_url_safe', 'logger', 'validate_request_url']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
