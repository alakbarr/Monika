# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.brokers.broker_adapter
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.brokers.broker_adapter"""

import sys
import monika.infrastructure.brokers.broker_adapter as _canonical

from monika.infrastructure.brokers.broker_adapter import (
    BrokerAdapter,
    MT5LiveAdapter,
    MT5RemoteGatewayAdapter,
    SimulatedBrokerAdapter,
    _get_contract_size,
    _get_pip_size,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "BrokerAdapter",
    "MT5LiveAdapter",
    "MT5RemoteGatewayAdapter",
    "SimulatedBrokerAdapter",
    "_get_contract_size",
    "_get_pip_size",
    "logger",
]
