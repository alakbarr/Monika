"""
Backward-compatibility facade for message_repair.
Canonical location: monika.application.agent.harness.message_repair
"""

import sys
import monika.application.agent.harness.message_repair as _canonical

from monika.application.agent.harness.message_repair import (
    repair_message_history,
    transform_messages_for_target_model,
)

__all__ = ["repair_message_history", "transform_messages_for_target_model"]

sys.modules[__name__] = _canonical
