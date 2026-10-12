"""Shim module: monika.application.execution.service.reconciliation."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.service.reconciliation import *

_canonical = _importlib.import_module("monika.application.execution.service.reconciliation")
_sys.modules[__name__] = _canonical
