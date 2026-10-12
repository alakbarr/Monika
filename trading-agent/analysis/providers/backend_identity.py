# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.backend_identity
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.backend_identity"""

import sys
import monika.infrastructure.providers.backend_identity as _canonical

from monika.infrastructure.providers.backend_identity import (
    BackendIdentity,
    FailoverCandidateSkipper,
    FailureScope,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "BackendIdentity",
    "FailoverCandidateSkipper",
    "FailureScope",
    "logger",
]
