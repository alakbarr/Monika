# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.brokers.rate_throttler
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.brokers.rate_throttler"""

import sys
import monika.infrastructure.brokers.rate_throttler as _canonical

from monika.infrastructure.brokers.rate_throttler import (
    RateThrottler,
    ThrottleVerdict,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "RateThrottler",
    "ThrottleVerdict",
    "logger",
]
