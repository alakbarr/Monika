"""
Backward-compatibility facade for message_repair.
Canonical location: monika.application.agent.harness.message_repair
"""

import sys
import monika.application.agent.harness.message_repair as _canonical

from monika.application.agent.harness.message_repair import repair_message_history

__all__ = ["repair_message_history"]

sys.modules[__name__] = _canonical
