# ==============================================================================
# File: execution/verification_engine.py
# Description: Backward-compatibility shim for monika.domain.execution.verification_engine
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.execution.verification_engine
"""

import sys
import monika.domain.execution.verification_engine as _canonical

from monika.domain.execution.verification_engine import (
    EvidenceFirstVerifier,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "EvidenceFirstVerifier",
    "logger",
]
