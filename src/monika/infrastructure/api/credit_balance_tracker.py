"""
Backward-compatibility facade for CreditBalanceTracker.
Canonical location: monika.infrastructure.llm.rate_limiting.credit_balance_tracker
"""

import sys
import monika.infrastructure.llm.rate_limiting.credit_balance_tracker as _canonical

from monika.infrastructure.llm.rate_limiting.credit_balance_tracker import CreditBalanceTracker

__all__ = ["CreditBalanceTracker"]

sys.modules[__name__] = _canonical
