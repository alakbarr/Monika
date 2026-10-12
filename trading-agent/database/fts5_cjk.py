# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.fts5_cjk
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.fts5_cjk"""

import sys
import monika.infrastructure.database.fts5_cjk as _canonical

from monika.infrastructure.database.fts5_cjk import (
    Fts5SessionSearch,
    _CJK_REGEX,
    _FTS5_SPECIAL_CHARS,
    logger,
    sanitize_fts5_term,
    tokenize_cjk_bigram,
)

sys.modules[__name__] = _canonical

__all__ = [
    "Fts5SessionSearch",
    "_CJK_REGEX",
    "_FTS5_SPECIAL_CHARS",
    "logger",
    "sanitize_fts5_term",
    "tokenize_cjk_bigram",
]
