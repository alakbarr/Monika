"""Shim module: monika.application.analysis.memory.skill_ledger_sha."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.skill_ledger_sha import *

_canonical = _importlib.import_module("monika.application.analysis.memory.skill_ledger_sha")
_sys.modules[__name__] = _canonical
