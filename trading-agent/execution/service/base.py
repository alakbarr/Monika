# ==============================================================================
# File: execution/service/base.py
# Description: Backward-compatibility shim for monika.domain.execution.base
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.execution.base
"""

import sys
import monika.domain.execution.base as _canonical

from monika.domain.execution.base import (
    _ExecutionServiceMixinBase,
)

sys.modules[__name__] = _canonical

__all__ = [
    "_ExecutionServiceMixinBase",
]
