"""Shim module: monika.application.benchmark.db_models."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.db_models import *

_canonical = _importlib.import_module("monika.application.benchmark.db_models")
_sys.modules[__name__] = _canonical
