"""
Compatibility facade for canonical EnvFileManager.
Re-exports all symbols from monika.core.config.env_file_manager.
"""

import sys
import monika.core.config.env_file_manager as _canonical

from monika.core.config.env_file_manager import EnvFileManager

__all__ = ["EnvFileManager"]

sys.modules[__name__] = _canonical
