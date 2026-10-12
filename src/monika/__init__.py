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

install_legacy_compat()

__all__ = [
    "__version__",
    "__author__",
    "install_legacy_compat",
]
