# ==============================================================================
# File: services/general_harness_service.py
# Description: Compatibility re-export shim for monika.application.services.general_harness_service
# ==============================================================================

"""
Backward-compatibility re-export shim.
Canonical implementation: monika.application.services.general_harness_service
"""

from monika.application.services.general_harness_service import GeneralHarnessService

__all__ = [
    "GeneralHarnessService",
]
