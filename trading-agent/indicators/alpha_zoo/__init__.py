# ==============================================================================
# File: indicators/alpha_zoo/__init__.py
# Monika Quantitative Factor Zoo Package
# ==============================================================================

"""
Monika Quantitative Alpha Zoo Package.

Exports the enterprise factor registry, schema metadata, and automatically registers
quantitative factors for MetaTrader 5 markets.
"""

from indicators.alpha_zoo.meta import AlphaCategory, AlphaDirection, AlphaMeta
from indicators.alpha_zoo.registry import FactorRegistry, RegistryError, load_alpha_meta_from_py

# Auto-register standard formulations
import indicators.alpha_zoo.qlib158  # noqa: F401
import indicators.alpha_zoo.alpha101  # noqa: F401
import indicators.alpha_zoo.academic_factors  # noqa: F401
import indicators.alpha_zoo.microstructure_factors  # noqa: F401
import indicators.alpha_zoo.fundamental_factors  # noqa: F401

__all__ = [
    "AlphaCategory",
    "AlphaDirection",
    "AlphaMeta",
    "FactorRegistry",
    "RegistryError",
    "load_alpha_meta_from_py",
]

