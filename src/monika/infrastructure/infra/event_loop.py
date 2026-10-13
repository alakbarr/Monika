"""
Compatibility facade for canonical event loop helpers.
Re-exports symbols from monika.core.platform.
"""

from monika.core.platform import get_loop_factory, run_async

__all__ = ["get_loop_factory", "run_async"]
