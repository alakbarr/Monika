"""
Compatibility facade shim for legacy web_reader.py.
Re-exports from canonical monika.infrastructure.data_ingestion.sources.web_reader.
"""

from __future__ import annotations

import sys as _sys
import monika.infrastructure.data_ingestion.sources.web_reader as _canonical

from monika.infrastructure.data_ingestion.sources.web_reader import (
    CHALLENGE_PHRASES,
    DEFAULT_HEADERS,
    DISALLOWED_TAGS,
    MAX_BODY_BYTES,
    WebReader,
    is_challenge_or_empty,
    is_prohibited_ip,
    logger,
    validate_url_ip,
)

__all__ = ['CHALLENGE_PHRASES', 'DEFAULT_HEADERS', 'DISALLOWED_TAGS', 'MAX_BODY_BYTES', 'WebReader', 'is_challenge_or_empty', 'is_prohibited_ip', 'logger', 'validate_url_ip']

# Module identity forwarding
_sys.modules[__name__] = _canonical

# Attribute forwarding fallback
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)
