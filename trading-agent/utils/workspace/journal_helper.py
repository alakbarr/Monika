"""
Compatibility facade shim for legacy journal_helper.py.
Re-exports from canonical monika.interfaces.workspace.journal_helper.
"""

from __future__ import annotations

import monika.interfaces.workspace.journal_helper as _canonical

from monika.interfaces.workspace.journal_helper import (
    format_dataview_journal,
    format_spreadsheet_row,
    record_trade_to_workspace,
)

__all__ = ['format_dataview_journal', 'format_spreadsheet_row', 'record_trade_to_workspace']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
