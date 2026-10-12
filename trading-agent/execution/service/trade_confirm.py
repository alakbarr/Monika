"""Shim module: monika.application.execution.service.trade_confirm."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.service.trade_confirm import *

_canonical = _importlib.import_module("monika.application.execution.service.trade_confirm")
_sys.modules[__name__] = _canonical
