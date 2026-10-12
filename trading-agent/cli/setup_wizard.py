"""
Compatibility facade shim for legacy setup_wizard.py.
Re-exports from canonical monika.interfaces.cli.setup_wizard.
"""

from __future__ import annotations

import monika.interfaces.cli.setup_wizard as _canonical

from monika.interfaces.cli.setup_wizard import (
    SetupWizard,
    clean_terminal_input,
    logger,
)

__all__ = ['SetupWizard', 'clean_terminal_input', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
