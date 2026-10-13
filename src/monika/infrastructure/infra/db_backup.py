"""
Backward-compatibility facade for DB backup.
Canonical location: monika.infrastructure.database.backup
"""

import sys
import monika.infrastructure.database.backup as _canonical

from monika.infrastructure.database.backup import create_backup

__all__ = ["create_backup"]

sys.modules[__name__] = _canonical
