# ==============================================================================
# File: utils/security/supply_chain_quarantine.py
# ==============================================================================

"""
Backward-compatibility re-export shim for supply_chain_quarantine.
Canonical location: security.supply_chain_quarantine
"""

from security.supply_chain_quarantine import (
    CRITICAL_CORE_LIBRARIES,
    DEFAULT_QUARANTINE_DAYS,
    QuarantineVerdict,
    SupplyChainQuarantine,
)

__all__ = [
    "CRITICAL_CORE_LIBRARIES",
    "DEFAULT_QUARANTINE_DAYS",
    "QuarantineVerdict",
    "SupplyChainQuarantine",
]
