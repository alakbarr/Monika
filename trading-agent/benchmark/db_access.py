"""Shim module: monika.application.benchmark.db_access."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.db_access import *

_canonical = _importlib.import_module("monika.application.benchmark.db_access")
_sys.modules[__name__] = _canonical
