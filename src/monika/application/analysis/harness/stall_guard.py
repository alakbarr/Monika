"""
Backward-compatibility facade for StallGuard.
Canonical location: monika.application.agent.harness.stall_guard
"""

import sys
import monika.application.agent.harness.stall_guard as _canonical

from monika.application.agent.harness.stall_guard import StallGuard

__all__ = ["StallGuard"]

sys.modules[__name__] = _canonical
