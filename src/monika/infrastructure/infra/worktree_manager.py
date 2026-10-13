"""
Backward-compatibility facade for WorktreeManager.
Canonical location: monika.infrastructure.sandboxes.worktree_manager
"""

import sys
import monika.infrastructure.sandboxes.worktree_manager as _canonical

from monika.infrastructure.sandboxes.worktree_manager import WorktreeManager

__all__ = ["WorktreeManager"]

sys.modules[__name__] = _canonical
