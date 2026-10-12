"""Shim module: monika.application.analysis.journal.journal_parser."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.journal.journal_parser import *

_canonical = _importlib.import_module("monika.application.analysis.journal.journal_parser")
_sys.modules[__name__] = _canonical
