"""Shim module: monika.application.benchmark.paired_evaluator."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.paired_evaluator import *

_canonical = _importlib.import_module("monika.application.benchmark.paired_evaluator")
_sys.modules[__name__] = _canonical
