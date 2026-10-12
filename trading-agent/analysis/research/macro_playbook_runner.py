"""Shim module: monika.application.analysis.research.macro_playbook_runner."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.research.macro_playbook_runner import *

_canonical = _importlib.import_module("monika.application.analysis.research.macro_playbook_runner")
_sys.modules[__name__] = _canonical
