"""Shim module: monika.application.analysis.memory.playbook_linter."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.playbook_linter import *

_canonical = _importlib.import_module("monika.application.analysis.memory.playbook_linter")
_sys.modules[__name__] = _canonical
