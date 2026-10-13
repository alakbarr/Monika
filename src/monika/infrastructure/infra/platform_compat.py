"""
Compatibility facade for canonical platform engine.
Re-exports all symbols from monika.core.platform.
"""

import sys
import monika.core.platform as _canonical

from monika.core.platform import (
    IS_DARWIN,
    IS_LINUX,
    IS_WINE,
    IS_WINDOWS,
    configure_event_loop,
    get_loop_factory,
    normalize_path,
    run_async,
    safe_subprocess_run,
)

__all__ = [
    "IS_WINDOWS",
    "IS_LINUX",
    "IS_DARWIN",
    "IS_WINE",
    "configure_event_loop",
    "get_loop_factory",
    "run_async",
    "normalize_path",
    "safe_subprocess_run",
]

sys.modules[__name__] = _canonical
