"""Shim module: monika.application.main."""

import sys as _sys
import importlib as _importlib

from monika.application.main import *

_canonical = _importlib.import_module("monika.application.main")
_sys.modules[__name__] = _canonical

if __name__ == "__main__":
    import asyncio
    asyncio.run(_canonical.main())
