"""
Backward-compatibility facade for Agent Harness.
Canonical location: monika.application.agent.harness
"""

import sys
import monika.application.agent.harness as _canonical

from monika.application.agent.harness.agent_harness import AgentHarness

__all__ = ["AgentHarness"]

sys.modules[__name__] = _canonical
