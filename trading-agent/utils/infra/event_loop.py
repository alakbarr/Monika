"""
Event loop configuration for Windows compatibility.

Psycopg 3 (used by langgraph-checkpoint-postgres) requires
SelectorEventLoop because ProactorEventLoop on Windows does not
implement loop.add_reader() / loop.add_writer().

Python 3.14 deprecates set_event_loop_policy() — use loop_factory instead.
"""

import asyncio
import sys
from typing import Any, Dict


from utils.infra.platform_compat import configure_event_loop, IS_WINDOWS


def get_loop_factory() -> Dict[str, Any]:
    """
    Return loop_factory keyword arguments for asyncio.run() or asyncio.Runner.

    Usage:
        asyncio.run(main(), **get_loop_factory())
    """
    return configure_event_loop()


def run_async(coroutine: Any, **kwargs: Any) -> Any:
    """
    Execute coroutine using asyncio.run() with SelectorEventLoop on Windows.

    Usage:
        run_async(main())
    """
    factory_kwargs = get_loop_factory()
    merged_kwargs = {**factory_kwargs, **kwargs}
    if sys.version_info < (3, 12):
        merged_kwargs.pop("loop_factory", None)
        if IS_WINDOWS:
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except Exception:
                pass
    return asyncio.run(coroutine, **merged_kwargs)
