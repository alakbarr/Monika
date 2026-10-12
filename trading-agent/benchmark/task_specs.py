"""Shim module: monika.application.benchmark.task_specs."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.task_specs import *

_canonical = _importlib.import_module("monika.application.benchmark.task_specs")
_sys.modules[__name__] = _canonical
