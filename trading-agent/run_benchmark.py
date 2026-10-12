"""Shim module: monika.application.benchmark.run_benchmark."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.run_benchmark import *

_canonical = _importlib.import_module("monika.application.benchmark.run_benchmark")
_sys.modules[__name__] = _canonical

if __name__ == "__main__":
    import asyncio
    asyncio.run(_canonical.main())
