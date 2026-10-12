# ==============================================================================
# File: services/market_intel_service.py
# Description: Compatibility re-export shim for monika.application.services.market_intel_service
# ==============================================================================

"""
Backward-compatibility re-export shim.
Canonical implementation: monika.application.services.market_intel_service
"""

from monika.application.services.market_intel_service import MarketIntelService

__all__ = [
    "MarketIntelService",
]
