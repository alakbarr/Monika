"""
Backward-compatibility facade for structured_output.
Canonical location: monika.application.agent.harness.structured_output
"""

import sys
import monika.application.agent.harness.structured_output as _canonical

from monika.application.agent.harness.structured_output import invoke_structured_or_freetext

__all__ = ["invoke_structured_or_freetext"]

sys.modules[__name__] = _canonical
