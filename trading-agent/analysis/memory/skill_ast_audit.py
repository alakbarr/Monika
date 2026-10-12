"""Shim module: monika.application.analysis.memory.skill_ast_audit."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.skill_ast_audit import *

_canonical = _importlib.import_module("monika.application.analysis.memory.skill_ast_audit")
_sys.modules[__name__] = _canonical
