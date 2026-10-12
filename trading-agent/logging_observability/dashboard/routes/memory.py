"""
Compatibility facade shim for legacy memory.py.
Re-exports from canonical monika.interfaces.dashboard.routes.memory.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.memory as _canonical

from monika.interfaces.dashboard.routes.memory import (
    MemorySearchRequest,
    PlaybookRollbackRequest,
    get_lessons,
    get_playbook_history,
    get_playbooks,
    get_reflections,
    logger,
    memory_router,
    rollback_playbook,
    search_memory,
)

__all__ = ['MemorySearchRequest', 'PlaybookRollbackRequest', 'get_lessons', 'get_playbook_history', 'get_playbooks', 'get_reflections', 'logger', 'memory_router', 'rollback_playbook', 'search_memory']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
