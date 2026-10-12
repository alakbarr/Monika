"""Shim module: monika.application.execution.service.multi_account_adapter."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.service.multi_account_adapter import *

_canonical = _importlib.import_module("monika.application.execution.service.multi_account_adapter")
_sys.modules[__name__] = _canonical
