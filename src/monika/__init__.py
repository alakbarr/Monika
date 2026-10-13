# ==============================================================================
# Package: monika
# Description: Monika Algorithmic Trading Platform & General-Purpose Agent Harness
# ==============================================================================

"""
Monika: Autonomous SOTA Algorithmic Trading Platform & General-Purpose Agent Harness.
Institutional Clean Architecture package layout.
"""

__version__ = "1.0.0"
__author__ = "Saiful Akbar"

from monika.infrastructure.infra.legacy_compat import install_legacy_compat

# Note: legacy_compat is deprecated. The monika package layout is 100% canonical.
# install_legacy_compat() remains exported for legacy test harnesses and scripts.

__all__ = [
    "__version__",
    "__author__",
    "install_legacy_compat",
]
