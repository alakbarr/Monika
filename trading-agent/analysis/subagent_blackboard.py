"""Shim module: monika.application.analysis.subagent_blackboard."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.subagent_blackboard import *

_canonical = _importlib.import_module("monika.application.analysis.subagent_blackboard")
_sys.modules[__name__] = _canonical
