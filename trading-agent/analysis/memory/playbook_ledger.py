"""Shim module: monika.application.analysis.memory.playbook_ledger."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.playbook_ledger import *

_canonical = _importlib.import_module("monika.application.analysis.memory.playbook_ledger")
_sys.modules[__name__] = _canonical
