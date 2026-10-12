"""Shim module: monika.application.evals.runner."""

import sys as _sys
import importlib as _importlib

from monika.application.evals.runner import *

_canonical = _importlib.import_module("monika.application.evals.runner")
_sys.modules[__name__] = _canonical
