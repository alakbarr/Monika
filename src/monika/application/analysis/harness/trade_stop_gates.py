"""
Backward-compatibility facade for trade_stop_gates.
Canonical location: monika.application.agent.harness.trade_stop_gates
"""

import sys
import monika.application.agent.harness.trade_stop_gates as _canonical

from monika.application.agent.harness.trade_stop_gates import (
    TradeStopGate,
    TradeStopVerdict,
)

__all__ = ["TradeStopGate", "TradeStopVerdict"]

sys.modules[__name__] = _canonical
