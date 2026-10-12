"""Shim module: monika.application.analysis.harness.agent_harness."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.harness.agent_harness import *

_canonical = _importlib.import_module("monika.application.analysis.harness.agent_harness")
_sys.modules[__name__] = _canonical
