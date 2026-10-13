"""
Backward-compatibility facade for repetition_guard.
Canonical location: monika.application.agent.harness.repetition_guard
"""

import sys
import monika.application.agent.harness.repetition_guard as _canonical

from monika.application.agent.harness.repetition_guard import detect_text_repetition

__all__ = ["detect_text_repetition"]

sys.modules[__name__] = _canonical
