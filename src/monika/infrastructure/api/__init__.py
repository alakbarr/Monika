"""
Backward-compatibility package for infrastructure.api.
Canonical package: monika.infrastructure.llm.rate_limiting
"""

import sys
import monika.infrastructure.llm.rate_limiting as _canonical

sys.modules[__name__] = _canonical
