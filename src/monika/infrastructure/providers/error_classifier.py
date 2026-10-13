"""
Backward-compatibility shim.

Use analysis.providers.provider_failover_classifier instead.
"""

from monika.infrastructure.providers.provider_failover_classifier import FailoverReason, classify_error

__all__ = ["FailoverReason", "classify_error"]
