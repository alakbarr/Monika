"""Shim module: monika.application.evals.eval_runner."""

import sys as _sys
import importlib as _importlib

from monika.application.evals.eval_runner import *

_canonical = _importlib.import_module("monika.application.evals.eval_runner")
_sys.modules[__name__] = _canonical
