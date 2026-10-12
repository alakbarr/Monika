# ==============================================================================
# File: indicators/alpha_zoo/registry.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.registry
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.registry
"""

import sys
import monika.domain.indicators.alpha_zoo.registry as _canonical

from monika.domain.indicators.alpha_zoo.registry import (
    AlphaMeta,
    AlphaZooRegistry,
    FactorCallable,
    FactorRegistry,
    RegistryError,
    annotations,
    load_alpha_meta_from_py,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AlphaMeta",
    "AlphaZooRegistry",
    "FactorCallable",
    "FactorRegistry",
    "RegistryError",
    "annotations",
    "load_alpha_meta_from_py",
]
