"""Shim module: monika.application.analysis.debate.blackboard."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.debate.blackboard import *

_canonical = _importlib.import_module("monika.application.analysis.debate.blackboard")
_sys.modules[__name__] = _canonical
