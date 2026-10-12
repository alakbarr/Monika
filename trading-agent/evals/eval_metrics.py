"""Shim module: monika.application.evals.eval_metrics."""

import sys as _sys
import importlib as _importlib

from monika.application.evals.eval_metrics import *

_canonical = _importlib.import_module("monika.application.evals.eval_metrics")
_sys.modules[__name__] = _canonical
